# Security Policy

## Reporting a vulnerability

If you find a vulnerability in this benchmark's harness, corpus generator, or methodology that could:

- Expose real PII (the corpus is synthetic but a generator bug could change that)
- Leak credentials in CI or test runs
- Allow malicious replication of the test against real systems without consent
- Misrepresent results in a way that misleads readers or downstream citations

Please report it **privately** rather than opening a public issue.

**Contact:** `security@aegispreflight.com`

You should expect acknowledgment within 24 hours and an initial assessment within 3 business days.

## Disclosure timeline

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure):

| Stage | Target |
|---|---|
| Acknowledgment | within 24 hours |
| Initial assessment shared with reporter | within 3 business days |
| Fix landed in repo OR mitigation plan agreed | within 14 days |
| Public disclosure (coordinated with reporter) | within 30 days |

Credit will be given in the changelog and (where relevant) the paper acknowledgments unless the reporter prefers anonymity.

## Scope

### In scope

- Bugs in `corpus/generate.py` that could produce non-synthetic output
- Bugs in `harness/` that could leak credentials, real data, or environment variables
- Methodology issues that produce systematically misleading benchmark results
- CI / build pipeline issues that could compromise the published artifact or introduce supply-chain risk
- Dependency vulnerabilities with active exploitation paths in our code

### Out of scope

- **Issues with the AI tools being benchmarked themselves.** Report those to the respective vendors. This benchmark observes their behavior; we do not own their security.
- **General Q&A or security advice.** Use [GitHub Discussions](https://github.com/aegis-preflight/llm-pre-send-leakage-benchmark/discussions) instead.
- **Issues with Aegis Preflight's commercial product.** Report to the Aegis security team via [aegispreflight.com](https://aegispreflight.com). The product and this research artifact are separate; this policy is for the research artifact only.

## What we explicitly do not do

- Pay bug bounties for this repo. It's a research artifact, not a commercial product.
- Block public disclosure indefinitely. We aim for 30 days from report to public; longer timelines require reporter agreement.
- Engage with reports that include real, non-consenting PII or scraped personal data.
