"""Tests for the 5-dimension scorer.

Covers the D1 arithmetic (per-prompt scoring + bucketing), the
join between rubric metadata and capture data, dry-run rejection,
the discover-captures walker, and the end-to-end CSV output.
"""

from __future__ import annotations

import csv
import json
from typing import TYPE_CHECKING, Any

import pytest

from harness.rubric.rubric import RubricEntry
from harness.score import (
    CSV_HEADERS,
    D1Result,
    bucket_d1,
    compute_d1_from_records,
    discover_captures,
    load_api_capture,
    main,
    score,
    score_prompt,
    write_csv,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# score_prompt — per-prompt D1 sub-score
# ---------------------------------------------------------------------------


def test_score_prompt_verbatim_leak_scores_zero() -> None:
    """Prompt reached the wire unchanged → tool did nothing."""
    assert score_prompt(sent_verbatim=True, outbound_findings=[]) == 0


def test_score_prompt_verbatim_leak_ignores_findings_length() -> None:
    """Verbatim is the dominant signal — findings would be present too."""
    assert score_prompt(sent_verbatim=True, outbound_findings=[{"type": "SSN"}]) == 0


def test_score_prompt_fully_scrubbed_scores_two() -> None:
    """Not verbatim AND no residual findings → the tool fully redacted."""
    assert score_prompt(sent_verbatim=False, outbound_findings=[]) == 2


def test_score_prompt_partial_scrub_scores_one() -> None:
    """Not verbatim but findings still present → partial redaction."""
    assert score_prompt(sent_verbatim=False, outbound_findings=[{"type": "EMAIL"}]) == 1


# ---------------------------------------------------------------------------
# bucket_d1
# ---------------------------------------------------------------------------


def test_bucket_d1_below_low_threshold_is_zero() -> None:
    assert bucket_d1(0.0) == 0
    assert bucket_d1(0.49) == 0


def test_bucket_d1_middle_range_is_one() -> None:
    assert bucket_d1(0.5) == 1
    assert bucket_d1(1.0) == 1
    assert bucket_d1(1.49) == 1


def test_bucket_d1_high_range_is_two() -> None:
    assert bucket_d1(1.5) == 2
    assert bucket_d1(2.0) == 2


# ---------------------------------------------------------------------------
# compute_d1_from_records
# ---------------------------------------------------------------------------


def _record(
    sent_verbatim: bool,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "sent_verbatim": sent_verbatim,
        "outbound_findings": findings or [],
    }


def test_compute_d1_empty_records_returns_none() -> None:
    result = compute_d1_from_records([])
    assert result == D1Result(d1=None, prompts_scored=0, mean_prompt_score=None)


def test_compute_d1_all_verbatim_bucket_zero() -> None:
    """API-direct baseline: 100 verbatim prompts → D1=0."""
    result = compute_d1_from_records([_record(sent_verbatim=True) for _ in range(10)])
    assert result.d1 == 0
    assert result.prompts_scored == 10
    assert result.mean_prompt_score == 0.0


def test_compute_d1_all_fully_scrubbed_bucket_two() -> None:
    result = compute_d1_from_records(
        [_record(sent_verbatim=False, findings=[]) for _ in range(10)]
    )
    assert result.d1 == 2
    assert result.mean_prompt_score == 2.0


def test_compute_d1_half_scrubbed_half_leaked_bucket_one() -> None:
    """Half verbatim (0) + half fully scrubbed (2) → mean 1.0 → D1=1."""
    records = [_record(sent_verbatim=True) for _ in range(5)] + [
        _record(sent_verbatim=False, findings=[]) for _ in range(5)
    ]
    result = compute_d1_from_records(records)
    assert result.d1 == 1
    assert result.mean_prompt_score == 1.0


def test_compute_d1_partial_scrubs_only_bucket_one() -> None:
    """Every prompt partial → mean 1.0 → D1=1."""
    result = compute_d1_from_records(
        [_record(sent_verbatim=False, findings=[{"type": "SSN"}]) for _ in range(10)]
    )
    assert result.d1 == 1


# ---------------------------------------------------------------------------
# load_api_capture — dry-run guard
# ---------------------------------------------------------------------------


def _write_capture(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"schema_version": 1, "count": len(results), "results": results}),
        encoding="utf-8",
    )


def test_load_api_capture_returns_results(tmp_path: Path) -> None:
    path = tmp_path / "tool.json"
    _write_capture(
        path,
        [
            {
                "prompt_id": "ident-001",
                "sent_verbatim": True,
                "outbound_findings": [],
            }
        ],
    )
    records = load_api_capture(path)
    assert len(records) == 1
    assert records[0]["prompt_id"] == "ident-001"


def test_load_api_capture_rejects_dry_run(tmp_path: Path) -> None:
    """Dry-run captures must never reach the scored dataset."""
    path = tmp_path / "tool.json"
    _write_capture(
        path,
        [
            {
                "prompt_id": "ident-001",
                "sent_verbatim": True,
                "outbound_findings": [],
                "dry_run": True,
            }
        ],
    )
    with pytest.raises(ValueError, match="dry-run"):
        load_api_capture(path)


def test_load_api_capture_rejects_missing_results(tmp_path: Path) -> None:
    path = tmp_path / "tool.json"
    path.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="no 'results' array"):
        load_api_capture(path)


# ---------------------------------------------------------------------------
# discover_captures
# ---------------------------------------------------------------------------


def test_discover_captures_finds_top_level_api_json(tmp_path: Path) -> None:
    (tmp_path / "anthropic.json").write_text("{}", encoding="utf-8")
    (tmp_path / "openai.json").write_text("{}", encoding="utf-8")
    found = discover_captures(tmp_path)
    assert set(found.keys()) == {"anthropic", "openai"}


def test_discover_captures_skips_dryrun_files(tmp_path: Path) -> None:
    (tmp_path / "anthropic.json").write_text("{}", encoding="utf-8")
    (tmp_path / "openai.dryrun.json").write_text("{}", encoding="utf-8")
    found = discover_captures(tmp_path)
    assert "openai" not in found
    assert "anthropic" in found


def test_discover_captures_finds_web_manifests(tmp_path: Path) -> None:
    web_dir = tmp_path / "web" / "chatgpt_free"
    web_dir.mkdir(parents=True)
    (web_dir / "manifest.json").write_text("[]", encoding="utf-8")
    found = discover_captures(tmp_path)
    assert "chatgpt_free" in found
    assert found["chatgpt_free"].name == "manifest.json"


def test_discover_captures_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    found = discover_captures(tmp_path / "nonexistent")
    assert found == {}


# ---------------------------------------------------------------------------
# score — join rubric with captures
# ---------------------------------------------------------------------------


def _entry(
    tool: str, d2: int = 0, d3: int = 2, d4: int = 1, d5: int = 1
) -> RubricEntry:
    return RubricEntry(
        tool=tool,
        display_name=tool.upper(),
        tier="t",
        category="C",
        d2_notification=d2,
        d3_encryption=d3,
        d4_retention=d4,
        d5_audit=d5,
    )


def test_score_unmeasured_row_when_no_capture(tmp_path: Path) -> None:
    rubric = {"anthropic": _entry("anthropic")}
    rows = score(rubric, captures={})
    assert len(rows) == 1
    row = rows[0]
    assert row["tool"] == "anthropic"
    assert row["measured"] == "false"
    assert row["d1_redaction"] == ""
    assert row["total"] == ""
    assert row["band"] == ""


def test_score_measured_row_computes_total_and_band(tmp_path: Path) -> None:
    """API-direct pattern: D1=0 (verbatim) + D2=0 + D3=2 + D4=1 + D5=1 = 4 → Minimal."""
    capture = tmp_path / "anthropic.json"
    _write_capture(capture, [_record(sent_verbatim=True) for _ in range(5)])
    rubric = {"anthropic": _entry("anthropic", d2=0, d3=2, d4=1, d5=1)}
    rows = score(rubric, {"anthropic": capture})
    row = rows[0]
    assert row["measured"] == "true"
    assert row["d1_redaction"] == 0
    assert row["total"] == 4
    assert row["band"] == "Minimal"


def test_score_orders_measured_before_unmeasured(tmp_path: Path) -> None:
    capture = tmp_path / "anthropic.json"
    _write_capture(capture, [_record(sent_verbatim=True)])
    rubric = {
        "gemini": _entry("gemini"),  # unmeasured
        "anthropic": _entry("anthropic"),  # measured
    }
    rows = score(rubric, {"anthropic": capture})
    # Measured row is first even though gemini precedes anthropic in the dict.
    assert rows[0]["tool"] == "anthropic"
    assert rows[1]["tool"] == "gemini"


def test_score_orders_measured_by_total_desc(tmp_path: Path) -> None:
    """Two measured tools: higher composite score comes first."""
    low_cap = tmp_path / "low.json"
    _write_capture(low_cap, [_record(sent_verbatim=True)])  # D1=0
    high_cap = tmp_path / "high.json"
    _write_capture(high_cap, [_record(sent_verbatim=False, findings=[])])  # D1=2

    rubric = {
        "low": _entry("low", d2=0, d3=2, d4=1, d5=1),  # 0+0+2+1+1 = 4
        "high": _entry("high", d2=0, d3=2, d4=1, d5=1),  # 2+0+2+1+1 = 6
    }
    rows = score(rubric, {"low": low_cap, "high": high_cap})
    assert [r["tool"] for r in rows] == ["high", "low"]


def test_score_ignores_captures_not_in_rubric(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    unknown = tmp_path / "unknown_tool.json"
    _write_capture(unknown, [_record(sent_verbatim=True)])
    rubric = {"anthropic": _entry("anthropic")}
    rows = score(rubric, {"unknown_tool": unknown})
    # Only the rubric-listed tool emits a row.
    assert [r["tool"] for r in rows] == ["anthropic"]
    assert any(
        "unknown_tool" in rec.message and "no rubric" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# write_csv + end-to-end via main()
# ---------------------------------------------------------------------------


def test_write_csv_emits_expected_headers(tmp_path: Path) -> None:
    out = tmp_path / "results.csv"
    write_csv([dict.fromkeys(CSV_HEADERS, "")], out)
    with out.open(encoding="utf-8", newline="") as fp:
        header_row = next(csv.reader(fp))
    assert tuple(header_row) == CSV_HEADERS


def test_write_csv_creates_parent_dir(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "results.csv"
    write_csv([], out)
    assert out.is_file()


def test_main_end_to_end_produces_csv(tmp_path: Path) -> None:
    """CLI: bundled rubric + one API capture + full run to CSV."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_capture(
        raw_dir / "anthropic.json",
        [_record(sent_verbatim=True) for _ in range(3)],
    )
    output = tmp_path / "results.csv"

    exit_code = main(
        [
            "--raw-dir",
            str(raw_dir),
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.is_file()

    with output.open(encoding="utf-8", newline="") as fp:
        rows = list(csv.DictReader(fp))

    anthropic = next(r for r in rows if r["tool"] == "anthropic")
    assert anthropic["measured"] == "true"
    # Every other tool in the rubric is unmeasured.
    unmeasured = [r for r in rows if r["measured"] == "false"]
    assert len(unmeasured) == len(rows) - 1
