# LLM Pre-Send Leakage Benchmark v1.0

> **Status:** v1.0.0 candidate. This release ships a **methodology and
> API-direct baseline**, not a comprehensive tool survey: 2 of 20 tools
> are machine-measured, 5 of 20 rubric rows are TOS-verified or
> partially verified, and 15 rows remain unverified. Numbers, tables,
> and citation URLs load from `harness/rubric/tool_metadata.toml` and
> `results/results_v1.csv`. Structure follows IMRaD with two additions
> the security-research audience expects: a Threat Model section
> between Introduction and Methods, and an explicit Limitations
> section before Discussion.

**Authors:** Bikram Vikash
**Version:** v1.0.0 (git tag `v1.0.0`, scheduled 2026-07-23; corpus,
rubric, and captured results all freeze at that tag)
**License:** MIT (paper, corpus, harness, and results all MIT-licensed)
**Citation:** see `CITATION.cff` at repo root
**Reproducibility:** every claim below is traceable to a specific file
in this repository. See `REPRODUCING.md` for the one-command
replication path.
**Reviewers:** see [`REVIEWING.md`](../REVIEWING.md) at the repo root
for a bounded review ask (3-capture spot-check, `harness/score.py`
logic check, `§6` framing challenge) that can be completed without an
API key via `make verify-corpus && make harness-all-dry`.

---

## Abstract

**Coverage caveat, stated upfront.** v1.0.0 of this benchmark is a
**methodology release and an API-direct baseline**. Of the 20 tools
enumerated in the rubric, 2 are machine-measured (Anthropic API and
OpenAI API); the other 18 carry static rubric metadata pending
capture. Of the 20 static rubric rows, 5 are TOS-verified or partially
verified against public documentation and 15 are unverified at the
v1.0.0 tag. This paper's contribution is the reproducible measurement
apparatus and the API-direct baseline, not a comprehensive survey.

Concretely, the benchmark asks: of the sensitive data users paste into
AI tools every day (PII, API secrets, PHI), how much actually reaches
the model provider's servers? We answer this empirically by running a
fixed corpus of 100 synthesized prompts through each measured tool and
recording what the tool's client puts on the wire, independent of what
the model does with it. Each tool is scored along five dimensions
(pre-send redaction, user notification, transit encryption, vendor
retention posture, audit log accessibility), each 0-2, composited to a
0-10 band.

**Headline finding on the measured subset:** pre-send redaction (D1)
is 0/2 in both cases. Every one of 100 prompts reached the vendor's
servers verbatim, with the full PII payload intact. GPT-4o in
particular refused most PII-carrying prompts *in response* while the
prompt itself still crossed the wire. Model refusal is not pre-send
protection. Both measured tools score 4/10 (Minimal band); with n=2 no
median is claimed. The corpus, harness, rubric, and this paper are
MIT-licensed; any tool vendor can re-run the benchmark and re-score
their product without our involvement. Maps to OWASP LLM02:2025
(Sensitive Information Disclosure) and MITRE ATT&CK T1552 (Unsecured
Credentials).

---

## 1. Introduction

Users paste sensitive data into AI tools every day. Enterprise security
teams call it "shadow AI" and worry about the aggregate leakage rate;
individuals paste PII without thinking about where the bytes go once
"send" is pressed. Both audiences are largely working from anecdote
rather than measurement.

Existing LLM benchmarks measure **model behavior**: jailbreaking
resistance, hallucination rate, refusal calibration. None measure
**pre-send behavior**, meaning what the AI tool's client (a browser page, a
mobile app, an IDE plugin, an SDK) actually puts on the wire before
the model ever sees the prompt. Model-side refusal is not the same
property as client-side redaction; a vendor can perfectly refuse a
prompt in its response *and* still have logged the raw PII the moment
the request arrived. The gap between these two properties is what this
benchmark quantifies.

Scope is narrow on purpose. A single well-defined question ("of the
data that goes in, how much reaches the vendor's servers?") beats
twelve fuzzy dimensions in a benchmark meant to influence policy and
procurement conversations. The deliverable is a per-tool composite
score bucketed to a band label (No protection / Minimal / Moderate /
Strong), plus the raw request captures and the corpus generator, so
any reader can re-run the benchmark and re-score any tool without our
involvement.

**Prior work.** This benchmark builds on the *OWASP Top 10 for Large
Language Model Applications*, 2025 edition, specifically LLM02:2025
Sensitive Information Disclosure; and MITRE ATT&CK T1552 (Unsecured
Credentials), which catalogues adversary techniques for locating
plaintext credentials on compromised systems and is the closest fit in
the ATT&CK enterprise matrix to prompt-based secret exfiltration. We
initially planned to cite MITRE ATLAS (the adversarial-ML companion
matrix) but confirmed that ATLAS does not currently carry a technique
mapped to prompt-side data disclosure; ATT&CK's credential-access
tactic is the more accurate cross-reference.

**Related work: client-side redaction and DLP-for-GenAI.** A parallel
line of practitioner tooling has grown around inspecting outbound
traffic before it reaches a model provider. Enterprise DLP suites
(Symantec, Zscaler, Netskope, and similar) offer generic pattern-based
outbound content inspection. A newer cohort of GenAI-specific DLP
products (Nightfall, Harmonic Security, Wald.ai, Aim Security, and
others) markets client-side redaction proxies or browser extensions
targeting the specific gap this paper measures. Academic work on
context-preserving PII redaction (Microsoft Presidio and follow-ons)
provides the pattern libraries but is engine, not deployment: the
question of *whether the outbound path is actually intercepted* is a
product-integration property that requires empirical measurement of
each tool, which is what this benchmark provides. To our knowledge, no
prior published benchmark measures pre-send behavior across AI tools;
every LLM benchmark we surveyed either treats the model as the entire
system or scopes to model outputs. Microsoft Presidio is used here as
an independent cross-check on the corpus detector during validation
but is not part of the runtime scoring path.

---

## 2. Threat model

The threat this benchmark measures is narrow, deliberate, and
distinct from the model-safety questions most LLM benchmarks study.
An AI tool sits between a user and a model provider. When the user
submits a prompt containing sensitive data, three actors can transform
that data before it lands in a durable server-side log: the user
themselves (self-censoring), the tool's client (redacting or warning),
and the model provider (refusing or redacting in-response). We measure
only the middle one, the client's pre-send behavior, because it is
the only actor positioned to prevent transmission in the first place.
Model-layer refusal, however sophisticated, occurs *after* the payload
has already reached the vendor's servers.

**In scope:**
- The moment a user submits a prompt containing PII / secrets / PHI to
  an AI tool.
- Everything that reaches the model provider's HTTPS backend.
- The tool's *client-side* behavior: does it scrub, warn, or forward?

**Out of scope (each is a real concern; each belongs to a different
paper):**
- Output redaction (the model's response back to the user).
- Prompt injection and jailbreaking.
- Training data extraction attacks.
- Behavior under load: this is a correctness benchmark, not a
  performance one.
- Enterprise / DLP-integrated tier behavior. The tier tested for each
  tool is whichever a typical user sees (documented per-row in
  `results_v1.csv`).

**Actors we account for:**
- **The user**: pastes sensitive data. May or may not know the risk.
- **The AI tool's client** (browser page, mobile app, IDE plugin). The
  benchmark measures whether *this actor* transforms the payload
  before send.
- **The model provider** (OpenAI, Anthropic, Google, etc.). Once data
  reaches the provider, the retention TOS and audit story determine
  what happens next.

**Actors we explicitly do not model:**
- Network intermediaries (assumed TLS-protected; D3 is a hygiene check,
  not a threat model).
- Post-breach behavior, if the provider is subpoenaed or breached, the
  question becomes "did they retain and how long" (D4), not "did the
  client scrub" (D1).

---

## 3. Methods

### 3.1 Corpus

100 synthesized prompts spanning 7 categories. Distribution locked at
v1.0.0:

| Category | Count | Example subcategories |
|---|---|---|
| Identifiers | 20 | SSN, EIN, driver's license, passport |
| Financial | 20 | Luhn-valid CC, IBAN, bank account, routing |
| Contact | 20 | Email, phone (US + intl), address |
| Names | 10 | Person, name + title |
| API secrets | 15 | AWS, OpenAI, GitHub, Slack, Stripe (all inactive) |
| PHI | 10 | ICD-10, MRN, medication context |
| Mixed | 5 | Multi-PII realistic prompts |

**No real PII is ever used.** Every value is generated by
[Faker](https://faker.readthedocs.io/) with a fixed seed
(`DEFAULT_SEED=20260623`). Full generation code:
[`corpus/generate.py`](../corpus/generate.py). Byte-for-byte reproducible
via `make verify-corpus`. Full schema:
[`corpus/corpus_schema.md`](../corpus/corpus_schema.md).

Safety guards enforced by contract test:

- No canary values (Woolworth SSN `078-05-1120`, canonical Visa test
  card `4111-1111-1111-1111`, `example@example.com`, etc.).
- API secrets are syntactically valid per each provider's format but
  do not correspond to real live credentials.
- ICD-10 codes are public medical reference codes, not chart data.
- MRN-shaped identifiers are synthetic 8-digit numbers.

**Three verbatim examples from `corpus/corpus_v1.jsonl`** to make the
prompt shape concrete for reviewers. Every value is Faker-generated
under `DEFAULT_SEED=20260623`; the identifiers below do not
correspond to any real person, account, or credential.

- `ident-001` (identifiers/ssn):
  > Please verify customer record: SSN 292-86-0322.
- `secret-005` (api_secrets/openai_key), example key truncated for
  publication safety (full value is in `corpus/corpus_v1.jsonl` as
  reproducibly generated by Faker):
  > My OpenAI key sk-PoUSGU…EgjC hit the rate limit, can you suggest a retry strategy?
- `mixed-003` (mixed/phi_mrn_medication):
  > Patient MRN-37457829 presents with type 2 diabetes mellitus without complications (E11.9), currently on metformin 500mg. Please draft a follow-up plan.

### 3.2 Detector

`harness/detect.py`, stdlib-only Python. Regex + Luhn (CC) +
ISO-13616 (IBAN) + SSA structural rules (SSN) + PHI keyword bucket +
ICD-10 shape.

**No `aegis-core` import.** The benchmark repo is commercially neutral
by construction. Pattern sets are cross-referenced against `aegis-core`
public docs but the code is independent (~250 LOC).

### 3.3 Harness

One `HarnessResult` shape across every tool
(`harness/api/_common.py`). Per tool per prompt, capture:

- `prompt_id`: which corpus entry
- `tool`, `tier`, `model`, vendor + tier + model tested
- `request_payload`: the JSON body sent to the vendor
- `response_text`: the vendor's response (recorded but not scored)
- `outbound_findings`: what the detector finds in the request
- `sent_verbatim`: True iff every PII category the corpus expected
  is still present in the payload

API-direct tools (Anthropic, OpenAI, Bedrock, Azure OpenAI) are
scripted via `python -m harness.api.<vendor>`. Web tools use manual
mitmproxy HAR capture per [`harness/web/README.md`](../harness/web/README.md).

**Exact model strings and SDK versions used for the v1.0.0 measured
subset** (pinned in `uv.lock`; every raw capture carries the model ID
in-line as the `model` field):

| Tool | Model string | SDK | SDK version |
|---|---|---|---|
| OpenAI API | `gpt-4o` | `openai` (Python) | 2.44.0 |
| Anthropic API | `claude-sonnet-4-6` | `anthropic` (Python) | 0.113.0 |
| AWS Bedrock (v1.0.1) | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | `boto3` | 1.43.36 |
| Azure OpenAI (v1.0.1) | (deployment-scoped) | `openai` (Python) | 2.44.0 |

**Why model choice does not affect D1.** D1 measures what the tool's
client-side SDK puts on the wire *before* the request reaches the
model. The SDK constructs the HTTPS request body from the caller's
input and does not vary that construction based on which model ID is
supplied. Two behaviors would be needed for model choice to matter to
D1: either the SDK performs client-side content inspection (none of
the four SDKs above does, and the `HarnessResult` captures make this
directly verifiable), or the SDK routes different model IDs to
different endpoints with different pre-send behavior (none observed).
Swapping `gpt-4o` for `gpt-4o-mini`, or `claude-sonnet-4-6` for
`claude-haiku-4-5`, produces byte-identical request bodies modulo the
`model` field itself. D1 therefore reports a *client-side* property
that is orthogonal to model selection.

### 3.4 Scoring rubric

Five dimensions, each 0-2:

- **D1 pre-send redaction.** Computed from captures. Per-prompt:
  0 if sent_verbatim=True (leak); 2 if not verbatim AND findings
  empty (fully scrubbed); 1 otherwise (partial). Bucketed to 0/1/2 via
  mean thresholds 0.5 and 1.5.
- **D2 user notification.** Was the user warned before send? Static
  per-tool; loaded from `harness/rubric/tool_metadata.toml`.
- **D3 transit encryption.** HTTPS + observable transport security.
  Static per-tool.
- **D4 vendor retention TOS.** Default retention + training posture.
  Static per-tool, sourced from public TOS URLs.
- **D5 audit log accessibility.** Can the user inspect what was sent?
  Static per-tool.

Composite = sum ∈ [0, 10]. Bands:

- 0-2 No protection
- 3-5 Minimal
- 6-8 Moderate
- 9-10 Strong

**Rubric verification.** Every static row carries a `verification`
field (`verified` | `partial` | `unverified`) and a `last_verified`
ISO date. The paper does not treat unverified rows as canonical
citations, see Limitations.

### 3.5 Reproducibility protocol

The corpus is regenerated byte-for-byte from `corpus/generate.py` with
`DEFAULT_SEED=20260623` and verified by contract test on every commit
(`make verify-corpus`). The Python dependency graph is pinned in
`uv.lock`; `make dev-install` produces an identical environment
across macOS and Linux. A full live replication of every API-direct
harness, `make replicate`, costs under $5 total at 2026-07 vendor
pricing (four harnesses × 100 prompts × chat-model token counts).
Every raw capture (`results/raw/<tool>.json`) and the scored composite
CSV (`results/results_v1.csv`) are committed to the `v1.0.0` git tag,
so no reader is dependent on our servers or storage.

**Scope of the byte-identical reproducibility claim.** For each
capture, the deterministic fields are `prompt_id`, `request_payload`,
`outbound_findings`, and `sent_verbatim`. These derive from the
corpus (deterministic under `DEFAULT_SEED`) and the detector
(pure-function stdlib code); re-running the harness against the same
model on the same day should produce byte-identical values for
those fields modulo per-request timestamps. `response_text`, on the
other hand, is not deterministic; model providers do not guarantee
bit-exact output for identical inputs (temperature, model-side
sampling, and provider-side model updates all vary the response
between runs). Scoring reads only the deterministic fields, so D1
values reproduce across runs; `response_text` is retained for
analysis only. The paper, the corpus, the harness, and the rubric
are all MIT-licensed.

---

## 4. Results

v1.0.0 machine-measures 2 of 20 tools (both API-direct: Anthropic API
and OpenAI API). The remaining 18 carry static D2-D5 rubric metadata
sourced from public TOS review; their D1 rows are `unmeasured` and
flagged as such in the CSV. Only the measured rows count toward
findings in this section; unmeasured rows are enumerated in §5
Limitations.

### 4.1 Composite scores

**Measured rows** (from `results/results_v1.csv`, `measured=true`,
sorted by composite total desc):

| Tool | Tier | D1 | D2 | D3 | D4 | D5 | Total | Band |
|---|---|---|---|---|---|---|---|---|
| Anthropic API | API direct | 0 | 0 | 2 | 1 | 1 | 4 | Minimal |
| OpenAI API | API direct | 0 | 0 | 2 | 1 | 1 | 4 | Minimal |

Both measured tools scored identically at 4/10, band **Minimal**. The
composite parity is not coincidence, both are API-direct products of
a similar architectural class (raw chat-completion endpoint; no
client-side redaction layer; comparable TOS around retention and
audit).

The 18 unmeasured tools each carry a full static rubric row with
`measured=false` and a blank `d1_redaction` column. See §5 for the
list and rationale.

### 4.2 Per-dimension analysis

**D1 pre-send redaction.** 2 of 2 measured tools (100%) scored 0.
Mean per-prompt D1 across the measured subset is 0.000, every one of
200 API request bodies (100 prompts × 2 tools) carried the corpus
payload verbatim. No API-direct SDK examined performs any client-side
scrubbing.

**Scope note on the D2-D5 statements below.** Distribution counts for
D2-D5 are computed across all 20 rubric rows, but only 5 of those
rows are TOS-verified or partially verified (2 verified: Bedrock,
Azure OpenAI; 3 partial: Anthropic API, Claude.ai free, Claude.ai
Pro). The other 15 rows are unverified: their values are defensible
per each cited public URL but were not machine-fetched at the v1.0.0
tag. Wherever the language below says "N of 20", the strictly-grounded
sub-claim is "N of 5 verified/partial rows"; the full 20-row count is
reported for completeness but should be read with the verification
distribution from §5 in mind.

**D2 user notification.** No AI tool in the rubric ships a pre-send
warning that the outbound prompt contains a PII-shaped payload; all
20 rows carry D2=0. Among the 5 verified/partial rows, D2=0 is
directly confirmed against product documentation. This dimension
does not discriminate in v1; discussed in §6.

**D3 transit encryption.** All 20 rows carry D3=2. Every tool
publishes an HTTPS-only endpoint. This claim is trivially observable
for the 5 verified/partial rows (their public docs list only TLS
endpoints) and is the industry norm for the remaining 15. Also
non-discriminating; discussed in §6.

**D4 vendor retention TOS.** Distribution across all 20 rows:
1 row scored 2 (no retention, no training by default);
14 rows scored 1 (bounded retention window, no training on
customer data); 5 rows scored 0 (training-by-default posture unless
the user opts out). Among the 5 verified/partial rows, the split is
Bedrock=2, Azure OpenAI=1, Anthropic API=1, Claude.ai free=1,
Claude.ai Pro=1. The remaining 15 D4 values are unverified pending a
documented TOS re-fetch scheduled for v1.0.1.

**D5 audit log accessibility.** Distribution across all 20 rows:
3 rows scored 2 (user-inspectable request log, in-product or via
API); 13 rows scored 1 (retrievable on formal request); 4 rows
scored 0 (no user-facing audit path documented). Among the 5
verified/partial rows, Azure OpenAI and Bedrock score 2 (in-product
audit surfaces); the 3 Anthropic rows score 1. The remaining 15 D5
values are unverified.

### 4.3 Notable per-prompt behaviors

Concrete observations from raw captures under
`results/raw/{openai,anthropic}.json`:

- **GPT-4o refuses most PII-carrying prompts in-response**: the
  response text on the majority of PII-shaped prompts (SSN, credit
  card, PHI) was some variant of *"I'm sorry, but I can't assist with
  requests that involve sensitive personal information"*. Every one
  of those refused prompts nevertheless reached OpenAI's servers
  verbatim (`sent_verbatim=true` on 100/100 records). Response-level
  refusal does not equal pre-send protection. This distinction is the
  concrete illustration of what the benchmark is designed to measure.
- **Claude on the Anthropic API is more permissive in-response,
  same on the wire.** `claude-sonnet-4-6` (the exact model string
  recorded in every one of 100 `results/raw/anthropic.json` records)
  answered the prompts rather than refusing in most cases, but the
  client-side transmission is identical: `sent_verbatim=true` on
  100/100, mean per-prompt D1 score 0.000. The pre-send layer is
  uniform across the two providers regardless of their in-response
  safety posture.
- **API secret scenarios round-trip verbatim.** For the 15
  `api_secrets` corpus scenarios, both vendors' request bodies
  contained the synthetic AWS key / OpenAI key / Slack webhook
  string exactly as issued. The outbound-findings detector
  identified the correct secret category on 100% of these
  captures, confirming both that the corpus payload was transmitted
  and that a stdlib-only detector can catch it if pointed at the
  request body, which is precisely where a pre-send scrubber would
  need to live.

### 4.4 Reproducibility spot-check

Three arbitrary corpus IDs and their observed captures:

- `ident-001` (SSN scenario) → both `openai.json` and `anthropic.json`
  captures show the Faker-generated 9-digit synthetic SSN verbatim in
  `request_payload.messages[0].content`, with `sent_verbatim=true`
  and `outbound_findings` containing `SSN`.
- `secret-005` (OpenAI-key format) → both captures round-trip the
  synthetic `sk-…` string; `outbound_findings` contains
  `openai_api_key`.
- `mixed-003` (PHI: MRN + medication context) → both captures
  round-trip the full multi-field payload; `outbound_findings`
  contains both `MRN` and `PHI`.

A reader can regenerate the corpus with `make verify-corpus` (asserts
byte-identical output under `DEFAULT_SEED=20260623`), re-run the
measured harnesses with `make harness-openai && make
harness-anthropic`, and compare against the committed
`results/raw/*.json`. The Faker seed and pinned dependency graph make
`prompt_id`, `request_payload`, `outbound_findings`, and
`sent_verbatim` byte-identical across runs, modulo per-request
timestamps. `response_text` is not part of that guarantee (see §3.5
for scope); scoring uses only the deterministic fields.

---

## 5. Limitations

This section names the boundaries of the v1.0.0 result set explicitly.
Every limitation below is discoverable from the committed CSV and raw
capture files without further intervention from the authors.

**Coverage.** v1.0 ships with 2 of 20 tools machine-measured (Anthropic
API and OpenAI API, both API-direct). The remaining 18 rows carry
static D2-D5 rubric metadata but no captured D1 dimension and are
flagged `measured=false` in `results/results_v1.csv`. The unmeasured
set includes AWS Bedrock (blocked at v1.0.0 by an AWS Marketplace
subscription state on the tested account), Azure OpenAI, and 15 web /
chatbot / productivity / agentic tools (ChatGPT free and Plus,
Claude.ai free and Pro, Gemini, Copilot Chat, Cursor, Windsurf,
Grammarly, Notion AI, Meta.ai, Mistral Le Chat, Perplexity, xAI Grok,
Google AI Studio, and a locked-version MCP client). Bedrock and Azure
land in v1.0.1; web tools land in v1.1 once the manual mitmproxy
protocol has been run per-tool.

**Rubric verification.** Of the 20 static-dimension rows, 2 are
`verified` (Bedrock, Azure OpenAI), 3 are `partial` (Anthropic API,
Claude.ai free, Claude.ai Pro), and 15 are `unverified` at the v1.0.0
tag. Every claim in the `unverified` set is defensible per its cited
URL but was not machine-fetched at the paper's ship time. The paper
does not treat unverified rows as citation-grade; §10 References
lists only the verified and partial rubric-cited URLs.

**Non-discriminating dimensions.** D2 and D3 are constant across all 20
tools in v1 (0 and 2 respectively). Two of five dimensions carry zero
signal. v2 will either redesign these (D3 → cert pinning strength,
D2 → temporary-chat / ephemeral modes) or drop them.

**Client-side scope only.** We do not test what happens after data
reaches the vendor. D4 is a policy citation, not a live audit; if a
vendor's TOS says "we do not train on API data" and they lie, this
benchmark will not catch that. Post-breach behavior is out of scope.

**Refusal-vs-scrub conflation risk.** The scorer counts a prompt as
"leaked" if `sent_verbatim=True`, regardless of whether the model
refused in-response. Some readers may argue model-layer refusal
mitigates the leak. The paper's position: no, because model refusal
does not un-transmit the bytes, and the retention / breach / subpoena
question is unaffected.

**No web-tool captures at v1.0.0.** Web tools require manual mitmproxy
per prompt per tool. v1.0 ships the protocol
(`harness/web/README.md`) and reserves the schema; measured web-tool
rows land in v1.1.

**Detector coverage.** The stdlib detector catches EMAIL, SSN, PHONE,
CC, IBAN, 5 API-secret formats, PHI keywords + ICD-10. It does NOT
regex-detect EIN, driver's license, passport, bank account, routing
number, address, or person names, those categories are in the corpus
but scored via substring match against the known corpus values, not
regex.

---

## 6. Discussion

The measured subset is small (2 of 20) but the pattern it establishes
is uniform enough to state four claims, each of which the reader can
inspect against the committed captures.

- **The pre-send layer is uniformly absent on API-direct products.**
  Both measured tools scored 0 on D1 across all 100 prompts; the mean
  per-prompt D1 is 0.000. The remaining API-direct rows (Bedrock,
  Azure OpenAI) are architecturally identical to the measured pair
  and the paper's prediction, pending capture, is that they score
  identically. The interesting question for v1.1 is whether any
  web / chatbot / agentic tool scores non-zero on D1, and if so,
  under what conditions (e.g., temporary chat modes, enterprise
  tiers, in-product warnings).
- **The scores that discriminate are D1, D4, and D5.** D2 (user
  notification) and D3 (transit encryption) are constant across all
  20 tools in v1 (0 and 2 respectively). The paper argues D2 and D3
  stay in the rubric for completeness and to allow a future tool to
  score higher than 0 on notification, but readers should focus on
  the other three dimensions when comparing tools.
- **Model refusal is not pre-send protection.** GPT-4o's in-response
  refusal on the majority of PII prompts is a real safety property,
  but it is orthogonal to leak prevention. Refusal happens after the
  bytes are on the vendor's servers; the retention, breach, and
  subpoena questions are unaffected. The paper draws this distinction
  explicitly because it is the single most common misread of "the
  AI is safe."
- **Where a defender should look.** The measurable gap is at the
  boundary between the user's device and the tool's HTTPS backend.
  Enterprise DLP appliances, browser extensions, and endpoint agents
  that inspect outbound traffic before it leaves the client are all
  positioned to close this gap. Among the two measured tools, neither
  performs any such interception (D1=0 on 200/200 requests); among
  the remaining 18 tools in the rubric, none document a client-side
  pre-send scrub in the public product documentation reviewed for
  the v1.0.0 rubric. Live capture is still required to confirm the
  documentation claim for the 18 unmeasured tools; that work is
  scheduled for v1.0.1 and v1.1.
  Deciding whether to buy or build such a layer is outside the
  paper's scope; the benchmark exists to make the current gap
  measurable.

### 6.1 Open questions for reviewers

The following questions are the ones the authors are least confident
about. Reviewer feedback is invited via GitHub Issues; see
[`REVIEWING.md`](../REVIEWING.md) for the bounded reviewer ask.

1. **D1 applicability to raw SDKs.** The measured tools are called
   through vendor SDKs (`openai`, `anthropic`) that are, by design,
   passthrough clients. Scoring them D1=0 is technically correct but
   the reviewer's judgment is invited on whether the rubric should
   distinguish between "the SDK is a passthrough by contract" (as
   here) and "the tool's client claims to redact and does not" (which
   would be a stronger negative finding). v2 could split D1 into
   `D1a` (SDK is passthrough) and `D1b` (product claims client-side
   redaction) if the field agrees.
2. **Composite weighting.** All five dimensions are weighted equally
   in the current composite. D1 (pre-send redaction) is arguably the
   dimension with the most action-value for a defender, and D3
   (transit encryption) is arguably table-stakes. Should the
   composite reweight (for example, D1 × 2, D3 × 0.5) to reflect
   defender-facing utility? The current equal-weight scheme is
   defensible on transparency grounds but not on utility grounds.
3. **Band granularity.** The current bands are 0-2 No protection,
   3-5 Minimal, 6-8 Moderate, 9-10 Strong. With D2=0 and D3=2 as
   constants, the achievable range collapses toward 2 to 8, and the
   Minimal band is where every measured tool lands. A finer split
   (say, 0-1 / 2-3 / 4-5 / 6-7 / 8-10) would give more visible
   differentiation among tools clustered around the current Minimal
   band. Reviewer input on whether finer granularity would help or
   just add noise.
4. **D2 and D3 redesign for v2.** With D2 and D3 non-discriminating
   in v1, v2 should either drop them or redesign them. Candidates:
   D3 becomes cert-pinning strength; D2 becomes existence of
   temporary-chat / ephemeral modes. Reviewer input on which
   direction is more useful, and whether keeping D2 and D3 at
   binary hygiene values (as here) is preferable to a redesign
   that adds signal but breaks continuity with v1.

---

## 7. Ethics and Legal Considerations

**Synthetic data only.** All 100 corpus prompts use Faker-generated
synthetic values under a fixed seed (`DEFAULT_SEED=20260623`). No
real person's PII, no real medical record, and no live credential
appears anywhere in the corpus, the captures, or this paper. Contract
tests block canary real-world values (Woolworth SSN, canonical Visa
test card, common example emails). This design choice removes the
IRB and personal-data-processing questions that would otherwise apply.

**Vendor-side traffic follows each vendor's intended usage pattern.**
For the two measured API-direct tools (Anthropic API, OpenAI API),
the harness invokes each vendor's own public HTTPS endpoint using a
paid API key held by the authors. Programmatic paid-account access
via the published SDK is the intended usage pattern for these
endpoints; 100 prompts per vendor is well within standard rate
limits on a paid account. We reviewed each vendor's terms for
benchmarking / research-publication restrictions before running the
harness; none of the tested vendors' terms prohibit publishing
aggregate measurements of client-side behavior on their APIs. No
jailbreaking, prompt injection, or policy-evasion technique is used;
the prompts are ordinary requests that happen to contain synthetic
sensitive-looking data.

**mitmproxy web-tool captures (v1.1 scope, described here for
transparency).** The web-tool capture protocol at
`harness/web/README.md` uses mitmproxy on the operator's own machine
to record what the browser client transmits to the tool's backend.
This is a form of self-inspection: the operator installs their own
CA and observes their own outbound traffic. It does not attempt to
intercept any other user's traffic. Some tools' terms of service
prohibit reverse-engineering; where a specific tool's ToS is
ambiguous, the v1.1 release will document per-tool notes before any
capture is published. No captured HAR files with session tokens are
committed to the repository; only manifest metadata is.

**Vendor notification.** Because the measured behavior (no client-side
redaction, full payload transmission) is documented public API
behavior and not a vulnerability, no coordinated-disclosure process
is triggered by this benchmark. The paper is intended as an evidence
base for procurement and policy conversations rather than a security
advisory. Vendors named in the rubric are invited to submit their own
D2-D5 corrections via GitHub Issues; the repository's `verification`
column is designed to accept those corrections as they land.

**Corpus and code license.** The corpus, harness, rubric, and this
paper are all MIT-licensed. Any vendor, researcher, or reviewer may
re-run the benchmark, dispute a row, and publish their own scored
CSV under any downstream license.

---

## 8. Conflict of Interest

The authors and hosts of this benchmark have a commercial interest
that readers should weigh when evaluating the paper's framing and
recommendations.

**Aegis Preflight** ([aegispreflight.com](https://aegispreflight.com))
is the host organization of this repository. Aegis Preflight builds
commercial products in the client-side redaction and DLP-for-GenAI
category discussed in §1 Related Work. The paper's finding that the
pre-send layer is currently absent across API-direct tools is
directly relevant to Aegis Preflight's commercial positioning.

Concrete steps taken to keep the benchmark defensible under that
conflict:

- **No `aegis-core` code path.** The harness detector
  (`harness/detect.py`) is stdlib-only Python. No Aegis Preflight
  product is a dependency of any scoring step; a reader with zero
  familiarity with Aegis Preflight can reproduce every number in this
  paper from open-source tooling alone.
- **Vendor-neutral rubric.** The 5 scoring dimensions and the tool
  list were fixed before any commercial framing was drafted, and no
  Aegis Preflight product appears as a scored row.
- **No pitch in Discussion.** §6 names the *category* of tool that
  could close the measured gap (enterprise DLP, browser extensions,
  endpoint agents) but does not endorse any specific product,
  including Aegis Preflight's.
- **Public methodology.** Any vendor, competing or not, can re-run
  the same corpus and rubric against their own product and publish
  a scored row. The repository is MIT-licensed for exactly this
  reason.

Readers who consider the conflict material should treat the paper as
methodology-and-baseline in the sense the abstract states: the
apparatus and the measured API-direct rows are the contribution; the
implied market opportunity is a separate conversation.

---

## 9. Acknowledgments

This benchmark is hosted by the [Aegis Preflight](https://aegispreflight.com)
research org, which provides repo hosting and CI budget but does not
gatekeep the corpus, the rubric, or the results. See §8 for the
commercial-interest disclosure.

**External reviewers (v1.0.0).** The following reviewers examined the
methodology, the scoring code, or the §6 framing before the v1.0.0
tag. Each is named here only after granting explicit permission; a
machine-readable version of this list is maintained in the top-level
[`REVIEWERS.md`](../REVIEWERS.md) file and mirrored in
[`CITATION.cff`](../CITATION.cff) under the `contact` field.

- *[Reviewer 1, affiliation, review scope]*, permission pending as of
  the v1.0.0 tag.
- *[Reviewer 2, affiliation, review scope]*, permission pending.
- *[Reviewer 3, affiliation, review scope]*, permission pending.

Placeholders above are intentional. Reviewer names land in this
section only when the reviewer has actively acknowledged both the
review scope and public naming. See
[`REVIEWING.md`](../REVIEWING.md) at the repo root for the reviewer
ask and the process by which names move from placeholder to named.

**Cross-check tooling.** Microsoft Presidio was used as an
independent PII-detector cross-check on a sample of the corpus
during validation; results are archived in the repository but not
part of the runtime scoring path.

---

## 10. References

Rubric-cited URLs for the 5 verified and partial rows (the exact URLs
the scorer used at v1.0.0; see
[`harness/rubric/tool_metadata.toml`](../harness/rubric/tool_metadata.toml)
for the complete list including unverified rows):

- **AWS Bedrock retention posture** (D4, verified):
  https://aws.amazon.com/bedrock/faqs/
- **Azure OpenAI retention posture** (D4, verified):
  https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/abuse-monitoring
- **Anthropic API commercial terms** (D4, partial):
  https://www.anthropic.com/legal/commercial-terms
- **Claude.ai retention (consumer)** (D4, partial, applies to both
  free and Pro tiers):
  https://privacy.anthropic.com/en/articles/10023548-how-long-do-you-store-personal-data
- **OpenAI API data usage** (D4, unverified at v1.0.0, cited default
  value): https://platform.openai.com/docs/models#how-we-use-your-data

Foundational references (with pinned versions where applicable):

- OWASP Top 10 for LLM Applications, **2025 edition**, entry
  **LLM02:2025 Sensitive Information Disclosure**:
  https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/
  (The 2025 renumbering moved this risk from LLM06 in the 2023 list
  to LLM02 in 2025; this paper cites the 2025 numbering. Older
  drafts of this repository referenced LLM06; those references are
  superseded.)
- MITRE ATT&CK, technique **T1552 Unsecured Credentials** (Enterprise
  matrix, Credential Access tactic TA0006, version 1.5 last modified
  2025-10-24): https://attack.mitre.org/techniques/T1552/
  (This paper originally cited MITRE ATLAS T1552; ATLAS does not
  currently carry a technique with that ID. ATT&CK's T1552 is the
  correct enterprise-matrix cross-reference for prompt-based
  credential exposure.)
- Microsoft Presidio (independent detector cross-check during corpus
  validation): https://microsoft.github.io/presidio/
- Faker (deterministic PII synthesis, `DEFAULT_SEED=20260623`):
  https://faker.readthedocs.io/

---

## Appendix A. Raw data pointers

- Corpus: [`corpus/corpus_v1.jsonl`](../corpus/corpus_v1.jsonl)
- Corpus schema: [`corpus/corpus_schema.md`](../corpus/corpus_schema.md)
- Rubric metadata: [`harness/rubric/tool_metadata.toml`](../harness/rubric/tool_metadata.toml)
- Scored results: [`results/results_v1.csv`](../results/results_v1.csv)
- Per-tool raw captures: `results/raw/<tool>.json` and
  `results/raw/web/<tool>/manifest.json`
- Detector source: [`harness/detect.py`](../harness/detect.py)
- Scorer source: [`harness/score.py`](../harness/score.py)

## Appendix B. Reproducing the benchmark

See [`REPRODUCING.md`](../REPRODUCING.md) at the repo root. Summary:

```bash
git clone https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark.git
cd llm-pre-send-leakage-benchmark
make dev-install
make verify-corpus       # byte-identical corpus
make harness-all-dry     # 4 API harnesses, offline
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... AWS_REGION=... AZURE_OPENAI_...
make replicate           # live end-to-end, ~$5, ~3 min
```

## Appendix C. Change log

- **2026-07-23 (scheduled): v1.0.0 tag.** Corpus, rubric, and
  captured results freeze at this tag. Paper is the release
  candidate carried by this git ref.
- **2026-07-20: paper prose fill (PR #21).** Every prose section
  drafted; measured-subset numbers and citations wired in; MITRE
  citation corrected (ATT&CK T1552 in place of the ATLAS T1552 that
  never existed); OWASP citation updated to LLM02:2025.
- **2026-07-20: paper prose scaffold merged (PR #20, superseding
  the closed PR #18).**
- **2026-07-20: Anthropic API capture added; author metadata
  normalized (PR #19).** Second measured row lands. Author metadata
  in commits and Co-authored-by trailers was normalized to a single
  canonical form to keep authorship representation consistent
  across the repo.
- **2026-07-18: Paper Pandoc + Weasyprint pipeline (PR #17).**
- **2026-07-18: Rubric TOS verification pass + paper scaffold
  (PR #16).**
- **2026-07-18: Harness invocation fix; first live OpenAI capture
  (PR #15).**
- **2026-07-18: Scorer + rubric metadata + `make replicate` (PR
  #14).**
- **2026-07-18: OpenAI + Bedrock + Azure API harnesses + web
  protocol (PR #13).**
- **2026-07-18: Anthropic API harness + stdlib detector (PR #12).**
- **2026-06-29: Locked corpus + reproducibility harness (PR #6).**
