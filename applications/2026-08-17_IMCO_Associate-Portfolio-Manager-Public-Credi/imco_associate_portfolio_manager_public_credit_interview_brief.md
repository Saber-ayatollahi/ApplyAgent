## Five likely technical questions

**1. "Walk me through how you'd evaluate an external public credit manager's portfolio construction."**
Frame it as the review discipline I already run: decompose stated risk into contribution-to-risk and attribution, check whether realised exposures match the mandate's intended factor profile, and stress the portfolio under scenarios the manager did not choose. At Ortec I did exactly this on allocation recommendations — running near-optimal frontier analysis around the optimum so a recommendation had to survive perturbation, not just win a single optimisation. Be explicit that I've applied this to multi-asset mandates and would need to learn the manager-universe conventions of public credit.

**2. "How do you build a portfolio optimisation when the return distribution is fat-tailed — as credit is?"**
Mean-variance breaks down when the loss tail is asymmetric, which is why at Ortec I optimised on CVaR as well as VaR using the GLASS platform, on both asset-only and asset-liability (surplus) bases. CVaR is coherent and penalises tail severity rather than tail frequency; I'd pair it with stochastic scenario generation rather than a single historical covariance estimate. (STAR Story 4 — the LDI/SAA study — is the worked example.)

**3. "Tell me about a time you disagreed with a number that had already passed every check."**
Story 2: a client run produced portfolio-level sensitivities that passed all internal validation but contradicted the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, isolated a short-end inversion edge case in the curve calibration, escalated to product owners and the client's Head of Risk, and walked through remediation. 48-hour delay; client avoided acting on wrong numbers; I became their standing escalation contact.

**4. "You've talked about AI tooling — what have you actually shipped?"**
Story 7: validation workload was growing faster than headcount, so I built agentic workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts — human sign-off retained on anything governance-critical. Cycle time on comparable modules dropped an estimated 30-40%. Be precise about the boundary: the AI accelerates the analysis, it does not hold the judgement.

**5. "How would you improve investment data quality across Risk, Performance, Operations and Technology?"**
Story 6: I migrated a spreadsheet-driven valuation workflow into a Python pipeline by parallel-building it, running it in shadow mode for two full cycles, reconciling output line by line, and cutting over with a rollback plan — which closed a governance audit and became the template for adjacent workflows. The transferable point is that data-quality work only sticks when it runs in shadow against the incumbent long enough to prove itself.

## Three questions to ask

1. Within the ~$10.1B Global Credit strategy, how is the split between public and private credit governed — is capital allocation across segments a standing IC decision, or does the team hold discretion within bands?
2. What does the current manager-monitoring stack look like today, and where specifically does the MD feel the analytics are thinnest — style drift detection, attribution, or guideline adherence?
3. On the AI and investment-systems agenda: is there a defined target operating model already, or is the Associate PM expected to help define it alongside Risk, Performance and Technology?

## The one competency gap to prepare for

**Public credit security- and manager-level experience.** I have not selected external credit managers, negotiated fee arrangements, or traded/covered high yield, leveraged loans, or structured credit. Do not bluff this. Prepared answer: "I've been on the analytics, construction and independent-review side of institutional portfolios rather than in a credit selection seat. What I bring on day one is portfolio construction under CVaR, attribution and risk decomposition, scenario design, and the systems/AI build-out — and I'd expect to be climbing the segment-specific learning curve on structured credit and loans in the first two quarters, which I'd rather name now than discover later." Before interview: do genuine reading on leveraged loan vs. HY covenant and recovery dynamics, CLO tranche mechanics, and the current spread/technical backdrop, so the market-view conversation is credible even though the seat time isn't there.