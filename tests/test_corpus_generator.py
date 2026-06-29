"""Tests for the corpus generator.

These verify the contract that downstream PRs (harness, scorer, paper)
depend on: a deterministic, schema-conformant, 100-record JSONL corpus.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING

import pytest

from corpus.generate import (
    CATEGORY_DISTRIBUTION,
    DEFAULT_SEED,
    EXPECTED_RECORD_COUNT,
    CorpusRecord,
    build_corpus,
    write_jsonl,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def corpus() -> list[CorpusRecord]:
    """Build the canonical corpus once per test module."""
    return build_corpus(seed=DEFAULT_SEED)


# ---------------------------------------------------------------------------
# Contract: shape and integrity
# ---------------------------------------------------------------------------


def test_corpus_has_exactly_100_records(corpus: list[CorpusRecord]) -> None:
    assert len(corpus) == EXPECTED_RECORD_COUNT


def test_all_ids_unique(corpus: list[CorpusRecord]) -> None:
    ids = [r.id for r in corpus]
    assert len(set(ids)) == len(ids), (
        f"Duplicate ids: {sorted({i for i in ids if ids.count(i) > 1})}"
    )


def test_id_format_is_prefix_index(corpus: list[CorpusRecord]) -> None:
    """Every id matches ``<prefix>-<3-digit-index>``."""
    for record in corpus:
        parts = record.id.split("-")
        assert len(parts) >= 2, f"Bad id format: {record.id}"
        assert parts[-1].isdigit(), f"Index not numeric: {record.id}"
        assert len(parts[-1]) == 3, f"Index not 3-digit zero-padded: {record.id}"


def test_category_distribution_matches_spec(corpus: list[CorpusRecord]) -> None:
    counts = Counter(r.category for r in corpus)
    for category, expected_count in CATEGORY_DISTRIBUTION.items():
        assert counts[category] == expected_count, (
            f"{category}: expected {expected_count}, got {counts[category]}"
        )


def test_every_category_is_present(corpus: list[CorpusRecord]) -> None:
    categories = {r.category for r in corpus}
    assert categories == set(CATEGORY_DISTRIBUTION.keys())


# ---------------------------------------------------------------------------
# Contract: per-record schema
# ---------------------------------------------------------------------------


def test_required_fields_populated(corpus: list[CorpusRecord]) -> None:
    """Every record has non-empty required fields."""
    for r in corpus:
        assert r.id
        assert r.category
        assert r.subcategory
        assert r.prompt_text
        assert r.expected_categories
        assert r.expected_count


def test_expected_count_keys_match_categories(corpus: list[CorpusRecord]) -> None:
    """The keys of expected_count exactly match expected_categories."""
    for r in corpus:
        assert set(r.expected_count.keys()) == set(r.expected_categories), (
            f"{r.id}: count keys {set(r.expected_count)} != "
            f"expected_categories {set(r.expected_categories)}"
        )


def test_expected_count_values_are_positive(corpus: list[CorpusRecord]) -> None:
    for r in corpus:
        for category, count in r.expected_count.items():
            assert count >= 1, f"{r.id}: {category} count is {count}"


def test_prompt_text_is_meaningful(corpus: list[CorpusRecord]) -> None:
    """Prompts read like natural user input — not just raw PII dumps."""
    for r in corpus:
        # Heuristic: at least 5 words, ends with punctuation or has spaces.
        assert len(r.prompt_text.split()) >= 5, (
            f"{r.id}: prompt too short ({r.prompt_text!r})"
        )


# ---------------------------------------------------------------------------
# Contract: determinism
# ---------------------------------------------------------------------------


def test_same_seed_produces_same_corpus() -> None:
    """Two builds with the same seed produce identical CorpusRecord lists."""
    a = build_corpus(seed=DEFAULT_SEED)
    b = build_corpus(seed=DEFAULT_SEED)
    assert a == b


def test_different_seed_produces_different_corpus() -> None:
    """Confirm the seed actually drives the randomness, not a hidden constant."""
    a = build_corpus(seed=DEFAULT_SEED)
    b = build_corpus(seed=DEFAULT_SEED + 1)
    # Ids stay stable (they're a function of category and index, not seed),
    # but prompt_text must differ for at least most records.
    differing = sum(
        1 for ra, rb in zip(a, b, strict=True) if ra.prompt_text != rb.prompt_text
    )
    # At least 80% of prompts should differ — names, addresses, etc. all reseed.
    assert differing >= 80, f"Only {differing}/100 prompts differed under reseed"


def test_jsonl_serialization_is_deterministic(tmp_path: Path) -> None:
    """Two write_jsonl calls produce byte-identical files."""
    records = build_corpus(seed=DEFAULT_SEED)
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    write_jsonl(records, path_a)
    write_jsonl(records, path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


# ---------------------------------------------------------------------------
# Contract: JSONL output is valid
# ---------------------------------------------------------------------------


def test_jsonl_lines_parse(tmp_path: Path) -> None:
    """Every line of the output is valid JSON with the expected shape."""
    records = build_corpus(seed=DEFAULT_SEED)
    out = tmp_path / "corpus.jsonl"
    write_jsonl(records, out)

    parsed: list[dict[str, object]] = []
    with out.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                parsed.append(json.loads(line))

    assert len(parsed) == EXPECTED_RECORD_COUNT
    for record in parsed:
        for required_field in (
            "id",
            "category",
            "subcategory",
            "prompt_text",
            "expected_categories",
            "expected_count",
            "aegis_detect",
            "notes",
        ):
            assert required_field in record, f"Missing field: {required_field}"


def test_jsonl_uses_lf_line_endings(tmp_path: Path) -> None:
    """Output uses LF line endings (cross-platform consistency)."""
    records = build_corpus(seed=DEFAULT_SEED)
    out = tmp_path / "corpus.jsonl"
    write_jsonl(records, out)
    raw = out.read_bytes()
    assert b"\r\n" not in raw, "Output contains CRLF line endings"


# ---------------------------------------------------------------------------
# Safety: no real PII patterns
# ---------------------------------------------------------------------------


def test_no_obviously_real_test_strings(corpus: list[CorpusRecord]) -> None:
    """Corpus does not contain canonical test strings that signal real PII.

    These are well-known canary values that would appear if a developer
    accidentally pasted real test data from production logs or staging.
    Synthetic Faker output should never produce these exact strings.
    """
    canaries = [
        "078-05-1120",  # historical "Woolworth" SSN used in countless examples
        "999-99-9999",
        "4111-1111-1111-1111",  # canonical test CC
        "test@test.com",
        "example@example.com",
    ]
    full_text = "\n".join(r.prompt_text for r in corpus)
    for canary in canaries:
        assert canary not in full_text, f"Canary value found: {canary!r}"


def test_aegis_detect_field_is_present_but_empty(
    corpus: list[CorpusRecord],
) -> None:
    """aegis_detect is reserved for the validation pipeline; empty at gen-time."""
    for r in corpus:
        assert r.aegis_detect == [], (
            f"{r.id}: aegis_detect should be empty at generation time"
        )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def test_main_cli_writes_output(tmp_path: Path) -> None:
    from corpus.generate import main

    out = tmp_path / "corpus.jsonl"
    exit_code = main(["--seed", str(DEFAULT_SEED), "--output", str(out)])
    assert exit_code == 0
    assert out.is_file()
    line_count = sum(1 for _ in out.open(encoding="utf-8"))
    assert line_count == EXPECTED_RECORD_COUNT
