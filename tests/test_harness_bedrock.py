"""Tests for the AWS Bedrock API-direct harness."""

from __future__ import annotations

import io
import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from harness.api._common import CorpusRecord
from harness.api.bedrock import (
    BEDROCK_ANTHROPIC_VERSION,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    TIER,
    TOOL_NAME,
    _extract_response_text,
    _payload_body,
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
    ]


def test_payload_has_expected_keys() -> None:
    payload = build_request_payload("hello", DEFAULT_MODEL)
    assert set(payload.keys()) == {
        "model",
        "anthropic_version",
        "max_tokens",
        "messages",
    }


def test_payload_carries_bedrock_anthropic_version() -> None:
    payload = build_request_payload("hi", DEFAULT_MODEL)
    assert payload["anthropic_version"] == BEDROCK_ANTHROPIC_VERSION


def test_payload_records_model_id() -> None:
    payload = build_request_payload("x", "anthropic.claude-opus-4-v1:0")
    assert payload["model"] == "anthropic.claude-opus-4-v1:0"


def test_payload_body_strips_model_key() -> None:
    """``model`` is passed as modelId to boto3, not inside the JSON body."""
    payload = build_request_payload("hi", DEFAULT_MODEL)
    body = json.loads(_payload_body(payload))
    assert "model" not in body
    assert body["anthropic_version"] == BEDROCK_ANTHROPIC_VERSION
    assert body["messages"][0]["content"] == "hi"


def test_payload_max_tokens_default() -> None:
    payload = build_request_payload("x", DEFAULT_MODEL)
    assert payload["max_tokens"] == DEFAULT_MAX_TOKENS


def test_dry_run_produces_result_without_calling_client(
    sample_records: list[CorpusRecord],
) -> None:
    result = run_single(sample_records[0], DEFAULT_MODEL, client=None, dry_run=True)
    assert result.dry_run is True
    assert result.tool == TOOL_NAME
    assert result.tier == TIER
    assert result.model == DEFAULT_MODEL


def test_dry_run_marks_sent_verbatim_true(
    sample_records: list[CorpusRecord],
) -> None:
    for record in sample_records:
        result = run_single(record, DEFAULT_MODEL, client=None, dry_run=True)
        assert result.sent_verbatim is True


def _mock_bedrock_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Mimic the shape boto3 returns from invoke_model — body is a stream."""
    stream = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return {"body": stream}


def test_run_single_calls_client_with_correct_kwargs(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.invoke_model.return_value = _mock_bedrock_response(
        {"content": [{"text": "ok"}]}
    )

    run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)

    client.invoke_model.assert_called_once()
    kwargs = client.invoke_model.call_args.kwargs
    assert kwargs["modelId"] == DEFAULT_MODEL
    assert kwargs["contentType"] == "application/json"
    body = json.loads(kwargs["body"])
    assert body["anthropic_version"] == BEDROCK_ANTHROPIC_VERSION
    assert body["messages"][0]["content"] == sample_records[0].prompt_text


def test_run_single_captures_response_text(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.invoke_model.return_value = _mock_bedrock_response(
        {"content": [{"text": "acknowledged"}]}
    )
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.response_text == "acknowledged"
    assert result.error == ""


def test_run_single_records_error_on_api_failure(
    sample_records: list[CorpusRecord],
) -> None:
    client = MagicMock()
    client.invoke_model.side_effect = RuntimeError("throttling")
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert "RuntimeError" in result.error
    assert "throttling" in result.error


def test_extract_response_text_concatenates_blocks() -> None:
    body = _mock_bedrock_response({"content": [{"text": "hello "}, {"text": "world"}]})
    assert _extract_response_text(body) == "hello world"


def test_extract_response_text_ignores_non_text_blocks() -> None:
    body = _mock_bedrock_response(
        {"content": [{"type": "tool_use", "id": "t1"}, {"text": "spoken"}]}
    )
    assert _extract_response_text(body) == "spoken"


def test_extract_response_text_handles_empty_content() -> None:
    body = _mock_bedrock_response({"content": []})
    assert _extract_response_text(body) == ""


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


def test_main_live_run_without_region_errors_cleanly(tmp_path: Path) -> None:
    corpus = tmp_path / "mini.jsonl"
    output = tmp_path / "results.json"
    _write_mini_corpus(corpus)

    old_region = os.environ.pop("AWS_REGION", None)
    old_default = os.environ.pop("AWS_DEFAULT_REGION", None)
    try:
        with pytest.raises(RuntimeError, match="AWS_REGION"):
            main(["--corpus", str(corpus), "--output", str(output)])
    finally:
        if old_region is not None:
            os.environ["AWS_REGION"] = old_region
        if old_default is not None:
            os.environ["AWS_DEFAULT_REGION"] = old_default


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("AWS_REGION") or not os.environ.get("AWS_ACCESS_KEY_ID"),
    reason="AWS credentials not set — skipping live integration test",
)
def test_integration_single_prompt_round_trip(
    tmp_path: Path, sample_records: list[CorpusRecord]
) -> None:
    """One-prompt live round trip. Cost: ~$0.003."""
    from harness.api.bedrock import _build_client

    client = _build_client()
    result = run_single(sample_records[0], DEFAULT_MODEL, client=client, dry_run=False)
    assert result.error == "" or result.response_text != ""
    captured_prompt = result.request_payload["messages"][0]["content"]
    assert captured_prompt == sample_records[0].prompt_text
    assert result.sent_verbatim is True
