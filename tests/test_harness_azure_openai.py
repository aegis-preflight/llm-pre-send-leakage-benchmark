"""Tests for the Azure OpenAI API-direct harness."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from harness.api._common import CorpusRecord
from harness.api.azure_openai import (
    DEFAULT_MAX_TOKENS,
    DEPLOYMENT_ENV,
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

TEST_DEPLOYMENT = "test-deployment"


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
    ]


def test_payload_has_expected_top_level_keys() -> None:
    payload = build_request_payload("hello", TEST_DEPLOYMENT)
    assert set(payload.keys()) == {"model", "max_tokens", "messages"}


def test_payload_uses_deployment_as_model_field() -> None:
    payload = build_request_payload("hi", "prod-gpt-4o")
    assert payload["model"] == "prod-gpt-4o"


def test_payload_prompt_text_preserved_verbatim() -> None:
    prompt = "SSN 123-45-6789 update."
    payload = build_request_payload(prompt, TEST_DEPLOYMENT)
    assert payload["messages"] == [{"role": "user", "content": prompt}]


def test_payload_max_tokens_default() -> None:
    payload = build_request_payload("x", TEST_DEPLOYMENT)
    assert payload["max_tokens"] == DEFAULT_MAX_TOKENS


def test_dry_run_produces_result_without_calling_client(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], TEST_DEPLOYMENT, client=None, dry_run=True)
    assert result.dry_run is True
    assert result.tool == TOOL_NAME
    assert result.tier == TIER
    assert result.model == TEST_DEPLOYMENT


def test_dry_run_marks_sent_verbatim_true(
    sample_records: list[CorpusRecord],
) -> None:
    for record in sample_records:
        result = run_single(record, TEST_DEPLOYMENT, client=None, dry_run=True)
        assert result.sent_verbatim is True


def _mock_response(text: str) -> Any:
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def test_run_single_calls_client_with_deployment_as_model(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("ok")

    run_single(sample_records[0], TEST_DEPLOYMENT, client=client, dry_run=False)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == TEST_DEPLOYMENT
    assert kwargs["messages"][0]["content"] == sample_records[0].prompt_text


def test_run_single_captures_response_text(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("acknowledged")
    result = run_single(
        sample_records[0], TEST_DEPLOYMENT, client=client, dry_run=False
    )
    assert result.response_text == "acknowledged"


def test_run_single_records_error_on_api_failure(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("quota")
    result = run_single(
        sample_records[0], TEST_DEPLOYMENT, client=client, dry_run=False
    )
    assert "RuntimeError" in result.error
    assert "quota" in result.error


def test_extract_response_text_ok() -> None:
    response = MagicMock()
    msg = MagicMock()
    msg.content = "hi there"
    choice = MagicMock()
    choice.message = msg
    response.choices = [choice]
    assert _extract_response_text(response) == "hi there"


def test_run_all_preserves_input_order(
    sample_records: list[CorpusRecord],
) -> None:
    results = run_all(sample_records, TEST_DEPLOYMENT, client=None, dry_run=True)
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


def test_main_dry_run_with_model_arg(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    exit_code = main(
        [
            "--corpus",
            str(corpus),
            "--output",
            str(output),
            "--model",
            TEST_DEPLOYMENT,
            "--dry-run",
        ]
    )
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["results"][0]["model"] == TEST_DEPLOYMENT


def test_main_dry_run_uses_deployment_env_var(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    os.environ[DEPLOYMENT_ENV] = "env-deployment"
    try:
        exit_code = main(
            [
                "--corpus",
                str(corpus),
                "--output",
                str(output),
                "--dry-run",
            ]
        )
    finally:
        os.environ.pop(DEPLOYMENT_ENV, None)
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["results"][0]["model"] == "env-deployment"


def test_main_errors_when_deployment_missing(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    old = os.environ.pop(DEPLOYMENT_ENV, None)
    try:
        with pytest.raises(RuntimeError, match="Deployment name required"):
            main(["--corpus", str(corpus), "--output", str(output), "--dry-run"])
    finally:
        if old is not None:
            os.environ[DEPLOYMENT_ENV] = old


def test_main_live_run_without_credentials_errors_cleanly(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    saved = {
        k: os.environ.pop(k, None)
        for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")
    }
    try:
        with pytest.raises(RuntimeError, match=r"AZURE_OPENAI_(API_KEY|ENDPOINT)"):
            main(
                [
                    "--corpus",
                    str(corpus),
                    "--output",
                    str(output),
                    "--model",
                    TEST_DEPLOYMENT,
                ]
            )
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


@pytest.mark.integration
@pytest.mark.skipif(
    not (
        os.environ.get("AZURE_OPENAI_API_KEY")
        and os.environ.get("AZURE_OPENAI_ENDPOINT")
        and os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    ),
    reason="Azure OpenAI credentials not set — skipping live integration test",
)
def test_integration_single_prompt_round_trip(
    tmp_path: Path, sample_records: list[CorpusRecord]
) -> None:
    """One-prompt live round trip against a real Azure deployment."""
    from harness.api.azure_openai import _build_client

    client = _build_client()
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    result = run_single(sample_records[0], deployment, client=client, dry_run=False)
    assert result.error == "" or result.response_text != ""
    assert result.sent_verbatim is True
