# Changelog

All notable changes to this benchmark are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Dev tooling scaffold: `pyproject.toml` (Python 3.11+), mypy strict, ruff (lint + format), bandit (security), gitleaks (secret scan), pre-commit hooks.
- `Makefile` with `make help`, `make ci-precheck`, and all common dev tasks.
- GitHub Actions CI workflow — lint + format + type-check + security + secret scan + tests, matrix Python 3.11 + 3.12.
- Dependabot configuration — weekly updates for pip + GitHub Actions.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`.
- `.gitattributes` for cross-platform line ending consistency + Linguist hints.

## [0.1.0-wip] — 2026-06-29

Initial scaffold of the benchmark repository.

### Added
- `README.md` — public face describing scope, scoring rubric, corpus design, OWASP LLM06 alignment, timeline.
- `LICENSE` — MIT.
- `CITATION.cff` — machine-readable academic citation metadata.
- `.gitignore` — Python-focused, includes secrets and raw-capture tempfile patterns.
- `corpus/corpus_schema.md` — schema definition for the JSONL test corpus (locked at publication, never-real-PII rule, versioning policy).
- Branch protection on `main`: PR required, 1 approving review, dismiss stale on push, linear history, no force-push, no deletion.

Status: **Work in progress.** Paper + dataset publication target: **2026-07-23**.

[Unreleased]: https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark/compare/v0.1.0-wip...HEAD
[0.1.0-wip]: https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark/releases/tag/v0.1.0-wip
