r"""Pre-Send Leakage Benchmark — Anthropic API-direct harness.

Reads the locked corpus, sends each prompt to the Anthropic Messages
API, and records exactly what was on the wire alongside what came back.
Output feeds the scorer in a later PR.

The Anthropic tier tested here is ``api-direct`` — no wrapper client,
no proxy, no client-side redaction library. This is the baseline every
other tool is compared against. By construction it will always show
``sent_verbatim=True`` for every prompt, because the SDK forwards the
prompt content unchanged as the ``messages[0].content`` field. The
value of running it is establishing the ground truth: this is what
"zero pre-send protection" looks like on the wire.

Usage
-----
::

    # Real run against Anthropic.
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run python harness/api/anthropic.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output results/raw/anthropic.json

    # Offline smoke test (no API key needed, no network).
    uv run python harness/api/anthropic.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output /tmp/anthropic-dryrun.json \\
        --dry-run --limit 3
"""

from __future__ import annotations

import argparse
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

TOOL_NAME: Final[str] = "anthropic"
TIER: Final[str] = "api-direct"
# Sonnet 4.6 is the current stable general-purpose model as of the v1.0
# benchmark run (2026-07). Overridable via ``--model`` for reruns
# against a different snapshot.
DEFAULT_MODEL: Final[str] = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS: Final[int] = 256
API_KEY_ENV: Final[str] = "ANTHROPIC_API_KEY"


def build_request_payload(prompt_text: str, model: str) -> dict[str, Any]:
    """Reconstruct the JSON body the Anthropic SDK sends over the wire.

    This is the exact shape ``client.messages.create`` serializes as the
    HTTP body. Building it locally (rather than intercepting the httpx
    request) keeps the harness independent of Anthropic SDK internals
    and lets ``--dry-run`` produce the same payload without a network
    call. The paper documents that this payload is what the benchmark
    inspects for the pre-send-redaction dimension.

    Args:
        prompt_text: The corpus prompt as-is. This is the string the
            benchmark is asking about — does it reach the vendor?
        model: Model identifier to include in the payload.

    Returns:
        Serializable dict equivalent to the HTTP request body.
    """
    return {
        "model": model,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": prompt_text,
            }
        ],
    }


def run_single(
    record: CorpusRecord,
    model: str,
    client: Any | None,
    *,
    dry_run: bool,
) -> HarnessResult:
    """Run one corpus prompt through the harness.

    Args:
        record: Corpus entry to submit.
        model: Model identifier used in the request payload.
        client: An ``anthropic.Anthropic`` client, or None on dry-run.
        dry_run: When True, skip the vendor call and return a result
            with an empty ``response_text``. Payload capture and the
            outbound-findings detector still run — that path is
            testable offline.

    Returns:
        HarnessResult with request payload captured and outbound
        findings computed.
    """
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
        # Unreachable under normal use; guarded to keep mypy happy.
        msg = "client is required when dry_run=False"
        raise RuntimeError(msg)

    try:
        response = client.messages.create(**payload)
    except Exception as exc:
        LOGGER.warning("Anthropic call failed for %s: %s", record.id, exc)
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
    """Pull the text content out of an Anthropic Messages response.

    The response object exposes a ``content`` list of blocks; text
    blocks have a ``text`` attribute. Blocks of other types (tool
    calls, images) are ignored — the benchmark tests text prompts and
    only the text response is scored.
    """
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
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
    """Run every record through ``run_single`` and return the results.

    Ordering matches the input order so downstream tooling can zip the
    output back to the corpus file for per-prompt inspection.
    """
    results: list[HarnessResult] = []
    for record in records:
        LOGGER.info(
            "Testing %s (%s/%s)", record.id, record.category, record.subcategory
        )
        results.append(run_single(record, model, client, dry_run=dry_run))
    return results


def _build_client() -> Any:
    """Import and construct an Anthropic client.

    Import is deferred so ``--dry-run`` works without the SDK installed
    (the benchmark repo depends on ``anthropic`` only under the
    ``harness-anthropic`` extra).
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - environment error
        msg = (
            "The anthropic SDK is not installed. Install it with "
            "`uv sync --extra harness-anthropic` or run with --dry-run."
        )
        raise RuntimeError(msg) from exc
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        msg = f"{API_KEY_ENV} must be set for a live run (or pass --dry-run)."
        raise RuntimeError(msg)
    return anthropic.Anthropic(api_key=api_key)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Pre-Send Leakage Benchmark against the Anthropic "
            "Messages API (api-direct tier)."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Path to a corpus JSONL file (e.g. corpus/corpus_v1.jsonl).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the results JSON (parents created if missing).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Model identifier (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N records. Omit to run the full corpus.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Do not call the Anthropic API. Payload capture still runs "
            "so the harness can be smoke-tested offline."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
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
