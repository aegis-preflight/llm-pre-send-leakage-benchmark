"""Tests for the Anthropic API-direct harness.

Split into two tiers:

- Default (offline): dry-run and pure-function tests. No network, no
  API key, no dependency on the anthropic SDK actually being installed.
  These run in CI on every push.
- ``@pytest.mark.integration``: exercises the real Anthropic API. Only
  runs locally when ``ANTHROPIC_API_KEY`` is set. Excluded from CI.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from harness.api._common import CorpusRecord
from harness.api.anthropic import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    TIER,
    TOOL_NAME,
    _extract_response_text,
    build_request_payload,
    main,
    run_all,
    run_single,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_records() -> list[CorpusRecord]:
    """Three records covering clean, single-PII, and multi-PII prompts."""
    return [
        CorpusRecord(
            id="ident-001",
            category="identifiers",
            subcategory="ssn",
            prompt_text="Please verify customer record: SSN 123-45-6789.",
            expected_categories=["SSN"],
            expected_count={"SSN": 1},
        ),
        CorpusRecord(
            id="contact-001",
            category="contact",
            subcategory="email",
            prompt_text="Send a welcome note to alice@example.com about onboarding.",
            expected_categories=["EMAIL"],
            expected_count={"EMAIL": 1},
        ),
        CorpusRecord(
            id="mixed-001",
            category="mixed",
            subcategory="ssn_email",
            prompt_text=(
                "Customer service: reach out to alice@example.com about "
                "their SSN 123-45-6789 update request."
            ),
            expected_categories=["SSN", "EMAIL"],
            expected_count={"SSN": 1, "EMAIL": 1},
        ),
    ]


# ---------------------------------------------------------------------------
# build_request_payload
# ---------------------------------------------------------------------------


def test_payload_has_expected_top_level_keys() -> None:
    payload = build_request_payload("hello", DEFAULT_MODEL)
    assert set(payload.keys()) == {"model", "max_tokens", "messages"}


def test_payload_uses_supplied_model() -> None:
    payload = build_request_payload("hi", "claude-opus-4-7")
    assert payload["model"] == "claude-opus-4-7"


def test_payload_prompt_text_preserved_verbatim() -> None:
    prompt = "Please verify SSN 123-45-6789 for the customer file."
    payload = build_request_payload(prompt, DEFAULT_MODEL)
    assert payload["messages"] == [{"role": "user", "content": prompt}]


def test_payload_max_tokens_default() -> None:
    payload = build_request_payload("x", DEFAULT_MODEL)
    assert payload["max_tokens"] == DEFAULT_MAX_TOKENS


# ---------------------------------------------------------------------------
# run_single — dry run path
# ---------------------------------------------------------------------------


def test_dry_run_produces_result_without_calling_client(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    assert result.dry_run is True
    assert result.response_text == ""
    assert result.tool == TOOL_NAME
    assert result.tier == TIER


def test_dry_run_captures_payload(sample_records: list[CorpusRecord]) -> None:
    """Even without a network call, the payload the SDK *would* send is captured."""
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    content = result.request_payload["messages"][0]["content"]
    assert content == sample_records[0].prompt_text


def test_dry_run_marks_sent_verbatim_true_for_api_direct(
    sample_records: list[CorpusRecord],
) -> None:
    """API-direct tier never scrubs — every prompt is sent verbatim."""
    for record in sample_records:
        result = run_single(record, DEFAULT_MODEL, client=None, dry_run=True)
        assert result.sent_verbatim is True, f"{record.id} unexpectedly not verbatim"


def test_dry_run_populates_outbound_findings_for_ssn(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    types = {f.type for f in result.outbound_findings}
    assert "SSN" in types


def test_dry_run_populates_outbound_findings_for_email(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[1], DEFAULT_MODEL, client=None, dry_run=True)
    types = {f.type for f in result.outbound_findings}
    assert "EMAIL" in types


def test_dry_run_mixed_prompt_finds_all_categories(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[2], DEFAULT_MODEL, client=None, dry_run=True)
    types = {f.type for f in result.outbound_findings}
    assert {"SSN", "EMAIL"}.issubset(types)


# ---------------------------------------------------------------------------
# run_single — live client path (mocked)
# ---------------------------------------------------------------------------


def _mock_anthropic_response(text: str) -> Any:
    """Build a mock that mimics anthropic.types.Message shape."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_run_single_calls_client_with_payload_kwargs(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("ok")

    run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)

    client.messages.create.assert_called_once()
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["max_tokens"] == DEFAULT_MAX_TOKENS
    assert kwargs["messages"][0]["content"] == sample_records[0].prompt_text


def test_run_single_captures_response_text(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("acknowledged")
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.response_text == "acknowledged"
    assert result.error == ""


def test_run_single_records_error_on_api_failure(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("rate limit")
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.response_text == ""
    assert "RuntimeError" in result.error
    assert "rate limit" in result.error
    # Even under failure, the request payload we would have sent is captured.
    captured_prompt = result.request_payload["messages"][0]["content"]
    assert captured_prompt == sample_records[0].prompt_text


# ---------------------------------------------------------------------------
# _extract_response_text
# ---------------------------------------------------------------------------


def test_extract_response_text_concatenates_all_text_blocks() -> None:
    response = MagicMock()
    a = MagicMock()
    a.text = "hello "
    b = MagicMock()
    b.text = "world"
    response.content = [a, b]
    assert _extract_response_text(response) == "hello world"


def test_extract_response_text_ignores_non_text_blocks() -> None:
    response = MagicMock()
    text_block = MagicMock()
    text_block.text = "spoken text"
    tool_block = MagicMock(spec=[])  # spec=[] → no `.text` attribute
    response.content = [tool_block, text_block]
    assert _extract_response_text(response) == "spoken text"


def test_extract_response_text_handles_empty_content() -> None:
    response = MagicMock()
    response.content = []
    assert _extract_response_text(response) == ""


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------


def test_run_all_preserves_input_order(sample_records: list[CorpusRecord]) -> None:
    results = run_all(sample_records, DEFAULT_MODEL, client=None, dry_run=True)
    assert [r.prompt_id for r in results] == [r.id for r in sample_records]


def test_run_all_processes_every_record(sample_records: list[CorpusRecord]) -> None:
    results = run_all(sample_records, DEFAULT_MODEL, client=None, dry_run=True)
    assert len(results) == len(sample_records)


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


def _write_mini_corpus(path: object) -> None:
    """Write a 2-record corpus to ``path`` for CLI tests."""
    from pathlib import Path

    p = Path(str(path))
    with p.open("w", encoding="utf-8") as fp:
        fp.write(
            json.dumps(
                {
                    "id": "ident-001",
                    "category": "identifiers",
                    "subcategory": "ssn",
                    "prompt_text": "SSN 123-45-6789",
                    "expected_categories": ["SSN"],
                    "expected_count": {"SSN": 1},
                }
            )
            + "\n"
        )
        fp.write(
            json.dumps(
                {
                    "id": "contact-001",
                    "category": "contact",
                    "subcategory": "email",
                    "prompt_text": "Email me@example.com",
                    "expected_categories": ["EMAIL"],
                    "expected_count": {"EMAIL": 1},
                }
            )
            + "\n"
        )


def test_main_dry_run_writes_output(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    exit_code = main(
        [
            "--corpus",
            str(corpus),
            "--output",
            str(output),
            "--dry-run",
        ]
    )
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert all(r["dry_run"] for r in data["results"])


def test_main_dry_run_respects_limit(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    exit_code = main(
        [
            "--corpus",
            str(corpus),
            "--output",
            str(output),
            "--dry-run",
            "--limit",
            "1",
        ]
    )
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["results"][0]["prompt_id"] == "ident-001"


def test_main_live_run_without_api_key_errors_cleanly(tmp_path: Path) -> None:
    """A live run without ANTHROPIC_API_KEY should raise with a helpful message."""
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    # Ensure the env var is absent for this test regardless of dev environment.
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            main(["--corpus", str(corpus), "--output", str(output)])
    finally:
        if old is not None:
            os.environ["ANTHROPIC_API_KEY"] = old


# ---------------------------------------------------------------------------
# Integration — real Anthropic API. Only runs if key is present.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live integration test",
)
def test_integration_single_prompt_round_trip(
    tmp_path: Path, sample_records: list[CorpusRecord]
) -> None:
    """Confirm the harness completes a real API call end-to-end.

    Exercises exactly one prompt to keep cost negligible (~$0.001).
    """
    from harness.api.anthropic import _build_client

    client = _build_client()
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.error == "" or result.response_text != ""
    captured_prompt = result.request_payload["messages"][0]["content"]
    assert captured_prompt == sample_records[0].prompt_text
    assert result.sent_verbatim is True
