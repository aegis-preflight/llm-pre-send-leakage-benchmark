r"""Pre-Send Leakage Benchmark — OpenAI API-direct harness.

Companion to ``harness/api/anthropic.py``. Same shape, same output
schema, same design rationale: API-direct is the ""zero pre-send
protection"" baseline against which wrapper tools, IDE assistants, and
web chatbots are compared.

The OpenAI SDK forwards the ``messages[0].content`` field unchanged in
the HTTP body of ``POST /v1/chat/completions``. By construction
``sent_verbatim`` will be True for every corpus prompt in this tier.

Usage
-----
::

    # Real run against OpenAI.
    export OPENAI_API_KEY=sk-...
    uv run python harness/api/openai.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output results/raw/openai.json

    # Offline smoke test (no API key needed).
    uv run python harness/api/openai.py \\
        --corpus corpus/corpus_v1.jsonl \\
        --output /tmp/openai-dryrun.json \\
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

TOOL_NAME: Final[str] = "openai"
TIER: Final[str] = "api-direct"
# gpt-4o is the current stable general-purpose OpenAI chat model as of
# the v1.0 benchmark run (2026-07). Overridable via ``--model``.
DEFAULT_MODEL: Final[str] = "gpt-4o"
DEFAULT_MAX_TOKENS: Final[int] = 256
API_KEY_ENV: Final[str] = "OPENAI_API_KEY"


def build_request_payload(prompt_text: str, model: str) -> dict[str, Any]:
    """Reconstruct the JSON body sent to ``POST /v1/chat/completions``.

    The OpenAI SDK produces this exact shape as the HTTP body. Building
    it here lets ``--dry-run`` capture identical bytes without a network
    call, and keeps the harness independent of internal SDK details.

    Args:
        prompt_text: The corpus prompt as-is.
        model: Model identifier to include.

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
        response = client.chat.completions.create(**payload)
    except Exception as exc:
        LOGGER.warning("OpenAI call failed for %s: %s", record.id, exc)
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
    """Pull assistant text out of a ChatCompletion response.

    Shape: ``response.choices[0].message.content``. Non-text
    modalities (function calls, tool calls) are ignored — the
    benchmark only tests text prompts and only scores text responses.
    """
    parts: list[str] = []
    for choice in getattr(response, "choices", []) or []:
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            parts.append(content)
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
    """Import and construct an OpenAI client (deferred so --dry-run works)."""
    try:
        import openai
    except ImportError as exc:  # pragma: no cover - environment error
        msg = (
            "The openai SDK is not installed. Install it with "
            "`uv sync --extra harness-openai` or run with --dry-run."
        )
        raise RuntimeError(msg) from exc
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        msg = f"{API_KEY_ENV} must be set for a live run (or pass --dry-run)."
        raise RuntimeError(msg)
    return openai.OpenAI(api_key=api_key)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Pre-Send Leakage Benchmark against the OpenAI "
            "Chat Completions API (api-direct tier)."
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
