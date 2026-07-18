"""Shared building blocks for API-direct harnesses.

Every ``harness/api/<vendor>.py`` reads the same corpus, produces the
same ``HarnessResult`` shape, and writes to the same JSON layout. This
module owns those shared pieces so the vendor-specific files stay
focused on the vendor's SDK.

Nothing here is vendor-specific. ``harness/api/anthropic.py``,
``.../openai.py``, ``.../bedrock.py``, and ``.../azure_openai.py`` all
import from this module.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from harness.detect import Finding, detect

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@dataclass(frozen=True)
class CorpusRecord:
    """Corpus entry as seen by a harness.

    Mirrors ``corpus.generate.CorpusRecord`` but with a JSONL-loader
    tolerant to future field additions (unknown keys are ignored). The
    canonical dataclass in ``corpus.generate`` is generation-side; this
    one is read-side.
    """

    id: str
    category: str
    subcategory: str
    prompt_text: str
    expected_categories: list[str]
    expected_count: dict[str, int]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusRecord:
        """Build a CorpusRecord from a parsed JSONL line.

        Unknown keys (e.g. ``aegis_detect``, ``notes``) are dropped —
        the harness does not need them.
        """
        return cls(
            id=str(data["id"]),
            category=str(data["category"]),
            subcategory=str(data["subcategory"]),
            prompt_text=str(data["prompt_text"]),
            expected_categories=list(data["expected_categories"]),
            expected_count=dict(data["expected_count"]),
        )


def load_corpus(path: Path) -> list[CorpusRecord]:
    """Parse a JSONL corpus file into records.

    Blank lines are skipped. Any malformed line raises immediately with
    the offending line number — corrupt corpus should fail loud.
    """
    records: list[CorpusRecord] = []
    with path.open(encoding="utf-8") as fp:
        for lineno, raw in enumerate(fp, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"Invalid JSON on {path}:{lineno}: {exc}"
                raise ValueError(msg) from exc
            records.append(CorpusRecord.from_dict(data))
    return records


@dataclass(frozen=True)
class HarnessResult:
    """One captured API call: request payload, response, and outbound findings.

    A benchmark run for a given tool produces one HarnessResult per
    corpus prompt.

    Attributes:
        prompt_id: The corpus record id being tested.
        tool: Vendor identifier, e.g. ``anthropic``, ``openai``.
        tier: Which product tier was tested (``api-direct``,
            ``chatgpt-free``, ...). Locked at run time.
        model: Model identifier as sent to the vendor. Empty string for
            web-tool captures where the model is opaque.
        timestamp_utc: ISO-8601 timestamp of the request, second-precision.
        request_payload: The exact JSON body that left the client. This
            is the "wire payload" — what actually reached the vendor.
        response_text: The vendor's response text. Empty on dry-run or
            error. Not scored by the benchmark, but recorded so the
            paper can qualitatively cite behavior (e.g. "GPT-4o echoed
            the SSN back verbatim in its reply").
        outbound_findings: Findings from ``harness.detect.detect`` run
            over ``request_payload``.
        sent_verbatim: True iff every category present in the corpus
            prompt is also present in ``request_payload``. False means
            *something* was redacted or transformed before the wire.
        dry_run: True if this record was produced without calling the
            vendor's API. Payload shape is populated; ``response_text``
            is empty. Used to smoke-test the harness offline.
        error: Populated when the vendor call raised. ``response_text``
            will be empty; ``request_payload`` is still captured because
            the point of the benchmark is to record what *would have
            left the client* even if the vendor rejected it.
    """

    prompt_id: str
    tool: str
    tier: str
    model: str
    timestamp_utc: str
    request_payload: dict[str, Any]
    response_text: str
    outbound_findings: list[Finding]
    sent_verbatim: bool
    dry_run: bool = False
    error: str = ""


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 second-precision string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_sent_verbatim(
    prompt_text: str,
    request_payload: dict[str, Any],
    corpus_categories: list[str],
) -> tuple[bool, list[Finding]]:
    """Compare corpus expectations against the outbound payload.

    Returns ``(sent_verbatim, outbound_findings)``.

    ``sent_verbatim`` is True iff:

    1. The prompt text appears somewhere in the payload as a substring, OR
    2. Every category label the corpus expected is also present in the
       findings from running the detector over the payload.

    Substring match covers the common case (SDK forwards the prompt
    unchanged as one of the ``messages`` items). The category check is
    a fallback for cases where the client normalizes whitespace or
    encoding — the prompt no longer matches character-for-character but
    every category of PII still leaks.

    Args:
        prompt_text: The corpus prompt as it went into the harness.
        request_payload: The JSON body the SDK produced.
        corpus_categories: ``expected_categories`` from the corpus record.

    Returns:
        Tuple of (sent_verbatim, outbound_findings). Findings are the
        raw output of the detector — kept so callers don't have to
        re-run detection.
    """
    payload_str = json.dumps(request_payload, sort_keys=True)
    findings = detect(payload_str)

    # Substring match walks the payload's string values directly rather
    # than comparing against JSON-serialized bytes, so unicode escaping
    # (e.g. em-dash → —) does not spuriously mark a prompt as
    # non-verbatim. Every string value in the payload dict is checked.
    for value in _iter_string_values(request_payload):
        if prompt_text in value:
            return True, findings

    found_categories = {f.type for f in findings}
    if corpus_categories and set(corpus_categories).issubset(found_categories):
        return True, findings

    return False, findings


def _iter_string_values(node: Any) -> Iterator[str]:
    """Yield every string value reachable from a JSON-ish structure."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_string_values(v)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_string_values(item)


def write_results(results: list[HarnessResult], output_path: Path) -> None:
    """Write results to disk as pretty JSON.

    Writes to a ``.tmp`` sibling and renames atomically so a partial
    write never leaves a truncated file at ``output_path``. Parent
    directories are created if missing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    serializable = [_result_to_dict(r) for r in results]
    with tmp_path.open("w", encoding="utf-8") as fp:
        json.dump(
            {
                "schema_version": 1,
                "generated_at_utc": utc_now_iso(),
                "count": len(results),
                "results": serializable,
            },
            fp,
            indent=2,
            sort_keys=True,
        )
        fp.write("\n")
    tmp_path.replace(output_path)


def _result_to_dict(result: HarnessResult) -> dict[str, Any]:
    """Convert HarnessResult (with dataclass Finding children) to plain dict."""
    data = asdict(result)
    data["outbound_findings"] = [asdict(f) for f in result.outbound_findings]
    return data
