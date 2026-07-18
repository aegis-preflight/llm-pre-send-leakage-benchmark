"""Tests for the rubric loader and banding logic.

The rubric TOML is the source of truth for four of the five scoring
dimensions. A bug here silently miscore-s every tool in the paper,
so contract tests cover both the shape guarantees and the banding
edges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from harness.rubric.rubric import (
    BAND_MINIMAL,
    BAND_MODERATE,
    BAND_NO_PROTECTION,
    BAND_STRONG,
    RubricEntry,
    band_for_score,
    load_rubric,
)

if TYPE_CHECKING:
    from pathlib import Path


def _repo_root() -> Path:
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# banding logic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("total", [0, 1, 2])
def test_band_no_protection_covers_zero_to_two(total: int) -> None:
    assert band_for_score(total) == BAND_NO_PROTECTION


@pytest.mark.parametrize("total", [3, 4, 5])
def test_band_minimal_covers_three_to_five(total: int) -> None:
    assert band_for_score(total) == BAND_MINIMAL


@pytest.mark.parametrize("total", [6, 7, 8])
def test_band_moderate_covers_six_to_eight(total: int) -> None:
    assert band_for_score(total) == BAND_MODERATE


@pytest.mark.parametrize("total", [9, 10])
def test_band_strong_covers_nine_to_ten(total: int) -> None:
    assert band_for_score(total) == BAND_STRONG


def test_band_rejects_negative() -> None:
    with pytest.raises(ValueError, match="out of range"):
        band_for_score(-1)


def test_band_rejects_over_max() -> None:
    with pytest.raises(ValueError, match="out of range"):
        band_for_score(11)


# ---------------------------------------------------------------------------
# RubricEntry validation
# ---------------------------------------------------------------------------


def test_rubric_entry_accepts_valid_dimensions() -> None:
    entry = RubricEntry(
        tool="x",
        display_name="X",
        tier="t",
        category="C",
        d2_notification=0,
        d3_encryption=2,
        d4_retention=1,
        d5_audit=0,
    )
    assert entry.tool == "x"


def test_rubric_entry_rejects_out_of_range_dimension() -> None:
    with pytest.raises(ValueError, match="d3_encryption=3"):
        RubricEntry(
            tool="x",
            display_name="X",
            tier="t",
            category="C",
            d2_notification=0,
            d3_encryption=3,
            d4_retention=1,
            d5_audit=0,
        )


def test_rubric_entry_rejects_negative_dimension() -> None:
    with pytest.raises(ValueError, match="d2_notification=-1"):
        RubricEntry(
            tool="x",
            display_name="X",
            tier="t",
            category="C",
            d2_notification=-1,
            d3_encryption=2,
            d4_retention=1,
            d5_audit=0,
        )


# ---------------------------------------------------------------------------
# load_rubric — bundled TOML must load without errors
# ---------------------------------------------------------------------------


def test_bundled_rubric_loads() -> None:
    path = _repo_root() / "harness" / "rubric" / "tool_metadata.toml"
    entries = load_rubric(path)
    assert entries, "bundled rubric is empty"


def test_bundled_rubric_covers_all_four_api_direct_tools() -> None:
    """API-direct rubric must include every vendor harness we built."""
    path = _repo_root() / "harness" / "rubric" / "tool_metadata.toml"
    entries = load_rubric(path)
    for expected in ("anthropic", "openai", "bedrock", "azure_openai"):
        assert expected in entries, f"rubric missing api-direct tool: {expected}"


def test_bundled_rubric_has_twenty_tools() -> None:
    """Paper commits to 20 tools at v1.0.0."""
    path = _repo_root() / "harness" / "rubric" / "tool_metadata.toml"
    entries = load_rubric(path)
    assert len(entries) == 20, f"expected 20 tools, got {len(entries)}"


def test_bundled_rubric_every_entry_has_references() -> None:
    """Every static dimension needs a citation for the paper's methodology."""
    path = _repo_root() / "harness" / "rubric" / "tool_metadata.toml"
    entries = load_rubric(path)
    for tool_id, entry in entries.items():
        for dim in ("d2", "d3", "d4", "d5"):
            assert dim in entry.references, f"{tool_id}: missing reference for {dim}"


# ---------------------------------------------------------------------------
# load_rubric — synthetic error cases
# ---------------------------------------------------------------------------


def _write_toml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_load_rejects_wrong_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "r.toml"
    _write_toml(
        path,
        """
schema_version = 99

[[tools]]
tool = "x"
display_name = "X"
tier = "t"
category = "C"
d2_notification = 0
d3_encryption = 2
d4_retention = 1
d5_audit = 0
""",
    )
    with pytest.raises(ValueError, match="schema_version"):
        load_rubric(path)


def test_load_rejects_duplicate_tool_id(tmp_path: Path) -> None:
    path = tmp_path / "r.toml"
    _write_toml(
        path,
        """
schema_version = 1

[[tools]]
tool = "x"
display_name = "X1"
tier = "t"
category = "C"
d2_notification = 0
d3_encryption = 2
d4_retention = 1
d5_audit = 0

[[tools]]
tool = "x"
display_name = "X2"
tier = "t"
category = "C"
d2_notification = 0
d3_encryption = 2
d4_retention = 1
d5_audit = 0
""",
    )
    with pytest.raises(ValueError, match="duplicate tool id"):
        load_rubric(path)


def test_load_propagates_dimension_out_of_range(tmp_path: Path) -> None:
    path = tmp_path / "r.toml"
    _write_toml(
        path,
        """
schema_version = 1

[[tools]]
tool = "x"
display_name = "X"
tier = "t"
category = "C"
d2_notification = 0
d3_encryption = 5
d4_retention = 1
d5_audit = 0
""",
    )
    with pytest.raises(ValueError, match="d3_encryption=5"):
        load_rubric(path)


def test_load_populates_references_dict(tmp_path: Path) -> None:
    path = tmp_path / "r.toml"
    _write_toml(
        path,
        """
schema_version = 1

[[tools]]
tool = "x"
display_name = "X"
tier = "t"
category = "C"
d2_notification = 0
d3_encryption = 2
d4_retention = 1
d5_audit = 0

[tools.references]
d2 = "n/a"
d3 = "https://example.com/tls"
d4 = "https://example.com/retention"
d5 = "https://example.com/audit"
""",
    )
    entries = load_rubric(path)
    assert entries["x"].references == {
        "d2": "n/a",
        "d3": "https://example.com/tls",
        "d4": "https://example.com/retention",
        "d5": "https://example.com/audit",
    }
