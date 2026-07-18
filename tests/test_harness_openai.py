"""Tests for the OpenAI API-direct harness.

Same test tiers as the Anthropic harness: offline dry-run + mocked
live path always run; ``@pytest.mark.integration`` exercises the
real API only when ``OPENAI_API_KEY`` is set.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from harness.api._common import CorpusRecord
from harness.api.openai import (
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


@pytest.fixture
def sample_records() -> list[CorpusRecord]:
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
    ]


def test_payload_has_expected_top_level_keys() -> None:
    payload = build_request_payload("hello", DEFAULT_MODEL)
    assert set(payload.keys()) == {"model", "max_tokens", "messages"}


def test_payload_uses_supplied_model() -> None:
    payload = build_request_payload("hi", "gpt-4o-mini")
    assert payload["model"] == "gpt-4o-mini"


def test_payload_prompt_text_preserved_verbatim() -> None:
    prompt = "SSN 123-45-6789 update."
    payload = build_request_payload(prompt, DEFAULT_MODEL)
    assert payload["messages"] == [{"role": "user", "content": prompt}]


def test_payload_max_tokens_default() -> None:
    payload = build_request_payload("x", DEFAULT_MODEL)
    assert payload["max_tokens"] == DEFAULT_MAX_TOKENS


def test_dry_run_produces_result_without_calling_client(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    assert result.dry_run is True
    assert result.response_text == ""
    assert result.tool == TOOL_NAME
    assert result.tier == TIER


def test_dry_run_marks_sent_verbatim_true(
    sample_records: list[CorpusRecord],
) -> None:
    for record in sample_records:
        result = run_single(record, DEFAULT_MODEL, client=None, dry_run=True)
        assert result.sent_verbatim is True


def test_dry_run_populates_outbound_findings(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    assert any(f.type == "SSN" for f in result.outbound_findings)


def _mock_response(text: str) -> Any:
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def test_run_single_calls_client_with_payload_kwargs(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("ok")

    run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)

    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["messages"][0]["content"] == sample_records[0].prompt_text


def test_run_single_captures_response_text(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("acknowledged")
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.response_text == "acknowledged"
    assert result.error == ""


def test_run_single_records_error_on_api_failure(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("rate limit")
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert "RuntimeError" in result.error
    assert "rate limit" in result.error
    captured_prompt = result.request_payload["messages"][0]["content"]
    assert captured_prompt == sample_records[0].prompt_text


def test_extract_response_text_concatenates_all_choices() -> None:
    response = MagicMock()
    msg_a = MagicMock()
    msg_a.content = "hello "
    msg_b = MagicMock()
    msg_b.content = "world"
    choice_a = MagicMock()
    choice_a.message = msg_a
    choice_b = MagicMock()
    choice_b.message = msg_b
    response.choices = [choice_a, choice_b]
    assert _extract_response_text(response) == "hello world"


def test_extract_response_text_handles_empty_choices() -> None:
    response = MagicMock()
    response.choices = []
    assert _extract_response_text(response) == ""


def test_run_all_preserves_input_order(
    sample_records: list[CorpusRecord],
) -> None:
    results = run_all(sample_records, DEFAULT_MODEL, client=None, dry_run=True)
    assert [r.prompt_id for r in results] == [r.id for r in sample_records]


def _write_mini_corpus(path: object) -> None:
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
    assert data["count"] == 1
    assert data["results"][0]["tool"] == TOOL_NAME


def test_main_live_run_without_api_key_errors_cleanly(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    old = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            main(["--corpus", str(corpus), "--output", str(output)])
    finally:
        if old is not None:
            os.environ["OPENAI_API_KEY"] = old


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping live integration test",
)
def test_integration_single_prompt_round_trip(
    tmp_path: Path, sample_records: list[CorpusRecord]
) -> None:
    """One-prompt live round trip. Cost: ~$0.001."""
    from harness.api.openai import _build_client

    client = _build_client()
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.error == "" or result.response_text != ""
    captured_prompt = result.request_payload["messages"][0]["content"]
    assert captured_prompt == sample_records[0].prompt_text
    assert result.sent_verbatim is True
