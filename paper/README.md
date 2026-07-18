# `paper/` — v1.0 paper draft

This directory holds the paper for the LLM Pre-Send Leakage Benchmark v1.0.

## Files

- **`paper.md`** — DRAFT scaffold. Structure is locked; prose gaps are
  marked `[TODO: ...]`. Every gap is a decision that needs to be made
  before the v1.0.0 tag (2026-07-23).
- **`build.py`** — Pandoc + Weasyprint pipeline. Regenerates HTML + PDF
  from `paper.md` in ~2 seconds.
- **`style.css`** — one stylesheet drives both HTML and PDF output.
  Print-safe, JS-free, no external CDNs.
- **`paper.html`** and **`paper.pdf`** *(generated, gitignored)* —
  written by `make paper`. Regenerate any time.

## Building the paper

Two prerequisites (one-time install):

```bash
# macOS
brew install pandoc pango

# Debian / Ubuntu
sudo apt install pandoc libpango-1.0-0

uv sync --extra paper
```

Then:

```bash
make paper         # renders HTML + PDF into paper/
make paper-html    # HTML only (skips weasyprint / PDF step)
make paper-clean   # remove generated artifacts
```

The `[TODO: ...]` markers in `paper.md` render as bright yellow
callouts in both HTML and PDF so reviewers can't miss unfinished
sections.

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

- **Bibliography file (`.bib`).** Deferred until §8 references are
  finalized.
- **Figures.** Any figure needed will be generated from
  `results/results_v1.csv` by a build script — no committed image
  files that could drift from the data. v1.0 ships raw tables only;
  charts wait until ≥ 4 tools are D1-measured to avoid publishing a
  chart of placeholders.
- **Interactive paper site.** The Pandoc HTML output IS the paper
  site for v1.0 — one page, hyperlinkable, embeddable, no
  interactivity. If v1.1 wants a filterable / drill-in dashboard,
  that becomes its own tooling PR.
