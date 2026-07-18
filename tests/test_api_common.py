"""Tests for shared API-harness building blocks in ``harness/api/_common.py``."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from harness.api._common import (
    CorpusRecord,
    HarnessResult,
    compute_sent_verbatim,
    load_corpus,
    utc_now_iso,
    write_results,
)
from harness.detect import Finding

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# CorpusRecord.from_dict
# ---------------------------------------------------------------------------


def _minimal_record_dict() -> dict[str, object]:
    return {
        "id": "ident-001",
        "category": "identifiers",
        "subcategory": "ssn",
        "prompt_text": "SSN 123-45-6789",
        "expected_categories": ["SSN"],
        "expected_count": {"SSN": 1},
    }


def test_from_dict_populates_all_required_fields() -> None:
    record = CorpusRecord.from_dict(_minimal_record_dict())
    assert record.id == "ident-001"
    assert record.category == "identifiers"
    assert record.expected_count == {"SSN": 1}


def test_from_dict_ignores_unknown_keys() -> None:
    """Forward-compatibility: unknown fields (aegis_detect, notes) are dropped."""
    data = _minimal_record_dict()
    data["aegis_detect"] = [{"type": "SSN", "count": 1}]
    data["notes"] = "example note"
    data["unexpected_future_field"] = "ignored"
    record = CorpusRecord.from_dict(data)
    assert record.id == "ident-001"


# ---------------------------------------------------------------------------
# load_corpus
# ---------------------------------------------------------------------------


def test_load_corpus_parses_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        fp.write(json.dumps(_minimal_record_dict()) + "\n")
        fp.write(json.dumps({**_minimal_record_dict(), "id": "ident-002"}) + "\n")
    records = load_corpus(path)
    assert len(records) == 2
    assert [r.id for r in records] == ["ident-001", "ident-002"]


def test_load_corpus_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "blanks.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        fp.write(json.dumps(_minimal_record_dict()) + "\n")
        fp.write("\n")
        fp.write("   \n")
        fp.write(json.dumps({**_minimal_record_dict(), "id": "ident-002"}) + "\n")
    assert len(load_corpus(path)) == 2


def test_load_corpus_raises_on_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        fp.write(json.dumps(_minimal_record_dict()) + "\n")
        fp.write("{not valid json\n")
    with pytest.raises(ValueError, match=r"broken\.jsonl:2"):
        load_corpus(path)


def test_load_corpus_reads_real_v1_corpus() -> None:
    """The locked v1 corpus loads without any per-record errors."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    corpus_path = repo_root / "corpus" / "corpus_v1.jsonl"
    records = load_corpus(corpus_path)
    assert len(records) == 100
    # Sanity: every category label is represented at least once.
    categories = {r.category for r in records}
    assert categories == {
        "identifiers",
        "financial",
        "contact",
        "names",
        "api_secrets",
        "phi",
        "mixed",
    }


# ---------------------------------------------------------------------------
# compute_sent_verbatim
# ---------------------------------------------------------------------------


def test_sent_verbatim_true_when_prompt_appears_in_payload() -> None:
    prompt = "SSN 123-45-6789 update."
    payload = {"messages": [{"role": "user", "content": prompt}]}
    sent, findings = compute_sent_verbatim(prompt, payload, ["SSN"])
    assert sent is True
    assert any(f.type == "SSN" for f in findings)


def test_sent_verbatim_true_when_categories_still_present_after_normalization() -> None:
    """Payload transforms whitespace but leaves the SSN — still a leak."""
    prompt = "SSN 123-45-6789 update."
    normalized = "ssn 123-45-6789 update"
    payload = {"messages": [{"role": "user", "content": normalized}]}
    sent, findings = compute_sent_verbatim(prompt, payload, ["SSN"])
    assert sent is True
    assert any(f.type == "SSN" for f in findings)


def test_sent_verbatim_false_when_payload_is_redacted() -> None:
    """Payload contains a scrubbed version — no PII leaks."""
    prompt = "SSN 123-45-6789 update."
    payload = {"messages": [{"role": "user", "content": "SSN [REDACTED] update."}]}
    sent, findings = compute_sent_verbatim(prompt, payload, ["SSN"])
    assert sent is False
    assert findings == []


def test_sent_verbatim_false_when_only_some_categories_leak() -> None:
    """Corpus had SSN + EMAIL; payload leaks only email → not verbatim."""
    prompt = "Contact alice@example.com about SSN 123-45-6789."
    payload = {
        "messages": [
            {"role": "user", "content": "Contact alice@example.com about SSN [MASK]."}
        ]
    }
    sent, findings = compute_sent_verbatim(prompt, payload, ["SSN", "EMAIL"])
    assert sent is False
    assert {f.type for f in findings} == {"EMAIL"}


# ---------------------------------------------------------------------------
# write_results
# ---------------------------------------------------------------------------


def _sample_result(prompt_id: str = "ident-001") -> HarnessResult:
    return HarnessResult(
        prompt_id=prompt_id,
        tool="anthropic",
        tier="api-direct",
        model="claude-sonnet-4-6",
        timestamp_utc="2026-07-18T12:00:00Z",
        request_payload={"messages": [{"role": "user", "content": "hello"}]},
        response_text="hi there",
        outbound_findings=[Finding(type="EMAIL", count=1, values=["me@x.com"])],
        sent_verbatim=True,
    )


def test_write_results_produces_valid_json(tmp_path: Path) -> None:
    out = tmp_path / "results.json"
    write_results([_sample_result("ident-001"), _sample_result("ident-002")], out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["count"] == 2
    assert [r["prompt_id"] for r in data["results"]] == ["ident-001", "ident-002"]


def test_write_results_serializes_finding_dataclass(tmp_path: Path) -> None:
    """Findings must serialize to plain dicts, not `<Finding object>` strings."""
    out = tmp_path / "results.json"
    write_results([_sample_result()], out)
    data = json.loads(out.read_text(encoding="utf-8"))
    findings = data["results"][0]["outbound_findings"]
    assert findings == [{"type": "EMAIL", "count": 1, "values": ["me@x.com"]}]


def test_write_results_creates_parent_directory(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "results.json"
    write_results([_sample_result()], out)
    assert out.is_file()


def test_write_results_is_atomic_no_tmp_file_left_behind(tmp_path: Path) -> None:
    """After a successful write, only the target file exists — no .tmp sibling."""
    out = tmp_path / "results.json"
    write_results([_sample_result()], out)
    siblings = list(tmp_path.iterdir())
    assert siblings == [out]


# ---------------------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------------------


def test_utc_now_iso_ends_with_z() -> None:
    """UTC marker is 'Z', not '+00:00', for compact JSON output."""
    stamp = utc_now_iso()
    assert stamp.endswith("Z")


def test_utc_now_iso_second_precision() -> None:
    """Trim microseconds — deterministic length for JSON diffs."""
    stamp = utc_now_iso()
    # Format: YYYY-MM-DDTHH:MM:SSZ = 20 chars
    assert len(stamp) == 20
