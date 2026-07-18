"""Ground-truth PII / secret detector for outbound payload inspection.

This detector runs against the *outbound* request payload that a harness
captures from an AI-tool client. Its job is narrow: identify how many
distinct PII / secret categories reached the wire, compared to what the
corpus record claimed the prompt contained.

The detector is deliberately **stdlib-only** — regex, Luhn, IBAN checksum,
and SSN structural rules. This keeps the benchmark repo commercially
neutral: no import of ``aegis-core``, no runtime dependency on any
commercial detector. The pattern set is cross-referenced against
``aegis-core``'s public docs but the code here is independent.

Detection categories intentionally mirror the labels used in
``corpus/corpus_schema.md`` so that scorer arithmetic in a later PR can
compare corpus expectations to outbound findings without a translation
layer.

Scope
-----
- Categories: EMAIL, PHONE, SSN, CREDIT_CARD, IBAN, AWS_ACCESS_KEY,
  OPENAI_KEY, GITHUB_PAT, SLACK_WEBHOOK, STRIPE_KEY, PHI_KEYWORD.
- The corpus also defines EIN / DRIVERS_LICENSE / PASSPORT /
  BANK_ACCOUNT / ROUTING_NUMBER / ADDRESS / PERSON / MRN. Those are
  intentionally *not* detected by regex here — none has a reliable
  signature independent of surrounding context. The scoring rubric in
  PR #5 treats them as ``substring_of_corpus_value_present`` (verbatim
  match against the corpus record), not as regex hits.

The detector is used by every API and web harness. Keep it small and
predictable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Finding:
    """One detected PII / secret category and its occurrences.

    Attributes:
        type: Category label. Matches the vocabulary in the corpus schema.
        count: Number of distinct matches for this category.
        values: The exact substrings that matched, in source order.
            Kept so callers can join with ``corpus_record.prompt_text``
            containment checks (i.e., verify a hit is actually a leak
            from the corpus prompt, not a hallucination in the response).
    """

    type: str
    count: int
    values: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Patterns
#
# Each pattern is a compiled regex with a named group where relevant.
# When the pattern needs post-validation (Luhn for CC, structural rules
# for SSN, ISO-13616 checksum for IBAN), the finder function does the
# validation and drops non-conforming candidates.
# ---------------------------------------------------------------------------

_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

# US-formatted SSN with dashes: XXX-XX-XXXX. We keep this strict on
# purpose — undashed 9-digit runs collide with too many other identifier
# formats (routing numbers, order ids) to be reliable.
_SSN_RE: Final[re.Pattern[str]] = re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b")

# Phone: North American formats + generic international with country
# code. Kept permissive because tool responses vary in punctuation.
_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    (?<![A-Za-z0-9])           # not preceded by alnum
    (?:
        \+?\d{1,3}[\s.-]?       # optional country code
    )?
    \(?\d{3}\)?[\s.-]?          # area code
    \d{3}[\s.-]?\d{4}           # local
    (?![A-Za-z0-9])             # not followed by alnum
    """,
    re.VERBOSE,
)

# Credit-card: 13-19 digits, dash/space-tolerant. Luhn-validated in
# ``_find_credit_cards``.
_CC_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:\d[ -]?){12,18}\d\b",
)

# IBAN: 2-letter country + 2 check digits + up to 30 alphanumerics.
# ISO-13616 checksum is validated in ``_find_iban``.
_IBAN_RE: Final[re.Pattern[str]] = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b")

# --- API secrets. Patterns anchored where possible to reduce collision.
_AWS_ACCESS_KEY_RE: Final[re.Pattern[str]] = re.compile(r"\bAKIA[A-Z0-9]{16}\b")

_OPENAI_KEY_RE: Final[re.Pattern[str]] = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")

_GITHUB_PAT_RE: Final[re.Pattern[str]] = re.compile(r"\bghp_[A-Za-z0-9]{30,}\b")

_SLACK_WEBHOOK_RE: Final[re.Pattern[str]] = re.compile(
    r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{20,}"
)

_STRIPE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")

# PHI markers we can detect by literal presence. Kept small on purpose:
# these are the tokens the corpus generator injects, so a scorer can
# tell whether the outbound payload preserved them verbatim.
_PHI_KEYWORDS: Final[tuple[str, ...]] = (
    "patient",
    "diagnosis",
    "diagnosed",
    "prescription",
    "medication",
    "mrn",
    "icd-10",
    "chart",
    "insurance denied",
    "problem list",
)

# ICD-10 codes have a distinctive shape: 1 letter + 2 digits + optional
# dot + up to 3 alphanumerics. We treat them as PHI signals.
_ICD10_RE: Final[re.Pattern[str]] = re.compile(r"\b[A-TV-Z]\d{2}(?:\.\d{1,3}[A-Z]?)?\b")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _luhn_valid(digits: str) -> bool:
    """Return True if ``digits`` (>= 12 chars, digits only) passes Luhn."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        n = ord(ch) - 48
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# IBAN mod-97 validator per ISO 13616.
_IBAN_LETTER_OFFSET: Final[int] = ord("A") - 10


def _iban_valid(candidate: str) -> bool:
    """Validate an IBAN using the ISO-13616 mod-97 checksum."""
    if len(candidate) < 15 or len(candidate) > 34:
        return False
    rearranged = candidate[4:] + candidate[:4]
    numeric = "".join(
        str(ord(c) - _IBAN_LETTER_OFFSET) if c.isalpha() else c for c in rearranged
    )
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


# SSN structural rules per SSA guidance:
#   area (first 3): 001-899 excluding 666
#   group (middle 2): 01-99
#   serial (last 4): 0001-9999
def _ssn_structurally_valid(area: str, group: str, serial: str) -> bool:
    """Return True if the three SSN parts pass SSA-issued-format rules."""
    a, g, s = int(area), int(group), int(serial)
    if a == 0 or a == 666 or a >= 900:
        return False
    if g == 0:
        return False
    return s != 0


# ---------------------------------------------------------------------------
# Category finders
# ---------------------------------------------------------------------------


def _find_emails(text: str) -> Finding | None:
    values = _EMAIL_RE.findall(text)
    if not values:
        return None
    return Finding(type="EMAIL", count=len(values), values=list(values))


def _find_ssns(text: str) -> Finding | None:
    values: list[str] = []
    for m in _SSN_RE.finditer(text):
        area, group, serial = m.group(1), m.group(2), m.group(3)
        if _ssn_structurally_valid(area, group, serial):
            values.append(m.group(0))
    if not values:
        return None
    return Finding(type="SSN", count=len(values), values=values)


def _find_phones(text: str) -> Finding | None:
    values: list[str] = []
    for m in _PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        # Anti-collision: SSN-shape is already caught above; skip it.
        if _SSN_RE.match(raw):
            continue
        # Anti-collision: don't double-count credit cards.
        if len(digits) >= 12 and _luhn_valid(digits):
            continue
        if 7 <= len(digits) <= 15:
            values.append(raw)
    if not values:
        return None
    return Finding(type="PHONE", count=len(values), values=values)


def _find_credit_cards(text: str) -> Finding | None:
    values: list[str] = []
    for m in _CC_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            values.append(m.group(0).strip())
    if not values:
        return None
    return Finding(type="CREDIT_CARD", count=len(values), values=values)


def _find_iban(text: str) -> Finding | None:
    values: list[str] = []
    for m in _IBAN_RE.finditer(text):
        if _iban_valid(m.group(1)):
            values.append(m.group(1))
    if not values:
        return None
    return Finding(type="IBAN", count=len(values), values=values)


def _find_aws_keys(text: str) -> Finding | None:
    values = _AWS_ACCESS_KEY_RE.findall(text)
    if not values:
        return None
    return Finding(type="AWS_ACCESS_KEY", count=len(values), values=list(values))


def _find_openai_keys(text: str) -> Finding | None:
    values = _OPENAI_KEY_RE.findall(text)
    if not values:
        return None
    return Finding(type="OPENAI_KEY", count=len(values), values=list(values))


def _find_github_pats(text: str) -> Finding | None:
    values = _GITHUB_PAT_RE.findall(text)
    if not values:
        return None
    return Finding(type="GITHUB_PAT", count=len(values), values=list(values))


def _find_slack_webhooks(text: str) -> Finding | None:
    values = _SLACK_WEBHOOK_RE.findall(text)
    if not values:
        return None
    return Finding(type="SLACK_WEBHOOK", count=len(values), values=list(values))


def _find_stripe_keys(text: str) -> Finding | None:
    values = _STRIPE_KEY_RE.findall(text)
    if not values:
        return None
    return Finding(type="STRIPE_KEY", count=len(values), values=list(values))


def _find_phi(text: str) -> Finding | None:
    """PHI is a union of keyword hits and ICD-10 code hits."""
    lower = text.lower()
    keyword_hits = [kw for kw in _PHI_KEYWORDS if kw in lower]
    icd_hits = _ICD10_RE.findall(text)
    count = len(keyword_hits) + len(icd_hits)
    if count == 0:
        return None
    return Finding(type="PHI_KEYWORD", count=count, values=[*keyword_hits, *icd_hits])


# Order matters for anti-collision inside individual finders (see
# ``_find_phones`` skipping SSN / CC). At the top level, order is stable
# for reproducible output but does not affect correctness.
_FINDERS: Final[tuple[Callable[[str], Finding | None], ...]] = (
    _find_emails,
    _find_ssns,
    _find_phones,
    _find_credit_cards,
    _find_iban,
    _find_aws_keys,
    _find_openai_keys,
    _find_github_pats,
    _find_slack_webhooks,
    _find_stripe_keys,
    _find_phi,
)


def detect(text: str) -> list[Finding]:
    """Return all findings in ``text``, sorted by category label.

    An empty list means the detector saw nothing sensitive. Callers
    treat that as "outbound payload looks clean" — the scorer combines
    this with corpus expectations to decide whether the tool redacted.

    Args:
        text: Any string. Typically the JSON body of an outbound API
            request or the ``prompt`` field within it.

    Returns:
        Findings sorted alphabetically by ``type`` for deterministic
        output. Empty list if nothing detected.
    """
    findings: list[Finding] = []
    for finder in _FINDERS:
        result = finder(text)
        if result is not None:
            findings.append(result)
    findings.sort(key=lambda f: f.type)
    return findings
