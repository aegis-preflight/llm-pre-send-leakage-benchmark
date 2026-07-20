# Per-vendor terms review (v1.0.0)

Dated evidence for the paper's claim (`paper/paper.md` §7 Ethics and
Legal Considerations) that each vendor's terms of service were
reviewed for benchmark-publication restrictions before the v1.0.0
harness run.

For every vendor covered by the v1.0.0 measured subset or by the
verified/partial rubric rows, this file records the URL that was
reviewed, the date of retrieval, the specific clause examined, and
the review conclusion. Unverified rubric rows are not included here;
their retrieval is scheduled for v1.0.1.

| Vendor | URL reviewed | Retrieval date (UTC) | Clause examined | Review conclusion |
|---|---|---|---|---|
| OpenAI API | https://openai.com/policies/row-terms-of-use/ | 2026-07-20 | Sections on "Usage requirements" (permitted use of the API, benchmarking / performance testing), "Content" (customer inputs and outputs), and "Publicity" | Paid-account programmatic use via the published SDK is the intended usage pattern. Publishing aggregate measurements of client-side SDK behavior and vendor endpoint responses is not prohibited. No trademark or "OpenAI" branding used in a manner requiring separate publicity approval. |
| OpenAI API (data usage) | https://platform.openai.com/docs/models#how-we-use-your-data | 2026-07-20 | API data-usage default (no training on API data unless opted in) | Cited in `paper/paper.md` §10 as `unverified` because the WebFetch during the PR #16 rubric verification pass returned HTTP 403; the value used in the rubric matches the widely-cited default. Confirmed against the OpenAI enterprise privacy page during this review. Retained as `unverified` in the rubric pending a machine-readable fetch. |
| Anthropic API | https://www.anthropic.com/legal/commercial-terms | 2026-07-20 | Sections on "Customer Content" (no training on customer content), "Publicity" (mutual approval for co-marketing) | Paid programmatic use is permitted. Publishing aggregate measurements is not prohibited. No co-marketing implied by this paper; the Anthropic API row is a measurement subject, not a partner endorsement. |
| Claude.ai (retention) | https://privacy.anthropic.com/en/articles/10023548-how-long-do-you-store-personal-data | 2026-07-20 | Retention windows (30 days default, up to 5 years with opt-in, 2 years for flagged content, 7 years for trust-and-safety scores) | Consumer product; retention documented verbatim in the rubric. Not measured in v1.0.0 (web capture is a v1.1 target). |
| AWS Bedrock | https://aws.amazon.com/bedrock/faqs/ | 2026-07-20 | Data-handling FAQ ("AWS and the third-party model providers will not use any inputs to or outputs from Amazon Bedrock to train...") | Cited verbatim in the rubric. Bedrock harness run deferred to v1.0.1 by a payment-instrument state on the test account, not by any terms restriction. |
| Azure OpenAI | https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/abuse-monitoring | 2026-07-20 | "prompts and completions are not used to train, retrain, or improve the base models" + abuse-monitoring opt-out mechanism | Cited verbatim in the rubric. Azure OpenAI capture deferred to v1.0.1. |

## Notes on scope

- **What this file is for.** Concrete, dated evidence to back the
  paper's §7 claim. Not a substitute for the rubric metadata itself
  (`harness/rubric/tool_metadata.toml`), which remains the
  machine-readable canonical source for D4 values and citation URLs.
- **What this file is not.** Not a legal opinion. Not a claim that
  any vendor has approved this benchmark. Not a guarantee that
  vendor terms will not change post-publication; the retrieval dates
  above pin the snapshot each row was reviewed against.
- **Update policy.** New vendors added to the rubric or existing
  rows moved from `unverified` to `verified` should add or update a
  row here on the same PR. The retrieval date column is the audit
  trail.

## Access-restricted URLs

Two documentation URLs relevant to the rubric returned an HTTP 403
during the PR #16 automated verification pass:

- `https://platform.openai.com/docs/models#how-we-use-your-data`
  (bot-blocked; human-readable via a signed-in session)
- `https://help.openai.com/en/articles/5722486-how-your-data-is-used-to-improve-model-performance`
  (bot-blocked; human-readable via a signed-in session)

Both were opened manually in a browser during this review and their
content matched the values already in the rubric. The `unverified`
status is retained in `harness/rubric/tool_metadata.toml` because
the underlying automation still cannot fetch them; a manual override
would silently invalidate the machine-verification guarantee for
future rows.
