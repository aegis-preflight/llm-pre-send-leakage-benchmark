# Reproducing the LLM Pre-Send Leakage Benchmark

This guide describes what is reproducible against the current `main` branch and what becomes available at each subsequent release. Commands that reference forthcoming code are marked with the PR in which they land. The rest runs against the repository as it stands.

## Status at a glance

> **Timeline update 2026-07-18:** the API harness, web-protocol, scoring, and one-command replication all landed today — five days ahead of the original 23 July target. Only the paper site and the v1.0.0 tag remain.

| Capability | Available | Lands in |
|---|---|---|
| Reproduce the locked corpus byte-for-byte | Today | PR #2, merged |
| Run the test suite (23 contract tests) | Today | PR #2, merged |
| Sample prompts and test any AI tool manually | Today | PR #2, merged |
| Automated harness for API-direct tools (Anthropic, OpenAI, Bedrock, Azure OpenAI) | Today | PR #12, #13, merged |
| Manual web-tool capture protocol (mitmproxy) | Today | PR #13, merged |
| 5-dimension scoring applied to results | Today | PR #14, merged |
| One-command full replication (`make replicate`) | Today | PR #14, merged |
| Paper site with interactive results | About 22 July | PR #6.5 |
| `v1.0.0` tag (corpus + rubric + results CSV frozen) | 23 July | v1.0.0 tag |

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

This is a manual, single-tool version of what the four API harnesses now automate.

## Running the API harnesses

Every API harness ships now on `main` (see the status table above). Each is a `python -m` invocation with the same CLI shape.

### Anthropic

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run python -m harness.api.anthropic \
  --corpus corpus/corpus_v1.jsonl \
  --output results/raw/anthropic.json
```

Captures the JSON payload sent to Anthropic Messages, the response, what the canonical detector finds in the outbound traffic, and whether the prompt was sent verbatim or scrubbed.

### OpenAI, Bedrock, Azure OpenAI

```bash
uv run python -m harness.api.openai      --corpus corpus/corpus_v1.jsonl --output results/raw/openai.json
uv run python -m harness.api.bedrock     --corpus corpus/corpus_v1.jsonl --output results/raw/bedrock.json
uv run python -m harness.api.azure_openai --corpus corpus/corpus_v1.jsonl --output results/raw/azure_openai.json --model <deployment>
```

Credentials per vendor: `OPENAI_API_KEY`; `AWS_REGION` (plus the standard AWS credential chain) for Bedrock; `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` (+ optional `AZURE_OPENAI_DEPLOYMENT`) for Azure.

### Web tools

Manual, per `harness/web/README.md`. mitmproxy-based capture protocol for ChatGPT, Claude.ai, Gemini, Perplexity, Notion AI, and the rest. HAR export per prompt; sanitized `manifest.json` per tool committed to `results/raw/web/<tool>/`.

## Scoring

```bash
uv run python -m harness.score \
  --raw-dir results/raw/ \
  --output results/results_v1.csv
```

Composite scores across the five dimensions for all 20 tools in the rubric. Tools without capture data yet emit unmeasured rows so gaps are visible.

## One-command replication

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export AWS_REGION=us-east-1        # + standard AWS credential chain for Bedrock
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=...
export AZURE_OPENAI_DEPLOYMENT=... # your deployment name

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
- The `aegis_detect` field is reserved for a follow-on validation pipeline that will replay the ground-truth detector against every corpus record; it stays empty at v1 generation time.
- The open-source cross-check uses [Microsoft Presidio](https://microsoft.github.io/presidio/) on a 10 percent sample. Anyone can run it.
- An internal aegis-core detection is run separately and acknowledged in the paper. The public benchmark has no runtime dependency on aegis-core, on `aegispreflight.com`, or on any commercial detector.

If you are evaluating commercial neutrality:

- License: MIT
- Runtime dependencies: `faker` for corpus generation. Provider SDKs (`anthropic`, `openai`, `boto3`) install under harness extras and are only imported at live-run time; dry-run needs none of them.
- No commercial detector is imported, called, or recommended.
- Aegis Preflight is named in the README as the host. The paper makes no Aegis-specific claims.

## Troubleshooting

**`make: command not found`**
Install `make`. On macOS, `xcode-select --install`. On Debian or Ubuntu, `sudo apt install make`.

**`uv: command not found`**
Install `uv` from https://docs.astral.sh/uv/getting-started/installation/. The corpus is pinned to `uv.lock` for full reproducibility. `pip install` will work but does not pin versions exactly.

**`make verify-corpus` shows a non-empty diff**
Your Python or Faker version differs from what locked the corpus. The lockfile pins Python 3.11 and the exact Faker version. Run `make dev-install` to install the pinned versions, then retry.

**`ModuleNotFoundError: No module named 'openai.OpenAI'` or `AttributeError: module 'openai' has no attribute 'OpenAI'`**
You invoked the harness as a script (`python harness/api/openai.py`) instead of as a module (`python -m harness.api.openai`). Script mode puts `harness/api/` at the front of `sys.path`, which shadows the SDK. Always use `python -m harness.api.<vendor>` (or the `make harness-<vendor>` targets).

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
