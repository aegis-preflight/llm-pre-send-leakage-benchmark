"""Tests for the ground-truth PII / secret detector.

The detector is the scoring backbone for every harness — a bug here
would silently mis-score every tool. These tests treat each category
as a contract: positive hits, negative rejects, and adversarial
anti-collision cases.
"""

from __future__ import annotations

from harness.detect import Finding, detect


def _types(findings: list[Finding]) -> set[str]:
    return {f.type for f in findings}


# ---------------------------------------------------------------------------
# Empty and clean inputs
# ---------------------------------------------------------------------------


def test_empty_string_returns_no_findings() -> None:
    assert detect("") == []


def test_clean_text_returns_no_findings() -> None:
    """Text without any PII markers should trigger nothing."""
    assert detect("Please summarize the Q3 earnings report in three bullets.") == []


def test_findings_sorted_alphabetically_by_type() -> None:
    """Deterministic output — sorting is part of the contract."""
    text = "email me@example.com and card 4111 1111 1111 1111."
    findings = detect(text)
    types = [f.type for f in findings]
    assert types == sorted(types)


# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------


def test_email_single_hit() -> None:
    findings = detect("contact alice@example.com about the invoice")
    emails = [f for f in findings if f.type == "EMAIL"]
    assert len(emails) == 1
    assert emails[0].count == 1
    assert "alice@example.com" in emails[0].values


def test_email_multiple_hits() -> None:
    findings = detect("cc a@b.com, d@e.co, x.y+z@sub.example.org")
    emails = next(f for f in findings if f.type == "EMAIL")
    assert emails.count == 3


def test_email_rejects_bare_at_sign() -> None:
    assert detect("meet @ 3pm") == []


# ---------------------------------------------------------------------------
# SSN
# ---------------------------------------------------------------------------


def test_ssn_valid_structural() -> None:
    findings = detect("SSN on file: 123-45-6789.")
    ssns = [f for f in findings if f.type == "SSN"]
    assert len(ssns) == 1
    assert ssns[0].count == 1


def test_ssn_rejects_forbidden_area_666() -> None:
    """Area 666 is never issued — must be filtered out."""
    findings = detect("SSN: 666-12-3456")
    assert "SSN" not in _types(findings)


def test_ssn_rejects_zero_area() -> None:
    findings = detect("SSN: 000-12-3456")
    assert "SSN" not in _types(findings)


def test_ssn_rejects_zero_group() -> None:
    findings = detect("SSN: 123-00-6789")
    assert "SSN" not in _types(findings)


def test_ssn_rejects_area_over_899() -> None:
    findings = detect("SSN: 900-12-3456")
    assert "SSN" not in _types(findings)


def test_ssn_rejects_undashed_run_of_digits() -> None:
    """Strict format only — undashed digit runs collide with too many things."""
    findings = detect("Order number: 123456789")
    assert "SSN" not in _types(findings)


# ---------------------------------------------------------------------------
# PHONE
# ---------------------------------------------------------------------------


def test_phone_us_paren_format() -> None:
    findings = detect("Call (555) 234-5678 back tomorrow.")
    phones = [f for f in findings if f.type == "PHONE"]
    assert len(phones) == 1


def test_phone_dashed_format() -> None:
    findings = detect("Ring 415-555-2671 for support.")
    assert "PHONE" in _types(findings)


def test_phone_does_not_double_count_credit_card() -> None:
    """A Luhn-valid 16-digit run must not also register as a phone."""
    findings = detect("Card: 4111 1111 1111 1111")
    assert "PHONE" not in _types(findings)
    assert "CREDIT_CARD" in _types(findings)


def test_phone_does_not_double_count_ssn() -> None:
    findings = detect("SSN 123-45-6789")
    assert "PHONE" not in _types(findings)


# ---------------------------------------------------------------------------
# CREDIT_CARD
# ---------------------------------------------------------------------------


def test_credit_card_luhn_valid_visa_test_number() -> None:
    """4111 1111 1111 1111 is Luhn-valid — the canonical Visa test number."""
    findings = detect("Card 4111 1111 1111 1111 expired.")
    cards = [f for f in findings if f.type == "CREDIT_CARD"]
    assert len(cards) == 1


def test_credit_card_luhn_valid_amex() -> None:
    """378282246310005 is a Luhn-valid 15-digit Amex test number."""
    findings = detect("Amex 378282246310005 on file.")
    assert "CREDIT_CARD" in _types(findings)


def test_credit_card_rejects_luhn_invalid() -> None:
    """A random 16-digit run that fails Luhn must not be flagged."""
    findings = detect("Random ID: 1234 5678 1234 5678")
    assert "CREDIT_CARD" not in _types(findings)


# ---------------------------------------------------------------------------
# IBAN
# ---------------------------------------------------------------------------


def test_iban_valid_de() -> None:
    """DE89370400440532013000 is the canonical valid IBAN test value."""
    findings = detect("Wire to DE89370400440532013000 by Friday.")
    ibans = [f for f in findings if f.type == "IBAN"]
    assert len(ibans) == 1


def test_iban_rejects_bad_checksum() -> None:
    findings = detect("Wire to DE89370400440532013001 by Friday.")
    assert "IBAN" not in _types(findings)


# ---------------------------------------------------------------------------
# API secrets
# ---------------------------------------------------------------------------


def test_aws_access_key() -> None:
    findings = detect("Env: AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE")
    assert "AWS_ACCESS_KEY" in _types(findings)


def test_openai_key_sk_prefix() -> None:
    fake = "sk-" + ("a" * 48)
    findings = detect(f"OPENAI_API_KEY={fake}")
    assert "OPENAI_KEY" in _types(findings)


def test_github_pat_ghp_prefix() -> None:
    fake = "ghp_" + ("A" * 36)
    findings = detect(f"token: {fake}")
    assert "GITHUB_PAT" in _types(findings)


def test_slack_webhook() -> None:
    url = "https://hooks.slack.com/services/T12345678A/B12345678A/" + ("a" * 24)
    findings = detect(f"webhook: {url}")
    assert "SLACK_WEBHOOK" in _types(findings)


def test_stripe_live_key() -> None:
    fake = "sk_live_" + ("x" * 24)
    findings = detect(f"stripe: {fake}")
    assert "STRIPE_KEY" in _types(findings)


# ---------------------------------------------------------------------------
# PHI
# ---------------------------------------------------------------------------


def test_phi_keyword_hit() -> None:
    findings = detect("Patient chart shows medication refill due.")
    phi = [f for f in findings if f.type == "PHI_KEYWORD"]
    assert len(phi) == 1
    # "patient" + "chart" + "medication" all hit the keyword bucket.
    assert phi[0].count >= 3


def test_phi_icd10_code_hit() -> None:
    findings = detect("Diagnosis code E11.9 assigned.")
    assert "PHI_KEYWORD" in _types(findings)


def test_phi_clean_text_no_hit() -> None:
    findings = detect("The weather forecast looks clear tomorrow.")
    assert "PHI_KEYWORD" not in _types(findings)


# ---------------------------------------------------------------------------
# Mixed and adversarial
# ---------------------------------------------------------------------------


def test_mixed_pii_all_categories_present() -> None:
    text = (
        "Customer alice@example.com called about card 4111 1111 1111 1111 "
        "and their SSN 123-45-6789. Their patient chart shows E11.9."
    )
    types = _types(detect(text))
    assert {"EMAIL", "CREDIT_CARD", "SSN", "PHI_KEYWORD"}.issubset(types)


def test_finding_values_preserved_for_downstream_matching() -> None:
    """Callers need the raw match strings to correlate to corpus records."""
    findings = detect("me@example.com and you@example.com")
    email = next(f for f in findings if f.type == "EMAIL")
    assert email.values == ["me@example.com", "you@example.com"]
