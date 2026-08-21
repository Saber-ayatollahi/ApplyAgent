# Interview Brief — Affirm, Senior Manager, Quantitative Analytics (MRM)

## 5 likely technical questions + model answers

**1. "Walk me through how you validate a model you didn't build."**
Start with conceptual soundness: what the model claims, whether the methodology fits the use case, and whether assumptions are economically defensible — not just internally consistent. Then data integrity (lineage, treatment of missing/edge data), then performance and stability testing, then documentation adequacy and ongoing-monitoring design. At Moody's this is my delegated sign-off process: I review curve construction, calibration, and cross-asset interactions before production release, and I escalate anything I can't defend mathematically or economically.

**2. "Tell me about a time you challenged a model output and were right." (STAR Story 2)**
A client-delivery run passed every internal check but produced portfolio sensitivities that didn't square with economic intuition under a specific rate shock. Under deadline pressure I held the release, re-ran sensitivities decomposed by asset class, and isolated a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was remediated upstream and captured as a validation test. I became that Head of Risk's direct escalation contact.

**3. "You've validated valuation and ALM models — how does that transfer to ML underwriting models?"**
The framework transfers directly: conceptual soundness, data integrity, performance stability, benchmarking, documentation, monitoring. What changes is the failure mode — for ML underwriting it's feature leakage, population drift, segment-level performance degradation, proxy-discrimination and fair-lending exposure, and overfitting hidden by a favourable out-of-time window. I'd own that learning curve explicitly rather than pretend the domains are identical; my quant foundation (dual MSc, stochastic/Monte Carlo, Python) is what makes the ramp short.

**4. "How do you build governance that developers don't route around?"** (STAR Story 6)
A Moody's valuation workflow was spreadsheet-driven with no logging or versioning — unacceptable under audit. Instead of blocking delivery, I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs, and cut over with a rollback plan. The audit finding closed and the pipeline became the template for adjacent workflows. Governance sticks when the compliant path is also the easier path.

**5. "How do you stay hands-on while leading a team?" (Story 7)**
I keep the hardest validation on my own desk and use tooling as the force multiplier for the rest. My validation workload was growing faster than headcount, so I built agentic review workflows in Claude Code and Cursor — automated first-pass code review, validation scaffolding, documentation drafts — with human sign-off retained on anything governance-critical. Cycle time on comparable modules dropped an estimated 30-40%.

## 3 questions Saber should ask

1. Within the underwriting pillar, where does the MRM framework currently feel thinnest — initial validation depth, ongoing monitoring triggers, or findings closure with model owners?
2. How is independence protected in practice between MRM and the credit/data-science org — reporting lines, veto rights, and what happens when a model owner disagrees with a finding?
3. What does the team look like today, and what is the hiring plan versus the validation inventory for the next four quarters?

## The one competency gap to prepare for

**ML underwriting and consumer credit risk domain depth, plus formal people-management.** The repo evidences validation, governance, and mentorship within a ~12-person team — not hiring/managing a team, and not credit-model development. Prepare: (a) a crisp, non-defensive framing of the domain ramp (framework transfers, domain specifics learned fast, first-90-days plan); (b) fluency in ML validation vocabulary — AUC/KS/Gini, PSI and population drift, SHAP/feature importance, out-of-time and segment testing, fair-lending/adverse-action considerations; (c) concrete mentorship examples (junior colleagues at Moody's, the three-person UPP team at Ortec) framed as leadership readiness rather than claimed management tenure.