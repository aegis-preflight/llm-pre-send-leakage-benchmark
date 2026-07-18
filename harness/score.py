r"""Pre-Send Leakage Benchmark — 5-dimension scorer.

Reads captured harness output from ``results/raw/*.json`` (API tools)
and ``results/raw/web/<tool>/manifest.json`` (web tools), joins it
with the static rubric metadata at ``harness/rubric/tool_metadata.toml``,
and writes a per-tool composite score CSV.

Dimensions
----------
D1 pre-send redaction (computed here from captures)
D2 user notification         }
D3 transit encryption        } static per-tool metadata from the
D4 vendor retention TOS      } rubric TOML — decisions and citations
D5 audit log accessibility   } are locked at the v1.0.0 tag

Composite = D1+D2+D3+D4+D5 ∈ [0, 10], bucketed to a band label.

D1 computation
--------------
For each corpus prompt captured for a tool:

  per-prompt score = 0 if sent_verbatim=True (nothing scrubbed)
                   = 2 if sent_verbatim=False AND outbound_findings empty
                       (fully scrubbed)
                   = 1 otherwise (partial — some categories reached the
                       wire despite the tool doing something)

D1 for the tool = bucket(mean of per-prompt scores across all prompts):
  mean < 0.5       -> D1 = 0
  0.5 <= mean < 1.5 -> D1 = 1
  mean >= 1.5      -> D1 = 2

Tools present in the rubric but with no capture data yet get D1=None,
total=None, band=None in the CSV — the row still emits so paper
review knows what's outstanding.

Usage
-----
::

    uv run python -m harness.score \\
        --raw-dir results/raw/ \\
        --output results/results_v1.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from harness.rubric.rubric import (
    RubricEntry,
    band_for_score,
    load_rubric,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_RUBRIC_PATH: Final[Path] = (
    Path(__file__).parent / "rubric" / "tool_metadata.toml"
)
DEFAULT_RAW_DIR: Final[Path] = Path("results/raw")
DEFAULT_OUTPUT: Final[Path] = Path("results/results_v1.csv")

# D1 bucket thresholds — see module docstring.
D1_LOW_THRESHOLD: Final[float] = 0.5
D1_HIGH_THRESHOLD: Final[float] = 1.5

# Per-prompt D1 sub-score values.
_PROMPT_SCORE_VERBATIM: Final[int] = 0
_PROMPT_SCORE_PARTIAL: Final[int] = 1
_PROMPT_SCORE_SCRUBBED: Final[int] = 2


@dataclass(frozen=True)
class D1Result:
    """Outcome of D1 computation for one tool.

    Attributes:
        d1: Bucketed score 0-2, or None when no capture is available.
        prompts_scored: How many corpus prompts contributed. 0 means
            the tool has no capture yet.
        mean_prompt_score: Raw mean before bucketing (for CSV audit
            column). None when no prompts scored.
    """

    d1: int | None
    prompts_scored: int
    mean_prompt_score: float | None


def score_prompt(sent_verbatim: bool, outbound_findings: list[Any]) -> int:
    """Compute one prompt's D1 sub-score.

    Returns 0 for verbatim leak, 2 for fully-scrubbed, 1 for partial.
    """
    if sent_verbatim:
        return _PROMPT_SCORE_VERBATIM
    if not outbound_findings:
        return _PROMPT_SCORE_SCRUBBED
    return _PROMPT_SCORE_PARTIAL


def bucket_d1(mean_score: float) -> int:
    """Bucket a mean per-prompt D1 score into 0 / 1 / 2."""
    if mean_score < D1_LOW_THRESHOLD:
        return 0
    if mean_score < D1_HIGH_THRESHOLD:
        return 1
    return 2


def compute_d1_from_records(records: list[dict[str, Any]]) -> D1Result:
    """Compute D1 from a list of HarnessResult-shaped dicts.

    Args:
        records: One dict per corpus prompt, as loaded from
            ``results/raw/<tool>.json``. Must contain
            ``sent_verbatim`` and ``outbound_findings``.

    Returns:
        D1Result. If ``records`` is empty, returns d1=None so the
        scorer can emit an unscored row.
    """
    if not records:
        return D1Result(d1=None, prompts_scored=0, mean_prompt_score=None)
    scores = [
        score_prompt(bool(r["sent_verbatim"]), list(r.get("outbound_findings", [])))
        for r in records
    ]
    mean = sum(scores) / len(scores)
    return D1Result(
        d1=bucket_d1(mean),
        prompts_scored=len(scores),
        mean_prompt_score=mean,
    )


def load_api_capture(path: Path) -> list[dict[str, Any]]:
    """Load an API-harness output file and return its ``results`` list.

    The scorer refuses dry-run captures (``dry_run=True`` on any
    record) — those exist for offline smoke tests and should not
    reach the scored dataset. Detection is per-record; a single
    dry-run entry poisons the entire capture.

    Raises:
        ValueError: file has ``dry_run=True`` records, or ``results``
            is missing / malformed.
    """
    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    results = data.get("results")
    if not isinstance(results, list):
        msg = f"{path} has no 'results' array"
        raise ValueError(msg)
    dry_run_ids = [
        str(r.get("prompt_id", "?")) for r in results if r.get("dry_run") is True
    ]
    if dry_run_ids:
        head = ", ".join(dry_run_ids[:3])
        suffix = " (and more)" if len(dry_run_ids) > 3 else ""
        msg = (
            f"{path} contains dry-run records ({head}{suffix}); "
            "run the harness live before scoring."
        )
        raise ValueError(msg)
    return results


def load_web_manifest(path: Path) -> list[dict[str, Any]]:
    """Load a web-tool manifest and normalize to HarnessResult-ish shape.

    The manifest is a JSON list of per-prompt entries populated by hand
    per ``harness/web/README.md``. Every entry must carry
    ``sent_verbatim`` and ``outbound_findings`` — those are the two
    fields D1 depends on.
    """
    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    if isinstance(data, dict):
        data = data.get("results") or data.get("entries") or []
    if not isinstance(data, list):
        msg = f"{path} is not a JSON list or {{results: [...]}} object"
        raise ValueError(msg)
    return list(data)


def discover_captures(raw_dir: Path) -> dict[str, Path]:
    """Find every capture file under ``raw_dir`` and return ``{tool: path}``.

    API captures are ``<raw_dir>/<tool>.json`` (top-level).
    Web captures are ``<raw_dir>/web/<tool>/manifest.json``.
    Dry-run files (``<tool>.dryrun.json``) are ignored.
    """
    found: dict[str, Path] = {}
    if not raw_dir.is_dir():
        return found

    for entry in sorted(raw_dir.iterdir()):
        if entry.is_file() and entry.suffix == ".json":
            name = entry.stem
            if name.endswith(".dryrun"):
                continue
            found[name] = entry

    web_root = raw_dir / "web"
    if web_root.is_dir():
        for tool_dir in sorted(web_root.iterdir()):
            manifest = tool_dir / "manifest.json"
            if manifest.is_file():
                found[tool_dir.name] = manifest

    return found


def _emit_row(entry: RubricEntry, d1: D1Result) -> dict[str, Any]:
    """Build one CSV row from a rubric entry + its D1 result."""
    row: dict[str, Any] = {
        "tool": entry.tool,
        "display_name": entry.display_name,
        "tier": entry.tier,
        "category": entry.category,
        "d1_redaction": "" if d1.d1 is None else d1.d1,
        "d2_notification": entry.d2_notification,
        "d3_encryption": entry.d3_encryption,
        "d4_retention": entry.d4_retention,
        "d5_audit": entry.d5_audit,
    }
    if d1.d1 is None:
        row["total"] = ""
        row["band"] = ""
        row["measured"] = "false"
    else:
        total = (
            d1.d1
            + entry.d2_notification
            + entry.d3_encryption
            + entry.d4_retention
            + entry.d5_audit
        )
        row["total"] = total
        row["band"] = band_for_score(total)
        row["measured"] = "true"
    row["prompts_scored"] = d1.prompts_scored
    row["mean_prompt_score"] = (
        "" if d1.mean_prompt_score is None else f"{d1.mean_prompt_score:.3f}"
    )
    row["verification"] = entry.verification
    row["last_verified"] = entry.last_verified
    return row


CSV_HEADERS: Final[tuple[str, ...]] = (
    "tool",
    "display_name",
    "tier",
    "category",
    "d1_redaction",
    "d2_notification",
    "d3_encryption",
    "d4_retention",
    "d5_audit",
    "total",
    "band",
    "measured",
    "prompts_scored",
    "mean_prompt_score",
    "verification",
    "last_verified",
)


def score(
    rubric: dict[str, RubricEntry],
    captures: dict[str, Path],
) -> list[dict[str, Any]]:
    """Produce one row per rubric entry, joined with capture data.

    Rubric is the source of truth for row set — a capture without a
    rubric entry is logged and skipped. A rubric entry with no
    capture emits an unmeasured row.

    Returned rows are sorted: measured rows first, by ``total`` desc
    then ``tool`` asc; unmeasured rows last, by ``tool`` asc.
    """
    for tool_id in captures:
        if tool_id not in rubric:
            LOGGER.warning("Capture for %r has no rubric entry; skipping.", tool_id)

    rows: list[dict[str, Any]] = []
    for tool_id, entry in rubric.items():
        capture_path = captures.get(tool_id)
        if capture_path is None:
            d1 = D1Result(d1=None, prompts_scored=0, mean_prompt_score=None)
        else:
            records = _load_records_for(tool_id, capture_path)
            d1 = compute_d1_from_records(records)
        rows.append(_emit_row(entry, d1))

    rows.sort(
        key=lambda r: (
            0 if r["measured"] == "true" else 1,
            -int(r["total"]) if r["measured"] == "true" else 0,
            str(r["tool"]),
        )
    )
    return rows


def _load_records_for(tool_id: str, path: Path) -> list[dict[str, Any]]:
    """Dispatch on capture path shape (top-level .json vs web manifest)."""
    if path.name == "manifest.json":
        return load_web_manifest(path)
    LOGGER.info("Scoring %s from %s", tool_id, path)
    return load_api_capture(path)


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    """Write scored rows to a CSV. Parents created if missing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(CSV_HEADERS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score captured pre-send leakage benchmark results across "
            "five dimensions and emit results_v1.csv."
        ),
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help=f"Directory of raw captures (default: {DEFAULT_RAW_DIR}).",
    )
    parser.add_argument(
        "--rubric",
        type=Path,
        default=DEFAULT_RUBRIC_PATH,
        help=f"Rubric TOML path (default: {DEFAULT_RUBRIC_PATH}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT}).",
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

    rubric = load_rubric(args.rubric)
    captures = discover_captures(args.raw_dir)
    LOGGER.info(
        "Loaded rubric with %d tools; discovered %d captures in %s.",
        len(rubric),
        len(captures),
        args.raw_dir,
    )

    rows = score(rubric, captures)
    write_csv(rows, args.output)

    measured = sum(1 for r in rows if r["measured"] == "true")
    LOGGER.info(
        "Wrote %d rows (%d measured, %d unmeasured) to %s",
        len(rows),
        measured,
        len(rows) - measured,
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
