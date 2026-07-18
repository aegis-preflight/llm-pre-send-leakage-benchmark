# `paper/` — v1.0 paper draft

This directory holds the paper for the LLM Pre-Send Leakage Benchmark v1.0.

## Files

- **`paper.md`** — DRAFT scaffold. Structure is locked; prose gaps are
  marked `[TODO: ...]`. Every gap is a decision that needs to be made
  before the v1.0.0 tag (2026-07-23).

## Authoring convention

**Prose is the human's job.** The `[TODO: ...]` markers exist so the
author (Bikram + co-authors + external reviewers) decides the exact
wording, framing, and emphasis.

**Numbers, tables, and citation URLs are loaded mechanically.** Never
hand-copy a score from `results/results_v1.csv` or a URL from
`harness/rubric/tool_metadata.toml` into the paper — reference by
path. When the paper is built (Pandoc, Quarto, or a static-site
generator; TBD), a build-time step reads those files and substitutes
the values. That way the paper stays in lockstep with the harness and
never carries stale numbers.

## Section map

| § | Section | Status |
|---|---|---|
| Abstract | 200 words | TODO |
| 1 | Introduction | TODO |
| 2 | Threat model | TODO |
| 3 | Methods | mostly-fixed; corpus + detector + harness + rubric structure locked |
| 4 | Results | skeletal; depends on captures landing |
| 5 | Limitations | drafted; needs numbers |
| 6 | Discussion | TODO |
| 7 | Acknowledgments | TODO |
| 8 | References | TODO — will render from rubric TOML |
| App A | Raw data pointers | done |
| App B | Reproducing the benchmark | done — mirrors REPRODUCING.md |
| App C | Change log | done through 2026-07-18 |

## Not in this directory (yet)

- **Rendered PDF / HTML.** The site tooling ships in a follow-up PR
  (currently sketched as ""PR #6.5"" in REPRODUCING.md). Options being
  weighed: static HTML page (simplest, ~few hours), Quarto notebook
  page (reproducible-first, ~3 days), interactive D3 microsite
  (eye-candy, ~2 days). v1.0 leans toward static HTML with a
  placeholder for the interactive version in v1.1.
- **Bibliography file (`.bib`).** Deferred until §8 references are
  finalized.
- **Figures.** Any figure needed will be generated from
  `results/results_v1.csv` by a build script — no committed image
  files that could drift from the data.
