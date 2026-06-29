# Contributing

This is a single-publication research artifact. The published version (`v1.0.0` tag, target 2026-07-23) is the authoritative output. Post-publication contributions welcome for replication, methodology improvements, and corpus extensions to future `corpus_v2.jsonl`.

## Dev environment

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). All commands assume `uv` is on your PATH.

```bash
git clone https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark.git
cd llm-pre-send-leakage-benchmark
make dev-install   # uv sync --all-extras --dev
make hooks         # install pre-commit + commit-msg hooks
```

Run `make help` to see all available targets.

## PR workflow

1. **Branch off `main`** with a typed prefix:
   - `feat/` — new functionality
   - `fix/` — bug fix
   - `chore/` — tooling, dependencies, non-functional
   - `docs/` — documentation only
   - `test/` — test changes only
2. **Make changes.** Keep commits atomic and themed. First line < 72 chars, body explains *why*.
3. **Run `make ci-precheck` locally** before pushing. This catches every CI failure on your laptop.
4. **Push and open a PR against `main`.**
5. **CI must pass** (lint, format, type-check, security scan, secret scan, tests with ≥80% coverage on `corpus/` and `harness/`).
6. **At least 1 approving review required** before merge — enforced via branch protection.
7. **Linear history only** — squash or rebase merges. No merge commits on `main`.

## What CI checks

| Check | Tool | Threshold |
|---|---|---|
| Code style | `ruff format --check` | No formatting drift |
| Lint | `ruff check` | Zero warnings without inline `# noqa: <code>` + reason |
| Type safety | `mypy --strict` | Zero errors |
| Security (code) | `bandit -ll` | No medium-or-higher findings |
| Secret scan | `gitleaks` | Zero leaks (synthetic data allowlisted in `.gitleaks.toml`) |
| Tests | `pytest --cov` | All pass, ≥80% coverage on source dirs |
| Matrix | Python 3.11 + 3.12 | Both pass |

## Code standards

- **Python 3.11+**, full type hints
- `from __future__ import annotations` at the top of every module
- Google-style docstrings on every public function
- `pathlib.Path` for paths, never string concatenation
- `datetime.now(timezone.utc)` for time, never `datetime.now()`
- `logging` module for diagnostics, not `print` (exception: `__main__` CLI output)
- No bare `except:` — specific exception types, with logging that includes context
- **No real PII in tests or corpus, ever.** Faker only, with a seeded RNG and a comment naming the seed.

## Methodology decisions

Any change that affects the test corpus, the scoring rubric, or the harness measurement logic requires:

1. **Issue first**, describing the change and the rationale
2. **PR linked to the issue**
3. **Approval from at least one co-author or named peer reviewer** (not auto-merged via admin bypass)
4. **Update to `paper/paper.md`** methodology section if applicable
5. **Update to `CHANGELOG.md`** under `[Unreleased]`

These are the changes that affect benchmark *results*, so the review bar is higher than tooling changes.

## Reporting bugs

Use [GitHub Issues](https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark/issues). Helpful issues include:

- Python version and OS
- Output of `uv pip list`
- Steps to reproduce (the minimal commands)
- Expected vs. actual behavior

For security vulnerabilities, see [`SECURITY.md`](SECURITY.md) — do not open a public issue.

## What we don't accept

- **Vendor PR / counter-narratives.** The repo is for the research artifact, not for vendor debates. If your company is named in the benchmark and you dispute a finding, open a methodology issue with reproducible evidence — that's the only credible response.
- **Closed-source dependencies.** Every runtime dependency must be MIT, Apache-2.0, or BSD-licensed.
- **Real PII / credentials.** Any contribution containing real personal data, real API keys, or scraped human data will be rejected and the contributor blocked.
