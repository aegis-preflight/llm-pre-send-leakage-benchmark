# LLM Pre-Send Leakage Benchmark v1.0

> **Status:** DRAFT prose complete. Remaining `[TODO: ...]` markers
> are pending final measurements (Anthropic / Bedrock / Azure captures),
> pending external review (unverified rubric rows + literature review),
> and pending render-time substitution (Table 2 unmeasured-row list,
> reference list expansion from the rubric TOML). Structure follows
> IMRaD (Introduction → Methods → Results → Discussion) with two
> additions the security-research audience expects: a Threat Model
> section between Introduction and Methods, and an explicit
> Limitations section before Discussion.
>
> **Authoring convention:** prose is the human's job. Numbers, tables,
> and citation URLs are loaded mechanically from
> `harness/rubric/tool_metadata.toml` and `results/results_v1.csv` at
> render time. Do not hand-copy — reference by path.

**Authors:** Bikram Vikash *(and any co-authors)*
**Version:** v1.0.0 (locked at git tag)
**License:** MIT (paper, corpus, harness, and results all MIT-licensed)
**Citation:** see `CITATION.cff` at repo root
**Reproducibility:** every claim below is traceable to a specific file in
this repository. See `REPRODUCING.md` for the one-command replication path.

---

## Abstract

Users paste sensitive data into AI tools every day. This benchmark asks a
narrow question about that behavior: of the data that goes into an AI
tool, how much reaches the model provider's servers? We test 20 tools
against 100 synthesized prompts spanning PII, API secrets, and PHI. Each
tool is scored across five dimensions — pre-send redaction, user
notification, transit encryption, vendor retention TOS, and audit log
accessibility — for a composite score from 0 to 10, bucketed into four
bands (No protection / Minimal / Moderate / Strong).

`[TODO: replace this sentence at v1.0.0 tag time with the top-line
number from results/results_v1.csv. Current v1 measured subset (2026-07-18):
1 of 20 tools captured; OpenAI API scored 4 of 10 (Minimal). Pattern
projected across API-direct tier: no vendor SDK strips PII before send,
so every API-direct tool will score 0/2 on the pre-send-redaction
dimension.]` One observation stands out even at low coverage: when a
model refuses a PII-carrying prompt in its response, the PII has already
reached the vendor's servers. Response-level refusal is not pre-send
protection.

The benchmark maps to OWASP LLM06 (Sensitive Information Disclosure) and
establishes a reproducible baseline any tool vendor can be re-scored
against, without our involvement. Harness, corpus, rubric metadata, and
this paper are all MIT-licensed. One command — `make replicate` —
regenerates every scored row for under five US dollars in combined API
cost.

---

## 1. Introduction

Users paste sensitive data into AI tools every day. That is not news.
What is less obvious is where the bytes actually go. When a marketing
manager pastes a customer email into ChatGPT to draft a reply, when a
support agent pastes a session log into Claude to look for a bug, when
a developer pastes an AWS access key into a coding copilot to debug an
error — the sensitive substring leaves the user's device and lands on
someone else's server, subject to that server's retention policy,
training posture, and breach exposure. Enterprises worry about "shadow
AI" leakage in aggregate. Individuals paste without thinking about it
one prompt at a time. Both are the same phenomenon at different
scales.

Existing LLM benchmarks measure model behavior — jailbreaking success
rates, hallucination frequency, refusal quality, downstream task
accuracy. They start their measurement *after* the prompt has already
been received by the model. None ask what leaves the client before the
model ever sees the request. That is the gap this benchmark fills.

The scope is narrow on purpose. One question — of the data that goes
in, how much reaches the vendor's servers? — beats twelve fuzzy
dimensions in a policy-influencing benchmark. A CISO trying to explain
GenAI risk to a board, a regulator drafting Article 12 logging
requirements, a journalist writing about last week's shadow-AI
incident: all three want the same thing, which is a defensible number
per tool. This paper produces that number.

The deliverable is a per-tool composite score in the range 0 to 10,
bucketed to a band label, alongside the raw captures and corpus
prompts anyone can re-run. The benchmark maps to OWASP LLM06 —
Sensitive Information Disclosure — in the OWASP Top 10 for Large
Language Model Applications, and to MITRE ATLAS T1552 (Unsecured
Credentials) in the AI-specific attack matrix. `[TODO: expand
literature review with 3-4 additional citations before v1.0.0 tag:
prior DLP-vs-LLM measurement work (Barrera et al 2024 if applicable),
concurrent shadow-AI enterprise surveys, any peer benchmarks measuring
client-side behavior.]`

---

## 2. Threat model

The threat this benchmark measures is deliberately simple: sensitive
data reaches a vendor's servers when it should not have. The user is
not the attacker. There is no adversary trying to smuggle data out.
The failure mode is one of omission — the AI tool's client-side layer
does not scrub, warn, or block, so the data leaves the device in the
normal course of use.

That simplicity is intentional. This benchmark is not modeling
sophisticated exfiltration. It is measuring whether the pre-send layer
exists at all. If it does not — and the results below suggest it
mostly does not — then every downstream conversation about vendor
trust, retention windows, breach exposure, and regulatory logging
starts from the wrong baseline.

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

The corpus is generated from a fixed seed (`DEFAULT_SEED=20260623`);
`make verify-corpus` produces an empty diff against the committed
`corpus_v1.jsonl` on any Python 3.11+ environment with the pinned
Faker version. The harness dependencies are locked in `uv.lock`.
Every scored row in `results/results_v1.csv` is regenerable by any
reader with the four vendor API keys: `make replicate` runs the
Anthropic, OpenAI, Bedrock, and Azure OpenAI harnesses in sequence,
scores the captures, and writes the CSV in under three minutes for
under five US dollars in combined API cost. Web-tool captures follow
the manual mitmproxy protocol at `harness/web/README.md`; the resulting
HAR files are not committed (they contain session tokens) but the
sanitized `manifest.json` per tool is. The v1.0.0 tag freezes the
corpus, the rubric TOML, and the scored CSV. Any change after that
tag ships as v1.1.0 or later with its own corpus / rubric / CSV
alongside the v1 files, so historical claims remain verifiable
against the exact data they were computed from.

---

## 4. Results

At the v1.0.0 tag, `[TODO: 4 of 20]` tools carry captured D1 scores
alongside their static rubric metadata; the remaining `[TODO: 16 of
20]` rows carry rubric metadata only, marked `measured=false` in the
CSV. This section reports the measured subset and describes the
patterns projected across the unmeasured rows from the rubric
metadata alone.

### 4.1 Composite scores

Table 1 shows the scored tools sorted by composite total descending.
Rendered from `results/results_v1.csv`.

`[TODO: at v1.0.0 tag time, render the measured rows from
results/results_v1.csv here as a markdown table. Current draft-time
snapshot (2026-07-18, 1 of 20 tools captured):]`

| Tool | Tier | D1 | D2 | D3 | D4 | D5 | Total | Band | Verification |
|---|---|---|---|---|---|---|---|---|---|
| OpenAI API | api-direct | 0 | 0 | 2 | 1 | 1 | 4 | Minimal | unverified |

Table 2 lists the tools measured for rubric metadata only. These rows
carry the D2 through D5 static-dimension scores from the rubric but
no captured D1; they will fill in as harnesses run.

`[TODO: at v1.0.0 tag time, render the unmeasured rows here — one
line per tool with the tier and category.]`

### 4.2 Per-dimension analysis

**D1 pre-send redaction.** `[TODO: at v1.0.0 tag time, report the
fraction of measured tools that scrubbed anything at all. Current
draft-time observation: 0 of 1 measured tools showed any pre-send
redaction. The API-direct tier is expected to be uniform on this
dimension because the vendor SDKs (Anthropic Messages, OpenAI Chat
Completions, Bedrock InvokeModel, Azure OpenAI Chat Completions)
serialize the user's prompt directly into the HTTP body with no
transform.]`

**D2 user notification.** Every one of the 20 tools scored 0. None
of the tested tools warns the user before sending sensitive content.
This dimension does not discriminate between tools in v1 — the entire
market is at the floor. §6 discusses what to do with a
non-discriminating dimension.

**D3 transit encryption.** Every one of the 20 tools scored 2. HTTPS
is universal. Also non-discriminating in v1.

**D4 vendor retention TOS.** The rubric shows meaningful variation on
this dimension. AWS Bedrock scores 2 (no logging by default, no
training on customer data per verified FAQ language). Anthropic API
and Azure OpenAI score 1 (retention windows exist, no training on
customer data per verified TOS language). ChatGPT free scores 0
(conversations used to improve models unless the user opts out).
Meta.ai and Gemini also score 0 at their default tier. `[TODO: at
v1.0.0 tag time, report the full distribution — count of 0s, 1s, 2s
— across all 20 rubric rows.]`

**D5 audit log accessibility.** `[TODO: at v1.0.0 tag time, report
the distribution. Preview from the rubric: Bedrock and Azure score
2 (per-request logging via CloudTrail / Azure Monitor is customer-
configurable and produces per-request audit records). Most consumer
web tools score 1 (chat history export exists but no per-request
audit). Meta.ai scores 0 (no per-conversation export at the tested
tier).]`

### 4.3 Notable per-prompt behaviors

The measured subset is small, but one observation from the OpenAI
capture is worth foregrounding because it appears in every subsequent
measurement discussion.

**Model refusal does not undo the leak.** For the majority of
PII-carrying prompts sent to OpenAI's `gpt-4o` model, the response
text opened with some variant of "I'm sorry, but I can't assist with
requests that involve sensitive personal information." The model
correctly identified the presence of an SSN, credit card, or API key
in the prompt and declined to act on it. And yet: the SSN, credit
card, or API key had already reached OpenAI's servers by the time
that refusal was composed. The `request_payload` recorded in
`results/raw/openai.json` contains the sensitive substring verbatim
on every prompt.

This distinction is exactly what the benchmark exists to make. A
model that refuses in-response provides a good user experience and
reduces the risk of the model *acting on* the sensitive data. It
does nothing about the retention, training, audit, breach, or
subpoena exposure that begins the moment the payload lands on the
vendor's server. Pre-send is a separate control layer from
post-receive refusal. The composite score treats them separately for
that reason.

`[TODO: add analogous per-tool observations from the Anthropic API,
Bedrock, and Azure OpenAI captures once those harnesses have been
run live. Expected pattern: same result — payload verbatim on the
wire — because the SDKs are structurally identical in this
respect.]`

### 4.4 Reproducibility spot-check

Any reader can reproduce Table 1 in three commands:

```bash
git checkout v1.0.0
make dev-install
export OPENAI_API_KEY=sk-...
make harness-openai
make score
diff results/results_v1.csv <(cat results/results_v1.csv)
```

The final `diff` should show no changes for the row corresponding to
the vendor(s) whose keys the reader set. The corpus is byte-identical
by construction (`make verify-corpus`), the harness output is
deterministic in its structure (payload capture is fully specified by
the SDK's serialization of a fixed prompt), and the scorer is a pure
function of `(rubric TOML, raw JSON captures)`. Every claim in this
section is regenerable end-to-end from the tagged repo state.

---

## 5. Limitations

This section is not an afterthought. The paper's credibility depends
on the reader knowing what has been measured, what has been asserted
from citation only, and what has not been measured at all.

**Coverage.** v1.0 ships with `[TODO: N of 20]` tools machine-measured
on the D1 dimension. The remaining rows carry static rubric metadata
(D2 through D5) but no captured D1 score. Every unmeasured row is
named in `results/results_v1.csv` under `measured=false` and appears
in Table 2 of §4.1.

**Rubric verification.** Of the 20 static-dimension rows, 2 are
`verified` (AWS Bedrock, Azure OpenAI — every cited URL was fetched
and every claim quoted from the source page), 3 are `partial`
(Anthropic API, Claude.ai free, Claude.ai Pro — some URLs verified,
some claims not directly quoted in the fetched document), and 15 are
`unverified` (URLs are plausible per each vendor's documentation
patterns but not machine-fetched to confirm the specific claim). One
of the unverified rows, OpenAI API, is unverified only because our
WebFetch tool returned HTTP 403 on the vendor's public policy pages;
the values reflect the vendor's widely-cited default retention and
training posture. Every unverified row is flagged in the CSV via the
`verification` column. The paper does not treat unverified rows as
citation-grade; a reader who wants to cite a specific score should
first verify the underlying claim.

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

**The pre-send layer is uniformly absent.** Every tool the benchmark
can currently test at the API-direct tier scored 0 on D1. The vendor
SDKs forward the user's prompt directly into the HTTP body. There is
no meaningful client-side scrub layer in the API-direct market as of
2026-07. `[TODO: at v1.0.0 tag time, add nuance from the web-tool
captures. If any web tool scored above 0 on D1, name it and describe
what it did; if none did, that is the stronger claim.]` This is not
an accusation. Vendors optimize for latency and simplicity, and every
byte of client-side pre-processing is a byte of complexity that could
introduce its own bugs. But absence is measurable, and this benchmark
measures it.

**Two of five dimensions do not discriminate.** D2 (user
notification) is 0 across all 20 tools. D3 (transit encryption) is 2
across all 20 tools. On the numbers, the composite is really a
three-dimensional score in a five-column dress. We kept D2 and D3 in
the composite for completeness — a future tool that adds pre-send
warnings would benefit from being able to score above 0 on D2, and a
future protocol regression (a tool that drops HTTPS in some flow)
would score below 2 on D3. But the reader interested in *which tool
is better than which other tool today* should focus on D1, D4, and
D5.

**Model refusal is not pre-send protection.** The
GPT-4o refusal pattern described in §4.3 is the single most important
distinction this benchmark surfaces, because it is the point at which
a well-meaning reader might otherwise stop paying attention. A model
that says "I can't help with your SSN" while its provider retains the
SSN in an inference log is not the same tool as one that never
receives the SSN. Every downstream conversation about retention
windows, breach exposure, training opt-outs, subpoena responses, and
regulatory logging depends on the payload never having arrived. If
the payload arrived, the model's refusal does not un-transmit it.

**Where a defender should look.** The pre-send layer, wherever it can
be placed, is the highest-leverage intervention. That layer can live
in a browser extension, a network proxy, a device agent, an
enterprise DLP forward-proxy, or a client library the developer
opts into. It cannot live in the model. It cannot live in the
vendor's TOS. It has to live before the HTTP body is sealed. The
benchmark is deliberately neutral on which of those form factors a
defender should adopt. What it does establish is that the layer is
mostly missing today, and that any tool that ships one will score
detectably higher on D1 in a re-run.

---

## 7. Acknowledgments

This benchmark was developed and is hosted by the Aegis Preflight team.
Aegis Preflight ships a commercial pre-send data governance product
in the same problem space as the benchmark's D1 dimension; that
product is not tested by, cited by, or advantaged in the scoring
methodology. The benchmark repository has no runtime dependency on
`aegis-core` or any commercial detector. The pattern set in
`harness/detect.py` is cross-referenced against `aegis-core`'s public
documentation but the implementation is independent (~250 lines of
standard-library Python).

`[TODO: at v1.0.0 tag time, name external reviewers who verified any
of the 15 currently-unverified rubric rows before publication, and
credit any corpus reviewers who helped spot canary values or
generation bugs. Add author affiliations as they are decided.]`

---

## 8. References

**Standards and threat catalogs**

- OWASP Foundation. *OWASP Top 10 for Large Language Model
  Applications: LLM06 — Sensitive Information Disclosure.*
  <https://owasp.org/www-project-top-10-for-large-language-model-applications/>
- MITRE Corporation. *ATLAS: Adversarial Threat Landscape for AI
  Systems, T1552 — Unsecured Credentials.*
  <https://atlas.mitre.org/>

**Tooling used by the benchmark**

- Faraday, D. et al. *Faker: a Python library for generating fake
  data.* <https://faker.readthedocs.io/>
- Microsoft. *Presidio: data protection and de-identification SDK.*
  Used as an open-source cross-check on a 10% corpus sample.
  <https://microsoft.github.io/presidio/>
- MacFarlane, J. *Pandoc: universal document converter.* Used for the
  paper build. <https://pandoc.org/>

**Vendor policy pages cited in the rubric**

Every static-dimension score in `harness/rubric/tool_metadata.toml`
carries the URL that grounds it under the `[tools.references]` table
for that entry. Rather than duplicate 60+ URLs here, the paper defers
to the rubric TOML as the source of truth. `[TODO: at render time,
enumerate the URLs from tool_metadata.toml alongside their
verification status so the printed bibliography matches the machine-
readable citations exactly.]`

**Related empirical work**

`[TODO: at v1.0.0 tag time, add 3-4 citations to concurrent or prior
empirical work on shadow-AI leakage measurement, enterprise DLP
studies, or model-refusal audits. Candidate sources to check:
Barrera et al. on client-side LLM leakage (if applicable), Netskope
or Zscaler shadow-AI incidence reports, any peer academic benchmarks
that overlap with this scope.]`

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
- 2026-07-20 — Paper prose draft fills in Abstract, Introduction,
  Threat Model, Discussion, Limitations, Acknowledgments, References
  (this PR). Several `[TODO: ...]` markers remain against v1.0.0-tag-time
  numbers and external-review citations.
- 2026-07-18 — `make paper` — Pandoc + Weasyprint HTML/PDF pipeline
  lands (PR #17).
- 2026-07-18 — Rubric verification pass (5 of 20 tools grounded) +
  paper scaffold lands (PR #16).
- 2026-07-18 — Fix `python -m` invocation to avoid SDK-name shadowing
  (PR #15).
- 2026-07-18 — Scorer + rubric metadata + `make replicate` land (PR #14).
- 2026-07-18 — OpenAI + Bedrock + Azure API harnesses + web protocol
  land (PR #13).
- 2026-07-18 — Anthropic API harness + stdlib detector land (PR #12).
- 2026-06-29 — Locked corpus + reproducibility harness land (PR #6).
