"""Pre-Send Leakage Benchmark — deterministic corpus generator.

Generates 100 synthesized prompts across 7 PII categories. Output is written
to ``corpus/corpus_v1.jsonl`` as one JSON record per line.

The corpus is **deterministic**: running this script with the same ``--seed``
produces byte-identical output. The default seed is locked at v1.0.0; future
corpus revisions ship as ``corpus_v2.jsonl`` with their own seed.

Data safety
-----------
1. All PII is synthesized via Faker_. Never real personal data.
2. API secrets are syntactically valid but **inactive** — never match a real
   credential. They follow each provider's published format.
3. ICD-10 codes are public medical reference codes, not patient records.
4. MRN-shaped identifiers are synthetic 8-digit numbers, not real chart IDs.

.. _Faker: https://faker.readthedocs.io/

Usage
-----
::

    python corpus/generate.py
    python corpus/generate.py --output corpus/corpus_v1.jsonl
    python corpus/generate.py --seed 20260623 --output /tmp/test.jsonl

Schema is documented in :doc:`corpus_schema.md`.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import string
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from faker import Faker

LOGGER = logging.getLogger(__name__)

# Deterministic seed for v1.0.0. Changing this changes the entire corpus and
# MUST be accompanied by a corpus version bump (corpus_v2, corpus_v3, ...).
DEFAULT_SEED: Final[int] = 20260623

# Faker locales — variety in names, addresses, and phone formats.
DEFAULT_LOCALES: Final[list[str]] = ["en_US", "en_GB", "de_DE"]

DEFAULT_OUTPUT: Final[Path] = Path(__file__).parent / "corpus_v1.jsonl"

EXPECTED_RECORD_COUNT: Final[int] = 100

# Category distribution — sums to 100.
CATEGORY_DISTRIBUTION: Final[dict[str, int]] = {
    "identifiers": 20,
    "financial": 20,
    "contact": 20,
    "names": 10,
    "api_secrets": 15,
    "phi": 10,
    "mixed": 5,
}

# Public ICD-10 reference codes — not patient data. Used to populate PHI
# prompts with realistic medical context without using any real chart info.
ICD10_REFERENCE: Final[list[tuple[str, str]]] = [
    ("E11.9", "type 2 diabetes mellitus without complications"),
    ("I10", "essential hypertension"),
    ("J45.909", "unspecified asthma, uncomplicated"),
    ("F32.9", "major depressive disorder, single episode"),
    ("M54.5", "low back pain"),
    ("R51.9", "headache, unspecified"),
    ("K21.9", "GERD without esophagitis"),
    ("J06.9", "acute upper respiratory infection"),
]

# Common medication names — generic drug references, not prescriptions.
MEDICATIONS_REFERENCE: Final[list[str]] = [
    "metformin 500mg",
    "lisinopril 10mg",
    "atorvastatin 20mg",
    "albuterol inhaler",
    "sertraline 50mg",
    "omeprazole 20mg",
]


@dataclass(frozen=True)
class CorpusRecord:
    """A single test prompt with semantic ground-truth labels.

    Fields are documented in ``corpus/corpus_schema.md``. The dataclass is
    frozen to prevent accidental mutation after generation.

    Attributes:
        id: Stable identifier. Format ``<prefix>-<3-digit-index>``.
        category: One of the values in CATEGORY_DISTRIBUTION.
        subcategory: More specific type within the category.
        prompt_text: The exact text submitted to each tool under test.
        expected_categories: Semantic ground-truth — what categories of
            sensitive data the prompt was designed to contain.
        expected_count: Map of category label to expected count.
        aegis_detect: Populated by a separate validation pipeline that runs
            the canonical detector against ``prompt_text``. Empty at
            generation time; filled in PR #5 (results phase).
        notes: Free-form notes about the prompt (optional).
    """

    id: str
    category: str
    subcategory: str
    prompt_text: str
    expected_categories: list[str]
    expected_count: dict[str, int]
    aegis_detect: list[dict[str, object]] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Synthetic API-secret generators
#
# Every output here is syntactically valid for its respective provider but
# does NOT correspond to a real credential. The patterns are documented in
# each provider's public docs; we build them programmatically (no literal
# secret strings in source) to keep secret-scanners happy.
# ---------------------------------------------------------------------------


def _synthetic_aws_access_key(rng: random.Random) -> str:
    """Generate an AKIA-prefixed key matching AWS access-key format."""
    chars = string.ascii_uppercase + string.digits
    # Synthetic, deterministic seeding required — random is correct here.
    body = "".join(rng.choices(chars, k=16))
    return "AKIA" + body


def _synthetic_openai_key(rng: random.Random) -> str:
    """Generate an sk- prefixed key matching OpenAI's documented format."""
    chars = string.ascii_letters + string.digits
    body = "".join(rng.choices(chars, k=48))
    return "sk-" + body


def _synthetic_github_pat(rng: random.Random) -> str:
    """Generate a ghp_ prefixed personal access token (GitHub format)."""
    chars = string.ascii_letters + string.digits
    body = "".join(rng.choices(chars, k=36))
    return "ghp_" + body


def _synthetic_slack_webhook(rng: random.Random) -> str:
    """Generate a Slack incoming-webhook URL with synthetic team and channel ids."""
    upper_alnum = string.ascii_uppercase + string.digits
    mixed_alnum = string.ascii_letters + string.digits
    team = "T" + "".join(rng.choices(upper_alnum, k=10))
    channel = "B" + "".join(rng.choices(upper_alnum, k=10))
    secret = "".join(rng.choices(mixed_alnum, k=24))
    return f"https://hooks.slack.com/services/{team}/{channel}/{secret}"


def _synthetic_stripe_key(rng: random.Random) -> str:
    """Generate a sk_live_ prefixed Stripe key (live-mode format)."""
    chars = string.ascii_letters + string.digits
    body = "".join(rng.choices(chars, k=24))
    return "sk_live_" + body


# ---------------------------------------------------------------------------
# Synthetic identifier helpers
# ---------------------------------------------------------------------------


def _synthetic_ein(rng: random.Random) -> str:
    """Generate an EIN-formatted string ``XX-XXXXXXX``."""
    prefix = rng.randint(10, 99)
    suffix = rng.randint(1_000_000, 9_999_999)
    return f"{prefix}-{suffix:07d}"


def _synthetic_drivers_license(rng: random.Random) -> str:
    """Generate a US-style driver's license number (state-letter + 7 digits)."""
    letter = rng.choice(string.ascii_uppercase)
    number = rng.randint(1_000_000, 9_999_999)
    return f"{letter}{number}"


def _synthetic_passport(rng: random.Random) -> str:
    """Generate a US-style passport number (9 digits)."""
    return f"{rng.randint(100_000_000, 999_999_999)}"


def _synthetic_routing(rng: random.Random) -> str:
    """Generate a 9-digit ABA routing number."""
    return f"{rng.randint(100_000_000, 999_999_999)}"


def _synthetic_mrn(rng: random.Random) -> str:
    """Generate a synthetic MRN-shaped identifier (8 digits with MRN- prefix)."""
    return f"MRN-{rng.randint(10_000_000, 99_999_999)}"


# ---------------------------------------------------------------------------
# Per-category generators
# ---------------------------------------------------------------------------


def _make_record(
    prefix: str,
    index: int,
    category: str,
    subcategory: str,
    prompt_text: str,
    expected_categories: list[str],
    expected_count: dict[str, int],
    notes: str = "",
) -> CorpusRecord:
    """Construct a CorpusRecord with a formatted id."""
    return CorpusRecord(
        id=f"{prefix}-{index:03d}",
        category=category,
        subcategory=subcategory,
        prompt_text=prompt_text,
        expected_categories=expected_categories,
        expected_count=expected_count,
        notes=notes,
    )


def generate_identifiers(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 20 prompts containing identifier PII: SSN, EIN, DL, passport."""
    records: list[CorpusRecord] = []

    ssn_templates = [
        "Please verify customer record: SSN {ssn}.",
        "Tax filing question — my SSN is {ssn}, what's the next step?",
        "Quick check — does SSN {ssn} match what's in our records?",
        "Update customer file: SSN on record is {ssn}, last visit Tuesday.",
        "Help draft a response to an audit request mentioning SSN {ssn}.",
    ]
    # SSN is a US-specific concept. Faker's default ssn() randomly picks
    # between en_US (XXX-XX-XXXX), en_GB (NI number), and de_DE (Steuer-ID)
    # when the Faker instance is multi-locale — pin to en_US for SSN.
    us_fake = fake["en_US"]
    for i in range(1, 9):
        template = ssn_templates[(i - 1) % len(ssn_templates)]
        prompt = template.format(ssn=us_fake.ssn())
        records.append(
            _make_record("ident", i, "identifiers", "ssn", prompt, ["SSN"], {"SSN": 1})
        )

    ein_templates = [
        "Our company EIN is {ein}, can you draft a vendor onboarding response?",
        "For tax form 1099, recipient EIN: {ein}.",
        "Update contractor record — EIN {ein}, payment terms net-30.",
        "Verify this EIN against IRS records: {ein}.",
    ]
    for i in range(9, 13):
        template = ein_templates[(i - 9) % len(ein_templates)]
        prompt = template.format(ein=_synthetic_ein(rng))
        records.append(
            _make_record("ident", i, "identifiers", "ein", prompt, ["EIN"], {"EIN": 1})
        )

    dl_templates = [
        "Customer's driver's license number is {dl}, address verification needed.",
        "Need to update DL on file — new number is {dl}.",
        "DL {dl} flagged for renewal in 30 days.",
        "Process this ID verification: license number {dl}.",
    ]
    for i in range(13, 17):
        template = dl_templates[(i - 13) % len(dl_templates)]
        prompt = template.format(dl=_synthetic_drivers_license(rng))
        records.append(
            _make_record(
                "ident",
                i,
                "identifiers",
                "drivers_license",
                prompt,
                ["DRIVERS_LICENSE"],
                {"DRIVERS_LICENSE": 1},
            )
        )

    passport_templates = [
        "Travel booking — passport number {passport}, departure next Tuesday.",
        "Visa application notes: passport {passport}, expires 2030.",
        "Update employee file: new passport {passport} issued.",
        "Customer's passport is {passport}, please confirm spelling matches.",
    ]
    for i in range(17, 21):
        template = passport_templates[(i - 17) % len(passport_templates)]
        prompt = template.format(passport=_synthetic_passport(rng))
        records.append(
            _make_record(
                "ident",
                i,
                "identifiers",
                "passport",
                prompt,
                ["PASSPORT"],
                {"PASSPORT": 1},
            )
        )

    return records


def generate_financial(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 20 financial-PII prompts: CC, IBAN, bank account, routing."""
    records: list[CorpusRecord] = []

    cc_templates = [
        "Customer payment failed — card on file is {cc}.",
        "Refund request for transaction on card {cc}, amount $234.50.",
        "Please charge {cc} for the annual subscription.",
        "Update billing — replace expired card with {cc}.",
        "Customer disputes charge on card {cc}, last 4 digits visible.",
    ]
    for i in range(1, 9):
        template = cc_templates[(i - 1) % len(cc_templates)]
        prompt = template.format(cc=fake.credit_card_number())
        records.append(
            _make_record(
                "fin",
                i,
                "financial",
                "credit_card",
                prompt,
                ["CREDIT_CARD"],
                {"CREDIT_CARD": 1},
                notes="CC generated by Faker — Luhn-valid by construction.",
            )
        )

    iban_templates = [
        "Wire transfer destination: IBAN {iban}, urgent.",
        "Confirm IBAN for vendor payment: {iban}.",
        "Customer banking details — IBAN {iban}.",
        "Add this IBAN to approved beneficiaries: {iban}.",
    ]
    for i in range(9, 13):
        template = iban_templates[(i - 9) % len(iban_templates)]
        prompt = template.format(iban=fake.iban())
        records.append(
            _make_record("fin", i, "financial", "iban", prompt, ["IBAN"], {"IBAN": 1})
        )

    bank_templates = [
        "Account number is {acct}, please verify last transaction.",
        "Direct deposit setup — bank account {acct}.",
        "Refund to account {acct}, customer confirmed by phone.",
        "Update payroll: new account number {acct}.",
    ]
    for i in range(13, 17):
        template = bank_templates[(i - 13) % len(bank_templates)]
        acct = f"{rng.randint(10_000_000, 9_999_999_999)}"
        prompt = template.format(acct=acct)
        records.append(
            _make_record(
                "fin",
                i,
                "financial",
                "bank_account",
                prompt,
                ["BANK_ACCOUNT"],
                {"BANK_ACCOUNT": 1},
            )
        )

    routing_templates = [
        "ACH transfer — routing number {routing}, account verified.",
        "Update bank routing on file: {routing}.",
        "Wire instructions: routing {routing}, beneficiary as discussed.",
        "Customer's bank uses routing {routing} for incoming wires.",
    ]
    for i in range(17, 21):
        template = routing_templates[(i - 17) % len(routing_templates)]
        prompt = template.format(routing=_synthetic_routing(rng))
        records.append(
            _make_record(
                "fin",
                i,
                "financial",
                "routing",
                prompt,
                ["ROUTING_NUMBER"],
                {"ROUTING_NUMBER": 1},
            )
        )

    return records


def generate_contact(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 20 contact-PII prompts: email, phone, address."""
    records: list[CorpusRecord] = []

    email_templates = [
        "Send welcome email to {email}, mention the onboarding call.",
        "Customer at {email} reports login issues — please troubleshoot.",
        "Unsubscribe request from {email}, process per GDPR Article 17.",
        "Draft a follow-up to {email} about the renewal pricing.",
        "Forward this thread to {email}, CC the support team.",
    ]
    for i in range(1, 8):
        template = email_templates[(i - 1) % len(email_templates)]
        prompt = template.format(email=fake.email())
        records.append(
            _make_record(
                "contact",
                i,
                "contact",
                "email",
                prompt,
                ["EMAIL"],
                {"EMAIL": 1},
            )
        )

    phone_templates = [
        "Call customer at {phone} re: account verification.",
        "Phone on file: {phone}, last contact 3 weeks ago.",
        "Schedule a callback to {phone} for tomorrow afternoon.",
        "Update contact — primary number is {phone}.",
        "Customer requested SMS to {phone}, opt-in confirmed.",
    ]
    for i in range(8, 15):
        template = phone_templates[(i - 8) % len(phone_templates)]
        prompt = template.format(phone=fake.phone_number())
        records.append(
            _make_record(
                "contact",
                i,
                "contact",
                "phone",
                prompt,
                ["PHONE"],
                {"PHONE": 1},
            )
        )

    address_templates = [
        "Ship the package to {address}.",
        "Update billing address to {address}, effective next month.",
        "Customer's home address is {address}, please verify.",
        "Mail the contract to {address}, signature required.",
        "Delivery instructions for {address}: leave at the front door.",
        "Service appointment scheduled at {address}.",
    ]
    for i in range(15, 21):
        template = address_templates[(i - 15) % len(address_templates)]
        # Use one-liner address to keep PII concentrated; faker.address can be
        # multi-line otherwise.
        address = ", ".join(fake.address().splitlines())
        prompt = template.format(address=address)
        records.append(
            _make_record(
                "contact",
                i,
                "contact",
                "address",
                prompt,
                ["ADDRESS"],
                {"ADDRESS": 1},
            )
        )

    return records


def generate_names(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 10 name-only prompts: person, person + title."""
    records: list[CorpusRecord] = []

    name_templates = [
        "Draft an introduction for {name} to the engineering team.",
        "Schedule a one-on-one with {name} next Tuesday.",
        "Write a thank-you note to {name} for last week's feedback.",
        "Add {name} to the project channel and brief them on context.",
        "Send the contract to {name} for signature by end of week.",
    ]
    for i in range(1, 6):
        template = name_templates[(i - 1) % len(name_templates)]
        prompt = template.format(name=fake.name())
        records.append(
            _make_record(
                "name", i, "names", "person", prompt, ["PERSON"], {"PERSON": 1}
            )
        )

    titled_templates = [
        "Forward the briefing to {name}, copy the executive team.",
        "Set up a meeting with {name} for the quarterly review.",
        "Send the proposal to {name} and follow up in 48 hours.",
        "Brief {name} on the customer escalation before tomorrow's call.",
        "Add {name} to the steering committee invite list.",
    ]
    for i in range(6, 11):
        template = titled_templates[(i - 6) % len(titled_templates)]
        full_name = f"{fake.prefix()} {fake.name()}"
        prompt = template.format(name=full_name)
        records.append(
            _make_record(
                "name",
                i,
                "names",
                "person_titled",
                prompt,
                ["PERSON"],
                {"PERSON": 1},
            )
        )

    return records


def generate_api_secrets(rng: random.Random) -> list[CorpusRecord]:
    """Generate 15 prompts containing inactive API secrets."""
    records: list[CorpusRecord] = []

    aws_templates = [
        "My AWS deploy is failing — access key {key} returns InvalidSignature.",
        "Can you debug this? AWS_ACCESS_KEY_ID={key} but boto3 won't authenticate.",
        "Rotated keys this morning, new access key is {key}, secret stays the same.",
    ]
    for i in range(1, 4):
        template = aws_templates[(i - 1) % len(aws_templates)]
        prompt = template.format(key=_synthetic_aws_access_key(rng))
        records.append(
            _make_record(
                "secret",
                i,
                "api_secrets",
                "aws_access_key",
                prompt,
                ["AWS_ACCESS_KEY"],
                {"AWS_ACCESS_KEY": 1},
                notes="Synthetic AKIA-prefixed key, not active.",
            )
        )

    openai_templates = [
        "Why does this fail? OPENAI_API_KEY={key} but I get 401.",
        "My OpenAI key {key} hit the rate limit, can you suggest a retry strategy?",
        "Embed this into a fastapi snippet — key is {key}.",
    ]
    for i in range(4, 7):
        template = openai_templates[(i - 4) % len(openai_templates)]
        prompt = template.format(key=_synthetic_openai_key(rng))
        records.append(
            _make_record(
                "secret",
                i,
                "api_secrets",
                "openai_key",
                prompt,
                ["OPENAI_KEY"],
                {"OPENAI_KEY": 1},
                notes="Synthetic sk- prefixed key, not active.",
            )
        )

    github_templates = [
        "Push failing — my PAT {pat} returns 401 on `git push`.",
        'Help debug this curl: -H "Authorization: token {pat}" against api.github.',
        "Personal access token {pat} stopped working after rotation.",
    ]
    for i in range(7, 10):
        template = github_templates[(i - 7) % len(github_templates)]
        prompt = template.format(pat=_synthetic_github_pat(rng))
        records.append(
            _make_record(
                "secret",
                i,
                "api_secrets",
                "github_pat",
                prompt,
                ["GITHUB_PAT"],
                {"GITHUB_PAT": 1},
                notes="Synthetic ghp_ prefixed PAT, not active.",
            )
        )

    slack_templates = [
        "Why is this slack webhook 404? URL: {url}",
        "Posting to {url} returns 'no_service', what does that mean?",
        "Update incident-response bot to use {url} for alerts.",
    ]
    for i in range(10, 13):
        template = slack_templates[(i - 10) % len(slack_templates)]
        prompt = template.format(url=_synthetic_slack_webhook(rng))
        records.append(
            _make_record(
                "secret",
                i,
                "api_secrets",
                "slack_webhook",
                prompt,
                ["SLACK_WEBHOOK"],
                {"SLACK_WEBHOOK": 1},
                notes="Synthetic Slack webhook, not active.",
            )
        )

    stripe_templates = [
        "Charge failing in production — Stripe key {key} returns 'api_key_expired'.",
        "Why is sk_live_... rejected when sk_test_... works? Key: {key}",
        "Migrating to a new account, the new live key is {key}.",
    ]
    for i in range(13, 16):
        template = stripe_templates[(i - 13) % len(stripe_templates)]
        prompt = template.format(key=_synthetic_stripe_key(rng))
        records.append(
            _make_record(
                "secret",
                i,
                "api_secrets",
                "stripe_key",
                prompt,
                ["STRIPE_KEY"],
                {"STRIPE_KEY": 1},
                notes="Synthetic sk_live_ prefixed Stripe key, not active.",
            )
        )

    return records


def generate_phi(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 10 PHI prompts: ICD-10, MRN, medication-in-context."""
    records: list[CorpusRecord] = []

    icd_templates = [
        "Patient diagnosed with {desc} ({code}), next steps?",
        "Code {code} ({desc}) flagged for follow-up in 90 days.",
        "Add {code} to the problem list — patient has {desc}.",
        "Insurance denied claim for {code} ({desc}), can you draft an appeal?",
        "Quality measure question: how do we report {code} for the dashboard?",
    ]
    for i in range(1, 6):
        template = icd_templates[(i - 1) % len(icd_templates)]
        code, desc = ICD10_REFERENCE[(i - 1) % len(ICD10_REFERENCE)]
        prompt = template.format(code=code, desc=desc)
        records.append(
            _make_record(
                "phi",
                i,
                "phi",
                "icd10_code",
                prompt,
                ["PHI_KEYWORD"],
                {"PHI_KEYWORD": 1},
                notes="ICD-10 is a public reference code, not patient data.",
            )
        )

    mrn_templates = [
        "Pull chart for {mrn}, last appointment was 3 weeks ago.",
        "Patient {mrn} is here for follow-up, please review labs.",
        "Schedule {mrn} for the cardiology consult.",
    ]
    for i in range(6, 9):
        template = mrn_templates[(i - 6) % len(mrn_templates)]
        prompt = template.format(mrn=_synthetic_mrn(rng))
        records.append(
            _make_record(
                "phi",
                i,
                "phi",
                "mrn",
                prompt,
                ["MRN"],
                {"MRN": 1},
                notes="MRN-shaped 8-digit synthetic ID, not a real chart number.",
            )
        )

    med_templates = [
        "Patient is on {med}, can you draft refill instructions?",
        "Adjusting {med} dose — any interactions to watch for?",
    ]
    for i in range(9, 11):
        template = med_templates[(i - 9) % len(med_templates)]
        med = MEDICATIONS_REFERENCE[(i - 9) % len(MEDICATIONS_REFERENCE)]
        prompt = template.format(med=med)
        records.append(
            _make_record(
                "phi",
                i,
                "phi",
                "medication",
                prompt,
                ["PHI_KEYWORD"],
                {"PHI_KEYWORD": 1},
                notes="Generic medication reference, not a prescription.",
            )
        )

    return records


def generate_mixed(fake: Faker, rng: random.Random) -> list[CorpusRecord]:
    """Generate 5 multi-PII prompts that combine categories realistically."""
    records: list[CorpusRecord] = []

    # 1: SSN + email
    prompt_1 = (
        f"Customer service note: please reach out to {fake.email()} "
        f"about their SSN {fake.ssn()} update request — they called yesterday."
    )
    records.append(
        _make_record(
            "mixed",
            1,
            "mixed",
            "ssn_email",
            prompt_1,
            ["SSN", "EMAIL"],
            {"SSN": 1, "EMAIL": 1},
        )
    )

    # 2: CC + phone + email (payment-failure ticket)
    prompt_2 = (
        f"Refund ticket — card {fake.credit_card_number()} declined, "
        f"customer reachable at {fake.phone_number()} or {fake.email()}. "
        f"Please follow up by end of day."
    )
    records.append(
        _make_record(
            "mixed",
            2,
            "mixed",
            "cc_phone_email",
            prompt_2,
            ["CREDIT_CARD", "PHONE", "EMAIL"],
            {"CREDIT_CARD": 1, "PHONE": 1, "EMAIL": 1},
        )
    )

    # 3: PHI + MRN + medication (clinical note)
    code, desc = ICD10_REFERENCE[0]
    med = MEDICATIONS_REFERENCE[0]
    mrn = _synthetic_mrn(rng)
    prompt_3 = (
        f"Patient {mrn} presents with {desc} ({code}), currently on {med}. "
        f"Please draft a follow-up plan."
    )
    records.append(
        _make_record(
            "mixed",
            3,
            "mixed",
            "phi_mrn_medication",
            prompt_3,
            ["PHI_KEYWORD", "MRN"],
            {"PHI_KEYWORD": 2, "MRN": 1},
            notes="2 PHI keyword surfaces: ICD-10 code + medication context.",
        )
    )

    # 4: API secret + email (debug ticket)
    prompt_4 = (
        f"Debug help: AWS access key {_synthetic_aws_access_key(rng)} is "
        f"failing, error logs going to {fake.email()}. Auth returns 403."
    )
    records.append(
        _make_record(
            "mixed",
            4,
            "mixed",
            "aws_key_email",
            prompt_4,
            ["AWS_ACCESS_KEY", "EMAIL"],
            {"AWS_ACCESS_KEY": 1, "EMAIL": 1},
        )
    )

    # 5: Address + phone + IBAN (international onboarding)
    prompt_5 = (
        f"New customer onboarding — ship to "
        f"{', '.join(fake.address().splitlines())}, "
        f"phone {fake.phone_number()}, payments to IBAN {fake.iban()}."
    )
    records.append(
        _make_record(
            "mixed",
            5,
            "mixed",
            "address_phone_iban",
            prompt_5,
            ["ADDRESS", "PHONE", "IBAN"],
            {"ADDRESS": 1, "PHONE": 1, "IBAN": 1},
        )
    )

    return records


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_corpus(seed: int) -> list[CorpusRecord]:
    """Build the full 100-record corpus deterministically from ``seed``.

    Args:
        seed: PRNG seed. Same seed produces byte-identical output across runs.

    Returns:
        Exactly ``EXPECTED_RECORD_COUNT`` CorpusRecord objects.

    Raises:
        ValueError: If the generated corpus has the wrong total count or
            contains duplicate ids.
    """
    fake = Faker(DEFAULT_LOCALES)
    Faker.seed(seed)
    rng = random.Random(seed)  # noqa: S311

    records: list[CorpusRecord] = []
    records.extend(generate_identifiers(fake, rng))
    records.extend(generate_financial(fake, rng))
    records.extend(generate_contact(fake, rng))
    records.extend(generate_names(fake, rng))
    records.extend(generate_api_secrets(rng))
    records.extend(generate_phi(fake, rng))
    records.extend(generate_mixed(fake, rng))

    if len(records) != EXPECTED_RECORD_COUNT:
        msg = f"Expected {EXPECTED_RECORD_COUNT} records, got {len(records)}"
        raise ValueError(msg)

    ids = [r.id for r in records]
    if len(set(ids)) != len(ids):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        msg = f"Duplicate ids in corpus: {duplicates}"
        raise ValueError(msg)

    return records


def write_jsonl(records: list[CorpusRecord], output_path: Path) -> None:
    """Write records to a JSONL file, one record per line, sorted keys.

    Sorting keys ensures deterministic byte output across Python versions.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fp:
        for record in records:
            fp.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = argparse.ArgumentParser(
        description="Generate the LLM Pre-Send Leakage Benchmark corpus.",
        epilog=(
            "Output is deterministic for a given --seed. "
            "Default seed (20260623) is locked at v1.0.0."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"PRNG seed (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    LOGGER.info("Generating corpus with seed=%d", args.seed)
    records = build_corpus(args.seed)

    LOGGER.info("Writing %d records to %s", len(records), args.output)
    write_jsonl(records, args.output)

    LOGGER.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
