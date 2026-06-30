# Reproducing the LLM Pre-Send Leakage Benchmark

This document tells you exactly **what you can run today**, **what unlocks each week**, and **how to verify methodology** — without lying about the state of the artifact. Every command listed here is real and works today unless explicitly marked otherwise.

## Status at a glance

| Capability | Available | Lands in |
|---|---|---|
| Reproduce the locked corpus byte-for-byte | ✅ **Today** | (PR #2, merged) |
| Run the test suite (23 contract tests) | ✅ **Today** | (PR #2, merged) |
| Sample prompts and manually test any AI tool | ✅ **Today** | (PR #2, merged) |
| Automated harness for API-direct tools (Anthropic, OpenAI, Bedrock, Azure) | ⏳ ~Jul 7 | PR #3, #4 |
| Manual web-tool capture protocol (mitmproxy) | ⏳ ~Jul 9 | PR #4 |
| Apply 5-dimension scoring rubric to results | ⏳ ~Jul 11 | PR #5 |
| Paper site + interactive results | ⏳ ~Jul 22 | PR #6.5 |
| **Full one-command replication** | 🎯 Jul 23 (v1.0.0 tag) | `make replicate` |

If a command in this doc references a file that doesn't exist yet, it's because that PR hasn't landed — the table above tells you when.

## Concept in one paragraph

This benchmark measures whether 20 popular AI tools redact PII / secrets / PHI **before** the data leaves the user's device en route to the model. We submit a corpus of 100 synthesized prompts (Faker-generated, no real PII), capture the outbound network payload, and score each tool on a 5-dimension rubric: pre-send redaction, user notification, transit encryption, vendor retention TOS, audit log accessibility. The corpus is deterministic, MIT-licensed, and locked at v1.0.0. Maps to OWASP LLM06 (Sensitive Information Disclosure).

## What you can do today (PR #2 merged)

### 1. Prove the corpus is byte-reproducible (30 seconds)

```bash
git clone https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark.git
cd llm-pre-send-leakage-benchmark
make dev-install      # uv sync --all-extras --dev

make verify-corpus
# Expected output:
#   ✓ Corpus is reproducible — byte-identical from DEFAULT_SEED=20260623
```

If you see `✗ Corpus NOT reproducible` followed by a diff, your Python or Faker version differs from what locked the corpus — see *Troubleshooting* below.

### 2. Run the test suite (~5 seconds)

```bash
make test-cov
# Expected: 23 passed, ≥80% coverage on corpus/generate.py
```

This validates: exactly 100 records, unique ids, schema conformance, no canary-PII patterns, JSONL parseability, determinism under reseed.

### 3. Sample prompts and test your favorite AI tool (~10 minutes)

The corpus is one JSON record per line, so [`jq`](https://jqlang.github.io/jq/) is your friend:

```bash
# 3 prompts spanning categories
jq -c 'select(.id == "ident-001" or .id == "secret-001" or .id == "mixed-001")' \
  corpus/corpus_v1.jsonl

# All 10 PHI prompts
jq -c 'select(.category == "phi")' corpus/corpus_v1.jsonl

# Random sample of 5 prompts
shuf -n5 corpus/corpus_v1.jsonl | jq -c .

# Just the prompt text for a category
jq -r 'select(.category == "api_secrets") | .prompt_text' corpus/corpus_v1.jsonl
```

Copy the `prompt_text` field into any AI tool (web or API), observe behavior. Compare against:

- `expected_categories` — what PII the prompt was designed to contain
- `expected_count` — how many of each category

**Two signals worth recording:**

1. Did the tool **scrub or warn** before sending? (network tab / DevTools / mitmproxy)
2. Did the tool's **response** echo any PII back verbatim?

You've just run a single-tool version of what PRs #3–#5 automate.

## What unlocks each week

### After PR #3 (~Jul 7) — first API harness

```bash
# (Available after PR #3 merges. Won't work today.)
export ANTHROPIC_API_KEY=sk-ant-...
uv run python harness/api/anthropic.py \
  --corpus corpus/corpus_v1.jsonl \
  --output results/raw/anthropic.json
```

Captures: outbound JSON payload sent to Anthropic, full API response, what the canonical detector finds in the outbound, whether the prompt was sent verbatim or scrubbed.

### After PR #4 (~Jul 9) — remaining harnesses + web protocol

Similar harnesses for OpenAI, Bedrock, and Azure OpenAI land alongside `harness/web/README.md`, which documents the manual mitmproxy capture protocol for web-only tools (ChatGPT web, Claude.ai, Gemini, Perplexity, Notion AI, etc.).

### After PR #5 (~Jul 11) — scoring + results

```bash
# (Available after PR #5 merges.)
uv run python harness/score.py \
  --raw-dir results/raw/ \
  --output results/results_v1.csv

cat results/results_v1.csv
# Composite scores per tool, 5 dimensions × 20 tools
```

### After v1.0.0 (Jul 23) — one-command full replication

```bash
# (Available at the v1.0.0 tag.)
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export AWS_ACCESS_KEY_ID=...  # for Bedrock
export AZURE_OPENAI_API_KEY=...

make replicate
# Runs all 4 API harnesses + applies scorer + generates figures
# Total runtime: ~3 minutes. API cost: <$5 across all four providers.
```

## Verifying methodology

If you're checking whether the **corpus** is well-formed:

- Schema: [`corpus/corpus_schema.md`](corpus/corpus_schema.md)
- Tests: [`tests/test_corpus_generator.py`](tests/test_corpus_generator.py) — 17 contract tests
- Determinism: `make verify-corpus` produces empty diff
- No real PII: the safety test enumerates known-real canary values (Woolworth SSN, canonical test CCs, `example@example.com`) and asserts none appear in the corpus

If you're cross-checking **PII detection**:

- `expected_categories` + `expected_count` on each record are the semantic ground truth, set at generation time from the template (we know what we generated)
- The `aegis_detect` field is reserved for a separate validation pipeline (PR #5)
- Open-source cross-check uses [Microsoft Presidio](https://microsoft.github.io/presidio/) on a 10% sample — runnable by anyone, fully vendor-neutral
- Internal aegis-core detection is run out-of-band and acknowledged separately; **the public benchmark has zero runtime dependency on aegis-core, aegispreflight.com, or any commercial detector**

If you're evaluating **commercial neutrality**:

- License: MIT, no exceptions
- Runtime dependencies: `faker` only (corpus generation). Harness adds provider SDKs in PR #3+.
- The benchmark does not import, call, or recommend any commercial detector
- Aegis Preflight appears in the README acknowledgments as the research host; the paper makes no Aegis-specific claims

## Troubleshooting

**`make: command not found`**
Install `make`. macOS: `xcode-select --install`. Debian / Ubuntu: `sudo apt install make`.

**`uv: command not found`**
Install `uv`: https://docs.astral.sh/uv/getting-started/installation/. The corpus is pinned to `uv.lock` for full reproducibility — `pip install` will work but won't pin versions exactly.

**`make verify-corpus` shows a non-empty diff**
Your Python or Faker version differs from what locked the corpus. The corpus was locked with **Python 3.11** and Faker pinned by `uv.lock`. Run `make dev-install` to install the exact pinned versions, then retry.

**`harness/api/anthropic.py: No such file or directory`**
Expected — the first API harness lands in PR #3 (estimated Jul 7). The status table at the top of this document tells you when each artifact ships. Until then, run the manual jq + paste workflow above.

**Faker generates a non-US SSN format in some record**
Should not happen with `DEFAULT_SEED=20260623`. Both `generate_identifiers()` and `generate_mixed()` pin to `fake["en_US"]` for SSN. If you see this, open an issue with the offending record id.

## Citation

If you cite this benchmark, see [`CITATION.cff`](CITATION.cff) for machine-readable metadata. Citation format (filled in at v1.0.0 release with DOI):

> Vikash, B. et al. (2026). *LLM Pre-Send Leakage Benchmark v1.0*. Aegis Preflight.
> https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark

GitHub's "Cite this repository" button on the repo page also produces a copy-pasteable citation.

## Related documents

- [`README.md`](README.md) — project overview
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev workflow, code standards, PR process
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure policy
- [`CHANGELOG.md`](CHANGELOG.md) — version history
- [`corpus/corpus_schema.md`](corpus/corpus_schema.md) — per-record schema definition
