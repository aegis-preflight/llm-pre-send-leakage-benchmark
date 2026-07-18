# LLM Pre-Send Leakage Benchmark v1.0

> **Status:** DRAFT. This is a paper scaffold — every `[TODO: ...]` marker
> is a prose gap that needs to be filled before the v1.0.0 tag on
> 2026-07-23. Structure follows IMRaD (Introduction → Methods → Results →
> Discussion) with two additions the security-research audience expects:
> a Threat Model section between Introduction and Methods, and an
> explicit Limitations section before Discussion.
>
> **Authoring convention:** prose is the human's job. Numbers, tables,
> and citation URLs are loaded mechanically from
> `harness/rubric/tool_metadata.toml` and `results/results_v1.csv` at
> render time. Don't hand-copy — reference by path.

**Authors:** Bikram Vikash *(and any co-authors)*
**Version:** v1.0.0 (locked at git tag)
**License:** MIT (paper, corpus, harness, and results all MIT-licensed)
**Citation:** see `CITATION.cff` at repo root
**Reproducibility:** every claim below is traceable to a specific file in
this repository. See `REPRODUCING.md` for the one-command replication path.

---

## Abstract

`[TODO — 200 words. Draft the arc:]`

- **What we measured** — Of the data that users paste into 20 popular AI
  tools, how much reaches the model provider's servers? Corpus of 100
  synthesized prompts spanning PII, API secrets, and PHI. Five scoring
  dimensions (pre-send redaction, user notification, transit encryption,
  vendor retention TOS, audit log accessibility), each 0-2, composite
  0-10.
- **Headline finding** — `[TODO: fill in the top-line number from
  results/results_v1.csv once ≥ 4/20 tools are measured. Current v1
  measured subset: 1/20 (openai) → total=4, band=Minimal. This will
  read something like ""X of 20 tools scored 0/2 on pre-send redaction;
  the median composite score was N of 10.""]`
- **Why it matters** — Maps to OWASP LLM06 (Sensitive Information
  Disclosure). Establishes a reproducible baseline any tool vendor
  can be re-scored against without our involvement.
- **What's MIT-licensed** — Harness, corpus, rubric, and this paper.

---

## 1. Introduction

`[TODO — 300 words on the motivation:]`

1. Users paste sensitive data into AI tools every day. Enterprises worry
   about ""shadow AI"" leakage; individuals paste PII without thinking
   about where the bytes go.
2. Existing benchmarks measure **model behavior** (jailbreaking,
   hallucination, refusal rates). None measure **pre-send behavior** —
   what the client actually puts on the wire before the model ever
   sees it. That's the gap this benchmark fills.
3. Scope is narrow on purpose. A single well-defined question — "of the
   data that goes in, how much reaches the vendor's servers?" — beats
   twelve fuzzy dimensions in a policy-influencing benchmark.
4. Deliverable: a per-tool composite score bucketed to a band label,
   plus the raw captures and prompts anyone can re-run.

Reference to prior work: OWASP LLM06, MITRE ATLAS T1552 (Unsecured
Credentials via LLM), any DLP-vs-LLM literature. `[TODO: fill in
literature review.]`

---

## 2. Threat model

`[TODO — 250 words. Position the reader before the methods:]`

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
- Behavior under load — this is a correctness benchmark, not a
  performance one.
- Enterprise / DLP-integrated tier behavior. The tier tested for each
  tool is whichever a typical user sees (documented per-row in
  `results_v1.csv`).

**Actors we account for:**
- **The user** — pastes sensitive data. May or may not know the risk.
- **The AI tool's client** (browser page, mobile app, IDE plugin). The
  benchmark measures whether *this actor* transforms the payload
  before send.
- **The model provider** (OpenAI, Anthropic, Google, etc.). Once data
  reaches the provider, the retention TOS and audit story determine
  what happens next.

**Actors we explicitly do not model:**
- Network intermediaries (assumed TLS-protected; D3 is a hygiene check,
  not a threat model).
- Post-breach behavior — if the provider is subpoenaed or breached, the
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

### 3.2 Detector

`harness/detect.py` — stdlib-only Python. Regex + Luhn (CC) +
ISO-13616 (IBAN) + SSA structural rules (SSN) + PHI keyword bucket +
ICD-10 shape.

**No `aegis-core` import.** The benchmark repo is commercially neutral
by construction. Pattern sets are cross-referenced against `aegis-core`
public docs but the code is independent (~250 LOC).

### 3.3 Harness

One `HarnessResult` shape across every tool
(`harness/api/_common.py`). Per tool per prompt, capture:

- `prompt_id` — which corpus entry
- `tool`, `tier`, `model` — vendor + tier + model tested
- `request_payload` — the JSON body sent to the vendor
- `response_text` — the vendor's response (recorded but not scored)
- `outbound_findings` — what the detector finds in the request
- `sent_verbatim` — True iff every PII category the corpus expected
  is still present in the payload

API-direct tools (Anthropic, OpenAI, Bedrock, Azure OpenAI) are
scripted via `python -m harness.api.<vendor>`. Web tools use manual
mitmproxy HAR capture per [`harness/web/README.md`](../harness/web/README.md).

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
citations — see Limitations.

### 3.5 Reproducibility protocol

`[TODO — one paragraph:]` deterministic corpus, MIT license, `uv.lock`
pins every dep, live run costs under $5 total via `make replicate`,
raw captures + scored CSV committed to the v1.0.0 tag.

---

## 4. Results

`[TODO — this section is skeletal until ≥ 4 API-direct tools are
captured. Structure:]`

### 4.1 Composite scores

`[Render results/results_v1.csv as a table, sorted by total desc. Only
""measured"" rows count toward findings; unmeasured rows are called out
as ""pending capture"" in a smaller table.]`

### 4.2 Per-dimension analysis

**D1 pre-send redaction.** `[TODO: report what fraction of tools scrubbed
anything at all. Current v1 measured subset: 0/1. The API-direct
pattern is uniform — no vendor's SDK strips PII before sending.]`

**D2 user notification.** All 20 tools scored 0. This dimension does
not discriminate in v1. Discussed in §6.

**D3 transit encryption.** All 20 tools scored 2. Also non-discriminating.
Discussed in §6.

**D4 vendor retention TOS.** `[TODO: report the distribution. Preview:
Bedrock scores 2 (no logging, no training by default), Azure/Anthropic
API score 1 (retention window exists, no training), ChatGPT free scores
0 (training-by-default unless opted out).]`

**D5 audit log accessibility.** `[TODO: report the distribution.]`

### 4.3 Notable per-prompt behaviors

`[TODO — this is the ""interesting stories"" subsection. Concrete
observations from raw captures:]`

- **GPT-4o refused most PII-carrying prompts in-response** — response
  text was some variant of ""I can't assist with requests that involve
  sensitive personal information"" — but the PII still reached
  OpenAI's servers. Response-level refusal does not equal pre-send
  protection. This is exactly what the benchmark measures.
- `[TODO: add analogous observations for Claude, Bedrock, Azure once
  captures land.]`

### 4.4 Reproducibility spot-check

`[TODO: pick 3 arbitrary corpus prompts, list the exact bytes captured
per tool. Reader can rerun the corpus generator + one harness invocation
and confirm byte-identical output.]`

---

## 5. Limitations

`[TODO — this section is critical for the paper's credibility. Draft:]`

**Coverage.** v1.0 ships with `[N of 20]` tools machine-measured. The
remaining rows carry static rubric metadata but no captured D1. Named
per-row in `results/results_v1.csv` under `measured=false`.

**Rubric verification.** Of the 20 static-dimension rows, `[N]` are
`verified`, `[N]` are `partial`, and `[N]` are `unverified` at the
v1.0.0 tag. Every claim in the `unverified` set is defensible per its
cited URL but was not machine-fetched. Paper explicitly does not treat
unverified rows as citation-grade.

**Non-discriminating dimensions.** D2 and D3 are constant across all 20
tools in v1 (0 and 2 respectively). Two of five dimensions carry zero
signal. v2 will either redesign these (D3 → cert pinning strength,
D2 → temporary-chat / ephemeral modes) or drop them.

**Client-side scope only.** We do not test what happens after data
reaches the vendor. D4 is a policy citation, not a live audit; if a
vendor's TOS says ""we do not train on API data"" and they lie, this
benchmark will not catch that. Post-breach behavior is out of scope.

**Refusal-vs-scrub conflation risk.** The scorer counts a prompt as
""leaked"" if `sent_verbatim=True` — regardless of whether the model
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
number, address, or person names — those categories are in the corpus
but scored via substring match against the known corpus values, not
regex.

---

## 6. Discussion

`[TODO — the ""so what"" section. Draft angles:]`

- **The pre-send layer is uniformly absent.** Every AI tool the
  benchmark can test at API-direct or web tier scored 0 on D1. There
  is no meaningful client-side scrub layer in the market as of
  2026-07. `[TODO: nuance once web-tool data lands.]`
- **The scores that discriminate are D1, D4, and D5.** D2 (notification)
  and D3 (encryption) are hygiene, not competitive dimensions. The
  paper argues D2 and D3 stay for completeness but the reader should
  focus on the other three.
- **Model refusal ≠ pre-send protection.** GPT-4o's in-response
  refusal is a real safety property but is orthogonal to leak
  prevention. The paper explicitly distinguishes.
- **Where a defender should look.** `[TODO: 2-3 sentences on
  implications for enterprise DLP, browser extensions, macOS agents.
  Don't pitch Aegis Preflight — this is the benchmark paper, not a
  vendor pitch. Named neutrally as the host org in the acknowledgments.]`

---

## 7. Acknowledgments

`[TODO: acknowledge the Aegis Preflight team as host of the repository;
name any external reviewers who verified rubric rows before publication;
credit corpus reviewers.]`

---

## 8. References

`[TODO: format bibliography. Load URLs from
harness/rubric/tool_metadata.toml programmatically at render time so
the paper reflects the same TOS URLs the scorer used.]`

Key references likely to appear:

- OWASP Top 10 for LLMs — LLM06 Sensitive Information Disclosure
- MITRE ATLAS T1552 — Unsecured Credentials
- Microsoft Presidio — cross-check detector for corpus validation
- Faker — corpus generation library
- Individual vendor TOS URLs (per `harness/rubric/tool_metadata.toml`)

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

- 2026-07-23 — v1.0.0 tag. Corpus + rubric + scored CSV frozen.
- 2026-07-18 — Scorer + rubric metadata + `make replicate` land (PR #14).
- 2026-07-18 — OpenAI + Bedrock + Azure API harnesses + web protocol
  land (PR #13).
- 2026-07-18 — Anthropic API harness + stdlib detector land (PR #12).
- 2026-06-29 — Locked corpus + reproducibility harness land (PR #6).
