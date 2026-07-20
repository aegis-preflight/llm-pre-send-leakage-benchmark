# Reviewing this benchmark

This document is for external reviewers of the *LLM Pre-Send Leakage
Benchmark v1.0*. It states a **bounded ask**, so reviewers can decide
whether to invest an evening or a week before opening the code.

## The ask, in three parts

1. **3-capture spot-check** (about 20 minutes). Pick any three rows
   from `results/results_v1.csv`, open the corresponding raw capture
   under `results/raw/<tool>.json`, and confirm that the captured
   `request_payload` actually contains the corpus payload. If it does
   not, the D1 score for that tool is wrong; open a GitHub Issue with
   the row and the mismatch.
2. **`harness/score.py` logic check** (about 30 to 60 minutes). Read
   `harness/score.py` and confirm that the per-prompt D1 score
   (0 if `sent_verbatim=True`, 2 if not verbatim and
   `outbound_findings` empty, 1 otherwise) is faithfully implemented,
   and that the mean-to-bucket thresholds (0.5 and 1.5) match the
   text in paper `§3.4`. If there is a discrepancy, the paper is
   wrong.
3. **`§6` framing challenge** (as long as you want). The Discussion
   section makes four claims and asks four open questions. Reviewers
   are invited to challenge any of the claims and to answer the open
   questions. Feedback on framing is at least as valuable as
   feedback on code.

## The no-API-key path

Every review step above can be done without a paid API key:

```bash
git clone https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark.git
cd llm-pre-send-leakage-benchmark
make dev-install
make verify-corpus         # asserts byte-identical corpus under DEFAULT_SEED=20260623
make harness-all-dry       # 4 API harnesses, dry-run, no API calls, no cost
```

Both commands together take under a minute on a typical laptop and
produce all the artifacts a reviewer needs to spot-check step 1 and
audit step 2. Step 3 requires only reading `paper/paper.md` `§6`.

## Where feedback goes

- **GitHub Issues** on the repository, with the `review` label:
  https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark/issues/new?labels=review
- Please include:
  - The reviewer's name and affiliation (or an anonymous handle if
    preferred; both are welcome).
  - Which of the three ask categories the feedback addresses.
  - A concrete pointer (row ID, file path with line number, or
    section number) so the maintainer can respond precisely.

Issues opened with the `review` label are tracked publicly and
resolved (accepted, deferred, or disputed with reasoning) before the
next tagged release.

## From placeholder to named reviewer

The paper's `§9 Acknowledgments` currently lists reviewer slots as
placeholders. Names move from placeholder to named only when the
reviewer:

1. Confirms their review scope (which of the three asks they
   completed);
2. Explicitly acknowledges that their name and affiliation may be
   published in `paper/paper.md`, `README.md`, `CITATION.cff`, and
   the top-level `REVIEWERS.md`;
3. Approves the wording of their acknowledgment.

If any of the three is missing, the reviewer stays as a placeholder
or is thanked anonymously (their choice). Nobody is named in the
paper without an affirmative opt-in.

## What is out of scope for the v1.0.0 review

- **Vendor negotiations.** The benchmark measures documented public
  behavior. If a vendor disputes a rubric value, they should open a
  GitHub Issue with a specific citation; the `verification` column
  will move from `unverified` to `verified` when the dispute is
  resolved with a documented URL. Reviewers are welcome to flag
  disputes but are not asked to mediate them.
- **Full 20-tool coverage.** v1.0.0 explicitly ships as a
  methodology-and-baseline release; only 2 of 20 tools are measured.
  Reviewers should treat the unmeasured rows as pending, not as
  claims to be defended.
- **Long-form paper editing.** Prose-level copyediting is welcome
  but not the primary ask; the maintainer can absorb copy edits
  post-review. The three asks above are what the maintainer cannot
  do alone.

## Contact

The maintainer is reachable via:

- GitHub Issues (preferred): the `review` label.
- Repository contact block in `CITATION.cff`.
- Aegis Preflight org contact at [aegispreflight.com](https://aegispreflight.com).
