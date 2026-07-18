r"""Pre-Send Leakage Benchmark — Azure OpenAI API-direct harness.

Azure OpenAI is a rebranded, tenant-scoped OpenAI. The SDK is
``openai.AzureOpenAI`` and the wire format is identical to native
OpenAI: same ``messages`` shape, same response shape, same
``sent_verbatim=True`` outcome by construction.

The one meaningful difference is the ``model`` argument. In Azure
OpenAI it is the *deployment name* the tenant chose — a
customer-scoped string, not a public model id. The harness accepts
that value via ``--model`` or the ``AZURE_OPENAI_DEPLOYMENT``
environment variable.

Usage
-----
::

    # Real run.
    export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com"
    export AZURE_OPENAI_API_KEY="..."
    export AZURE_OPENAI_DEPLOYMENT="my-gpt-4o-deployment"
    # AZURE_OPENAI_API_VERSION is optional; defaults to 2024-10-21.
    uv run python -m harness.api.azure_openai \\
        --corpus corpus/corpus_v1.jsonl \\
        --output results/raw/azure_openai.json

    # Offline smoke test.
    uv run python -m harness.api.azure_openai \\
        --corpus corpus/corpus_v1.jsonl \\
        --output /tmp/azure-dryrun.json \\
        --dry-run --limit 3 --model my-deployment
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

TOOL_NAME: Final[str] = "azure_openai"
TIER: Final[str] = "api-direct"
DEFAULT_MAX_TOKENS: Final[int] = 256
API_KEY_ENV: Final[str] = "AZURE_OPENAI_API_KEY"
ENDPOINT_ENV: Final[str] = "AZURE_OPENAI_ENDPOINT"
DEPLOYMENT_ENV: Final[str] = "AZURE_OPENAI_DEPLOYMENT"
API_VERSION_ENV: Final[str] = "AZURE_OPENAI_API_VERSION"
# Sticks to a widely available API version. Overridable via the env var
# above for tenants pinned to a specific preview.
DEFAULT_API_VERSION: Final[str] = "2024-10-21"


def build_request_payload(prompt_text: str, deployment: str) -> dict[str, Any]:
    """Reconstruct the JSON body sent to the Azure OpenAI chat endpoint.

    Identical shape to native OpenAI. ``deployment`` is the customer-
    scoped deployment name — Azure looks up the underlying model
    server-side.

    Args:
        prompt_text: The corpus prompt.
        deployment: Azure deployment name for this call.

    Returns:
        Serializable dict equivalent to the HTTP request body.
    """
    return {
        "model": deployment,
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
    deployment: str,
    client: Any | None,
    *,
    dry_run: bool,
) -> HarnessResult:
    """Run one corpus prompt through the harness."""
    payload = build_request_payload(record.prompt_text, deployment)
    sent_verbatim, findings = compute_sent_verbatim(
        record.prompt_text, payload, record.expected_categories
    )
    timestamp = utc_now_iso()

    if dry_run:
        return HarnessResult(
            prompt_id=record.id,
            tool=TOOL_NAME,
            tier=TIER,
            model=deployment,
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
        LOGGER.warning("Azure OpenAI call failed for %s: %s", record.id, exc)
        return HarnessResult(
            prompt_id=record.id,
            tool=TOOL_NAME,
            tier=TIER,
            model=deployment,
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
        model=deployment,
        timestamp_utc=timestamp,
        request_payload=payload,
        response_text=response_text,
        outbound_findings=findings,
        sent_verbatim=sent_verbatim,
    )


def _extract_response_text(response: Any) -> str:
    """Pull assistant text from an Azure OpenAI ChatCompletion (same as OpenAI)."""
    parts: list[str] = []
    for choice in getattr(response, "choices", []) or []:
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            parts.append(content)
    return "".join(parts)


def run_all(
    records: Iterable[CorpusRecord],
    deployment: str,
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
        results.append(run_single(record, deployment, client, dry_run=dry_run))
    return results


def _build_client() -> Any:
    """Import and construct an AzureOpenAI client (deferred)."""
    try:
        import openai
    except ImportError as exc:  # pragma: no cover - environment error
        msg = (
            "The openai SDK is not installed. Install it with "
            "`uv sync --extra harness-azure` or run with --dry-run."
        )
        raise RuntimeError(msg) from exc

    api_key = os.environ.get(API_KEY_ENV)
    endpoint = os.environ.get(ENDPOINT_ENV)
    api_version = os.environ.get(API_VERSION_ENV, DEFAULT_API_VERSION)
    missing: list[str] = []
    if not api_key:
        missing.append(API_KEY_ENV)
    if not endpoint:
        missing.append(ENDPOINT_ENV)
    if missing:
        msg = f"{', '.join(missing)} must be set for a live run (or pass --dry-run)."
        raise RuntimeError(msg)
    # Both variables are validated non-empty above — asserts placate mypy
    # without adding runtime overhead in the happy path.
    assert api_key is not None  # noqa: S101
    assert endpoint is not None  # noqa: S101
    return openai.AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Pre-Send Leakage Benchmark against the Azure "
            "OpenAI chat completions API (api-direct tier)."
        ),
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            f"Azure deployment name. Falls back to ${DEPLOYMENT_ENV} "
            "env var if omitted."
        ),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _resolve_deployment(args: argparse.Namespace) -> str:
    """Deployment resolution: --model wins over env var; either must be set."""
    if args.model:
        return str(args.model)
    env_value = os.environ.get(DEPLOYMENT_ENV)
    if env_value:
        return env_value
    msg = (
        f"Deployment name required. Pass --model <deployment> or set ${DEPLOYMENT_ENV}."
    )
    raise RuntimeError(msg)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    deployment = _resolve_deployment(args)
    records = load_corpus(args.corpus)
    if args.limit is not None:
        records = records[: args.limit]
    LOGGER.info("Loaded %d records from %s", len(records), args.corpus)

    client = None if args.dry_run else _build_client()
    if args.dry_run:
        LOGGER.info("Dry-run mode: no API calls will be made.")

    results = run_all(records, deployment, client, dry_run=args.dry_run)
    write_results(results, args.output)
    LOGGER.info("Wrote %d results to %s", len(results), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
