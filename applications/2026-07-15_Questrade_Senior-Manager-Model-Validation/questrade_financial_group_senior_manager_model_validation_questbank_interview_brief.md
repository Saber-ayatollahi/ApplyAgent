## Likely Technical Questions

**1. Walk me through how you'd validate a credit scoring / origination model.**
Frame it as the four pillars in the JD: conceptual soundness (is the methodology fit for purpose and unbiased), data quality and suitability, implementation correctness, and ongoing performance monitoring. Tie to Story 9 - sign-off is attestation of defensibility of specific outputs, delegated by role within a formal governance framework, not a rubber stamp. Be honest that my direct credit-scoring build experience is adjacent (scenario/ALM/derivatives models), but the validation framework is identical.

**2. How have you handled a model output that passed checks but was still wrong?**
Use Story 2 verbatim: portfolio sensitivities passed internal checks but conflicted with client economic intuition under a rate-shock scenario; I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case (short-end inversion handling), escalated to product owners and the client's Head of Risk, and got it remediated upstream into validation tests. 48-hour delay, wrong action avoided, became their escalation contact.

**3. What do you know about ECL / IFRS 9 model validation?**
Be honest and precise: at EY I delivered IFRS 9 (and IFRS 17) transformation for Canadian insurers - governance documentation, regulatory readiness, aligning standards with implementation. I understand ECL mechanics (PD/LGD/EAD staging, forward-looking macro overlays) conceptually and from the transformation side. I have not personally built a bank ECL model - I'd frame my strength as the validation and governance discipline plus the macro-scenario/stress modeling that feeds ECL.

**4. How would you assess an AI/ML model for fairness, robustness, and defensibility?**
Conceptual soundness first (is ML the right tool, is the feature set defensible), then data quality/leakage checks, out-of-sample and out-of-time performance, stability/drift monitoring, and explainability for challenge. Reference agentic-AI workflows (Story 7) - I use Claude Code/Cursor for validation scaffolding and anomaly detection but a human signs off on governance-critical review; ML must not become a black box that escapes challenge.

**5. How do you document and communicate validation findings to non-technical stakeholders?**
Story 4/5: I've presented to pension investment committees and reconciled finance/actuarial/IT on IFRS 17. Lead with the risk decision, not the math; quantify materiality; give a clear remediation path. My reports are structured around findings, severity, and recommendations - decision-ready for model owners and senior management.

## Sharp Questions to Ask

1. How is the validation function structured relative to model development and the three-lines-of-defense - and how much of the current book is AI/ML vs. traditional statistical credit models?
2. Where is Questbank on its OSFI E-23 readiness (effective May 2027), and how much of this role is building the validation framework vs. running an established one?
3. How does QFG operationalize its 'AI-driven innovation' mandate inside model risk specifically - are validators tooling up with AI, and where are the guardrails?

## The One Competency Gap to Prepare

**Hands-on retail credit model development (credit scoring, account management, bank ECL under IFRS 9).** The repo evidences validation/governance depth, stochastic and scenario modeling, and EY-side IFRS 9 transformation - but not personally building retail credit origination or bank ECL models. Own it directly: position the transferable validation framework and macro/scenario modeling as the core, be candid that the specific retail-credit build is adjacent, and show fast-ramp credibility via the statistical foundation, Python, and CFA/dual-MSc quant depth. Do not claim credit-scoring or ECL model development on the resume.