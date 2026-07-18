"""Rubric metadata: types, loader, and banding logic.

The rubric TOML at ``harness/rubric/tool_metadata.toml`` carries four
of the five dimensions the scorer joins with capture data. This module
turns that file into typed values and provides the banding function
the scorer uses to convert composite totals into the paper's tiers.

Design notes
------------
- The composite score is the sum of five 0-2 dimensions (0-10 range).
- Only D1 (pre-send redaction) comes from raw captures; the other
  four are static per-tool metadata reviewed for the v1.0.0 tag.
- Reading uses ``tomllib`` from the stdlib (Python 3.11+). No YAML
  dependency; the file stays diff-friendly and PR-reviewable.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

DIMENSION_MIN: Final[int] = 0
DIMENSION_MAX: Final[int] = 2
COMPOSITE_MAX: Final[int] = 10
SCHEMA_VERSION: Final[int] = 1

# Band definitions per README.md. Ranges are inclusive on both ends.
BAND_NO_PROTECTION: Final[str] = "No protection"
BAND_MINIMAL: Final[str] = "Minimal"
BAND_MODERATE: Final[str] = "Moderate"
BAND_STRONG: Final[str] = "Strong"

# Verification statuses per tool. The rubric TOML must set one per entry
# so the paper reviewer can distinguish grounded scores from placeholder
# guesses at review time.
VERIFICATION_VERIFIED: Final[str] = "verified"
VERIFICATION_PARTIAL: Final[str] = "partial"
VERIFICATION_UNVERIFIED: Final[str] = "unverified"
_VALID_VERIFICATIONS: Final[frozenset[str]] = frozenset(
    {VERIFICATION_VERIFIED, VERIFICATION_PARTIAL, VERIFICATION_UNVERIFIED}
)


@dataclass(frozen=True)
class RubricEntry:
    """One tool's static rubric metadata.

    Attributes:
        tool: Stable identifier matching ``HarnessResult.tool`` and the
            raw-capture filename ``results/raw/<tool>.json``.
        display_name: Human-readable name for CSV / paper output.
        tier: Which product tier was tested (e.g. ``api-direct``,
            ``chatgpt-free``, ``claude-pro``).
        category: One of ``Chatbot``, ``Productivity``, ``Code AI``,
            ``API direct``, ``Agentic``.
        d2_notification: User notification before send (0-2).
        d3_encryption: Transit encryption posture (0-2).
        d4_retention: Vendor retention TOS (0-2).
        d5_audit: Audit log accessibility (0-2).
        references: URL / citation per dimension. Keys ``d2`` / ``d3``
            / ``d4`` / ``d5``; kept as free-form strings so the paper
            can cite non-URL sources (empty for n/a).
        verification: ``verified`` | ``partial`` | ``unverified``.
            Signals to the paper reviewer how much of the row's cited
            claims were machine-fetched vs. taken on faith.
        last_verified: ISO date of the most recent WebFetch that
            confirmed the cited claims. Empty for unverified rows.
    """

    tool: str
    display_name: str
    tier: str
    category: str
    d2_notification: int
    d3_encryption: int
    d4_retention: int
    d5_audit: int
    references: dict[str, str] = field(default_factory=dict)
    verification: str = VERIFICATION_UNVERIFIED
    last_verified: str = ""

    def __post_init__(self) -> None:
        """Validate dimension bounds + verification status."""
        for name, value in (
            ("d2_notification", self.d2_notification),
            ("d3_encryption", self.d3_encryption),
            ("d4_retention", self.d4_retention),
            ("d5_audit", self.d5_audit),
        ):
            if not DIMENSION_MIN <= value <= DIMENSION_MAX:
                msg = (
                    f"{self.tool}.{name}={value} out of range "
                    f"[{DIMENSION_MIN}, {DIMENSION_MAX}]"
                )
                raise ValueError(msg)
        if self.verification not in _VALID_VERIFICATIONS:
            msg = (
                f"{self.tool}.verification={self.verification!r} must be one of "
                f"{sorted(_VALID_VERIFICATIONS)}"
            )
            raise ValueError(msg)


def load_rubric(path: Path) -> dict[str, RubricEntry]:
    """Parse the rubric TOML and return a ``{tool_id: entry}`` mapping.

    Args:
        path: Path to ``tool_metadata.toml``.

    Returns:
        Dict keyed by tool id, preserving file order via insertion.

    Raises:
        ValueError: schema_version mismatch, duplicate tool id, or a
            per-tool dimension out of range.
    """
    with path.open("rb") as fp:
        data = tomllib.load(fp)

    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        msg = (
            f"rubric schema_version={schema_version} does not match "
            f"expected {SCHEMA_VERSION}"
        )
        raise ValueError(msg)

    entries: dict[str, RubricEntry] = {}
    for row in data.get("tools", []):
        entry = _entry_from_dict(row)
        if entry.tool in entries:
            msg = f"duplicate tool id in rubric: {entry.tool}"
            raise ValueError(msg)
        entries[entry.tool] = entry
    return entries


def _entry_from_dict(row: dict[str, Any]) -> RubricEntry:
    """Build a RubricEntry from one ``[[tools]]`` TOML table."""
    references_raw = row.get("references", {})
    references = {str(k): str(v) for k, v in references_raw.items()}
    return RubricEntry(
        tool=str(row["tool"]),
        display_name=str(row["display_name"]),
        tier=str(row["tier"]),
        category=str(row["category"]),
        d2_notification=int(row["d2_notification"]),
        d3_encryption=int(row["d3_encryption"]),
        d4_retention=int(row["d4_retention"]),
        d5_audit=int(row["d5_audit"]),
        references=references,
        verification=str(row.get("verification", VERIFICATION_UNVERIFIED)),
        last_verified=str(row.get("last_verified", "")),
    )


def band_for_score(total: int) -> str:
    """Map a composite score (0-10) to its band label.

    Bands per README.md:
      0-2   No protection
      3-5   Minimal
      6-8   Moderate
      9-10  Strong

    Args:
        total: Sum of all five dimension scores.

    Raises:
        ValueError: When ``total`` is outside [0, 10].
    """
    if not 0 <= total <= COMPOSITE_MAX:
        msg = f"total={total} out of range [0, {COMPOSITE_MAX}]"
        raise ValueError(msg)
    if total <= 2:
        return BAND_NO_PROTECTION
    if total <= 5:
        return BAND_MINIMAL
    if total <= 8:
        return BAND_MODERATE
    return BAND_STRONG
