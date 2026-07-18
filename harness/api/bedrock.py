r"""Pre-Send Leakage Benchmark — AWS Bedrock API-direct harness.

Bedrock is a family of foundation-model APIs behind a single AWS
endpoint (``bedrock-runtime.<region>.amazonaws.com``). The v1 benchmark
targets Anthropic Claude on Bedrock as the default — the most common
enterprise deployment. The payload shape is Anthropic's Messages API
with a Bedrock-specific version marker.

By construction, ``sent_verbatim`` is True for every corpus prompt in
this tier: the SDK serializes the payload dict to JSON and puts it on
the wire unchanged.

Authentication uses the standard AWS credential chain (env vars,
shared credentials file, IAM role, etc.). The harness requires only
that ``AWS_REGION`` (or ``AWS_DEFAULT_REGION``) resolves — every other
credential source that ``boto3`` accepts is honored.

Usage
-----
::

    # Real run. AWS credentials from the environment or ~/.aws/credentials.
    export AWS_REGION=us-east-1
    uv run python harness/api/bedrock.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output results/raw/bedrock.json

    # Offline smoke test.
    uv run python harness/api/bedrock.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output /tmp/bedrock-dryrun.json \\
        --dry-run --limit 3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from harness.api._common import (
    CorpusRecord,
    HarnessResult,
    compute_sent_verbatim,
    load_corpus,
    utc_now_iso,
    write_results,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

LOGGER = logging.getLogger(__name__)

TOOL_NAME: Final[str] = "bedrock"
TIER: Final[str] = "api-direct"
# Bedrock model IDs are region- and account-scoped. This default is a
# stable Anthropic-on-Bedrock ID that has been available since 2024
# and works in every US region. Override via ``--model`` for cross-
# region inference profiles (``us.anthropic.claude-*``) or newer
# Sonnet snapshots as they GA.
DEFAULT_MODEL: Final[str] = "anthropic.claude-3-5-sonnet-20241022-v2:0"
DEFAULT_MAX_TOKENS: Final[int] = 256
# The version string Bedrock requires in the payload for Claude models.
# Not the same as the SDK version — this is the Anthropic-on-Bedrock
# API version.
BEDROCK_ANTHROPIC_VERSION: Final[str] = "bedrock-2023-05-31"
REGION_ENV: Final[str] = "AWS_REGION"
FALLBACK_REGION_ENV: Final[str] = "AWS_DEFAULT_REGION"


def build_request_payload(prompt_text: str, model: str) -> dict[str, Any]:
    """Reconstruct the JSON body ``bedrock-runtime.invoke_model`` sends.

    The scorer inspects this dict for evidence of pre-send redaction.
    ``model`` is not included in the body itself — Bedrock takes it as
    a separate ``modelId`` parameter — but we include it in the
    returned dict under a leading key so results files preserve the
    full context of the call.

    Args:
        prompt_text: The corpus prompt.
        model: Bedrock ``modelId``. Recorded for traceability.

    Returns:
        Serializable dict. The ``model`` key is metadata; every other
        key is what ``boto3`` JSON-encodes as the wire body.
    """
    return {
        "model": model,
        "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": prompt_text,
            }
        ],
    }


def _payload_body(payload: dict[str, Any]) -> str:
    """Strip metadata and return the JSON body the SDK will actually send."""
    body = {k: v for k, v in payload.items() if k != "model"}
    return json.dumps(body)


def run_single(
    record: CorpusRecord,
    model: str,
    client: Any | None,
    *,
    dry_run: bool,
) -> HarnessResult:
    """Run one corpus prompt through the harness. See anthropic.run_single."""
    payload = build_request_payload(record.prompt_text, model)
    sent_verbatim, findings = compute_sent_verbatim(
        record.prompt_text, payload, record.expected_categories
    )
    timestamp = utc_now_iso()

    if dry_run:
        return HarnessResult(
            prompt_id=record.id,
            tool=TOOL_NAME,
            tier=TIER,
            model=model,
            timestamp_utc=timestamp,
            request_payload=payload,
            response_text="",
            outbound_findings=findings,
            sent_verbatim=sent_verbatim,
            dry_run=True,
        )

    if client is None:
        msg = "client is required when dry_run=False"
        raise RuntimeError(msg)

    try:
        response = client.invoke_model(
            modelId=model,
            body=_payload_body(payload),
            contentType="application/json",
            accept="application/json",
        )
    except Exception as exc:
        LOGGER.warning("Bedrock call failed for %s: %s", record.id, exc)
        return HarnessResult(
            prompt_id=record.id,
            tool=TOOL_NAME,
            tier=TIER,
            model=model,
            timestamp_utc=timestamp,
            request_payload=payload,
            response_text="",
            outbound_findings=findings,
            sent_verbatim=sent_verbatim,
            error=f"{type(exc).__name__}: {exc}",
        )

    response_text = _extract_response_text(response)
    return HarnessResult(
        prompt_id=record.id,
        tool=TOOL_NAME,
        tier=TIER,
        model=model,
        timestamp_utc=timestamp,
        request_payload=payload,
        response_text=response_text,
        outbound_findings=findings,
        sent_verbatim=sent_verbatim,
    )


def _extract_response_text(response: Any) -> str:
    """Pull text out of a Bedrock ``invoke_model`` response.

    Shape (for Claude on Bedrock): ``response['body']`` is a stream;
    the JSON payload has a ``content`` list of blocks; text blocks
    have a ``text`` field. Non-text blocks are ignored.
    """
    body_obj = response["body"] if isinstance(response, dict) else response.body
    raw = body_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    parsed = json.loads(raw)
    parts: list[str] = []
    for block in parsed.get("content", []) or []:
        text = block.get("text") if isinstance(block, dict) else None
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def run_all(
    records: Iterable[CorpusRecord],
    model: str,
    client: Any | None,
    *,
    dry_run: bool,
) -> list[HarnessResult]:
    """Run every record and return the results in input order."""
    results: list[HarnessResult] = []
    for record in records:
        LOGGER.info(
            "Testing %s (%s/%s)", record.id, record.category, record.subcategory
        )
        results.append(run_single(record, model, client, dry_run=dry_run))
    return results


def _build_client() -> Any:
    """Import and construct a Bedrock runtime client (deferred)."""
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - environment error
        msg = (
            "boto3 is not installed. Install it with "
            "`uv sync --extra harness-bedrock` or run with --dry-run."
        )
        raise RuntimeError(msg) from exc

    region = os.environ.get(REGION_ENV) or os.environ.get(FALLBACK_REGION_ENV)
    if not region:
        msg = (
            f"{REGION_ENV} (or {FALLBACK_REGION_ENV}) must be set for a live "
            "run (or pass --dry-run)."
        )
        raise RuntimeError(msg)
    return boto3.client("bedrock-runtime", region_name=region)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Pre-Send Leakage Benchmark against AWS Bedrock "
            "invoke_model (api-direct tier)."
        ),
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    records = load_corpus(args.corpus)
    if args.limit is not None:
        records = records[: args.limit]
    LOGGER.info("Loaded %d records from %s", len(records), args.corpus)

    client = None if args.dry_run else _build_client()
    if args.dry_run:
        LOGGER.info("Dry-run mode: no API calls will be made.")

    results = run_all(records, args.model, client, dry_run=args.dry_run)
    write_results(results, args.output)
    LOGGER.info("Wrote %d results to %s", len(results), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
