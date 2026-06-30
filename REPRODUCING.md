# Reproducing the LLM Pre-Send Leakage Benchmark

This guide describes what is reproducible against the current `main` branch and what becomes available at each subsequent release. Commands that reference forthcoming code are marked with the PR in which they land. The rest runs against the repository as it stands.

## Status at a glance

| Capability | Available | Lands in |
|---|---|---|
| Reproduce the locked corpus byte-for-byte | Today | PR #2, merged |
| Run the test suite (23 contract tests) | Today | PR #2, merged |
| Sample prompts and test any AI tool manually | Today | PR #2, merged |
| Automated harness for API-direct tools | About 7 July | PR #3, #4 |
| Manual web-tool capture protocol (mitmproxy) | About 9 July | PR #4 |
| 5-dimension scoring applied to results | About 11 July | PR #5 |
| Paper site with interactive results | About 22 July | PR #6.5 |
| One-command full replication (`make replicate`) | 23 July | v1.0.0 tag |

## What the benchmark measures

The question is narrow. When a user submits a prompt to an AI tool, what reaches the model provider's servers? The corpus contains 100 synthesized prompts spanning PII, API secrets, and PHI. Each prompt is submitted to a tool; the outbound network payload is captured and scored against the input. Five dimensions: pre-send redaction, user notification, transit encryption, vendor retention TOS, and audit log accessibility. The benchmark maps to OWASP LLM06 (Sensitive Information Disclosure). The corpus is MIT-licensed and locked at the `v1.0.0` tag.

## What you can do today

### Reproduce the corpus byte-for-byte

```bash
git clone https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark.git
cd llm-pre-send-leakage-benchmark
make dev-install   # uv sync --all-extras --dev

make verify-corpus
# ✓ Corpus is reproducible — byte-identical from DEFAULT_SEED=20260623
```

An empty diff confirms that the same seed produces the same 100 prompts in the same order. If the diff is not empty, your Python or Faker version differs from the lockfile. See Troubleshooting.

### Run the test suite

```bash
make test-cov
# 23 passed, coverage ≥80% on corpus/generate.py
```

The suite validates 100 records, unique ids, schema conformance, the absence of known-real canary PII, JSONL parseability, and determinism under reseed.

### Sample prompts and test any AI tool

The corpus is one JSON record per line. `jq` queries the file directly:

```bash
# Three prompts spanning categories
jq -c 'select(.id == "ident-001" or .id == "secret-001" or .id == "mixed-001")' \
  corpus/corpus_v1.jsonl

# All ten PHI prompts
jq -c 'select(.category == "phi")' corpus/corpus_v1.jsonl

# A random five
shuf -n5 corpus/corpus_v1.jsonl | jq -c .

# Just the prompt text for one category
jq -r 'select(.category == "api_secrets") | .prompt_text' corpus/corpus_v1.jsonl
```

Copy a `prompt_text` field into any AI tool (web or API) and watch what happens. Compare what the tool does against `expected_categories` (the categories the prompt was designed to contain) and `expected_count` (how many of each).

Two things are worth recording from each test:

1. Did the tool redact or warn the user before sending the prompt? Inspect the network tab or use mitmproxy.
2. Did the tool's response echo any PII back?

This is a manual, single-tool version of what PRs #3 through #5 automate.

## What becomes available at each release

### After PR #3 (around 7 July)

The first API harness will be at `harness/api/anthropic.py`. Usage:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run python harness/api/anthropic.py \
  --corpus corpus/corpus_v1.jsonl \
  --output results/raw/anthropic.json
```

It captures the JSON payload that goes to the Anthropic API, the full response, what the canonical detector finds in the outbound traffic, and whether the prompt was sent verbatim or scrubbed.

### After PR #4 (around 9 July)

OpenAI, Bedrock, and Azure OpenAI harnesses ship alongside `harness/web/README.md`, the manual mitmproxy capture protocol for web-only tools (ChatGPT, Claude.ai, Gemini, Perplexity, Notion AI, and the rest).

### After PR #5 (around 11 July)

The scorer applies the 5-dimension rubric:

```bash
uv run python harness/score.py \
  --raw-dir results/raw/ \
  --output results/results_v1.csv
```

Output is a CSV of composite scores across five dimensions and 20 tools.

### After v1.0.0 (23 July)

A single command runs the full benchmark end to end:

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export AWS_ACCESS_KEY_ID=...      # for Bedrock
export AZURE_OPENAI_API_KEY=...

make replicate
```

Total runtime is around three minutes. Combined API cost is under five US dollars across all four providers.

## Verifying methodology

If you are checking whether the corpus is well-formed:

- Schema: [`corpus/corpus_schema.md`](corpus/corpus_schema.md)
- Tests: [`tests/test_corpus_generator.py`](tests/test_corpus_generator.py), seventeen contract tests
- Determinism: `make verify-corpus` produces an empty diff
- Canary safety: the test suite enumerates known-real values (the Woolworth SSN, canonical test credit cards, `example@example.com`) and asserts none of them appear in the corpus

If you are cross-checking PII detection:

- The semantic ground truth on each record is `expected_categories` and `expected_count`. Both are set at generation time from the template, since we know what was synthesized.
- The `aegis_detect` field is reserved for a separate validation pipeline that lands in PR #5.
- The open-source cross-check uses [Microsoft Presidio](https://microsoft.github.io/presidio/) on a 10 percent sample. Anyone can run it.
- An internal aegis-core detection is run separately and acknowledged in the paper. The public benchmark has no runtime dependency on aegis-core, on `aegispreflight.com`, or on any commercial detector.

If you are evaluating commercial neutrality:

- License: MIT
- Runtime dependencies: `faker` for corpus generation. Provider SDKs are added in PR #3.
- No commercial detector is imported, called, or recommended.
- Aegis Preflight is named in the README as the host. The paper makes no Aegis-specific claims.

## Troubleshooting

**`make: command not found`**
Install `make`. On macOS, `xcode-select --install`. On Debian or Ubuntu, `sudo apt install make`.

**`uv: command not found`**
Install `uv` from https://docs.astral.sh/uv/getting-started/installation/. The corpus is pinned to `uv.lock` for full reproducibility. `pip install` will work but does not pin versions exactly.

**`make verify-corpus` shows a non-empty diff**
Your Python or Faker version differs from what locked the corpus. The lockfile pins Python 3.11 and the exact Faker version. Run `make dev-install` to install the pinned versions, then retry.

**`harness/api/anthropic.py: No such file or directory`**
That file lands in PR #3 around 7 July. Until then, use the manual sampling workflow above. The status table at the top of this document shows when each artifact ships.

**Non-US SSN format in a record**
Should not happen at `DEFAULT_SEED=20260623`. Both the identifiers and mixed generators pin to `fake["en_US"]` for SSN. If you see a non-US format, open an issue with the offending record id.

## Citation

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff). The citation format below will be completed with the v1.0.0 release and DOI:

> Vikash, B. et al. (2026). *LLM Pre-Send Leakage Benchmark v1.0*. Aegis Preflight.
> https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark

GitHub's "Cite this repository" button on the repo page produces the same citation.

## Related documents

- [`README.md`](README.md) — project overview
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development workflow, code standards, PR process
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure policy
- [`CHANGELOG.md`](CHANGELOG.md) — version history
- [`corpus/corpus_schema.md`](corpus/corpus_schema.md) — per-record schema
