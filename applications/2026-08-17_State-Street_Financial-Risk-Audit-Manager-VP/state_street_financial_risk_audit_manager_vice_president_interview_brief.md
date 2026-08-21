## Likely technical questions

**1. "Walk us through how you would scope an audit of the firm's interest rate risk measurement process."**
Start from where the numbers are produced: curve construction and calibration inputs, behavioural assumptions (prepayment, non-maturity deposits), the shock library (parallel and non-parallel), and the aggregation logic that converts security-level exposures into portfolio-level metrics. At Moody's my independent review covers exactly those four layers before production release, so I would test each for assumption ownership, documented rationale, benchmarking evidence, and change control — then trace a sample result end-to-end.

**2. "Give an example of effective challenge where you held the line."**
(STAR Story 2) A client run produced portfolio sensitivities that passed every internal check but contradicted economic intuition under a specific rate shock. I held the release, re-ran sensitivities decomposed by asset class, isolated a short-end inversion edge case in curve calibration, escalated to product owners and the client's Head of Risk, and walked through remediation. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was captured in validation tests and I became that Head of Risk's direct escalation contact.

**3. "How do you assess whether a liquidity risk framework is adequately controlled?"**
I look at whether cash-flow projections are reproducible, whether behavioural and stress overlays are evidenced rather than asserted, and whether the time-bucketing supports the decisions being made from it. I designed a configurable T+1-through-multi-year liquidity gap engine with base, stress, and reverse-stress scenarios, so I know where these frameworks typically break: undocumented assumption overrides and spreadsheet steps with no logging.

**4. "You have sign-off authority as an Assistant Director — explain that."**
(STAR Story 9) Moody's delegates sign-off by role within a formal governance framework, not by title. The role is IC-with-independent-review authority: I attest to the defensibility of specific analytical outputs — valuation, sensitivity, ALM — not to a client's investment strategy. That distinction is the same one a third-line reviewer draws between opining on control design and owning the risk.

**5. "How would you upgrade a control environment you found weak?"**
(STAR Story 6) I migrated a spreadsheet-driven valuation workflow that had no logging or versioning into a Python pipeline: parallel-built, run in shadow mode for two cycles, reconciled output, then cut over with a rollback plan. The governance audit closed satisfactorily and the pipeline became the template for adjacent workflows. Sustainable remediation beats an issue write-up that only survives one cycle.

## Questions Saber should ask

1. How does Corporate Audit currently split coverage between the financial risk frameworks themselves and the models feeding them — and where does this VP's mandate sit on that line?
2. Where has effective challenge from the third line most recently changed a first- or second-line practice at State Street? I would like to understand how much influence the seat actually carries.
3. What does the team's maturation agenda look like over the next 18 months — methodology, data-driven testing, or coverage expansion — and which of those would this role own?

## The one competency gap to prepare for

**Credit risk, including Trading Credit, and formal internal audit methodology.** Saber has no counterparty credit, PFE, or xVA experience and has never run an audit under IIA standards (no workpaper review, no formal audit plan ownership). Prepare a direct, unapologetic answer: name the gap first, then bridge — credit-spread calibration review inside multi-asset portfolios, exposure aggregation logic, and a governance-framework mindset (independent review, documentation standards, escalation) that transfers to any risk stripe. Offer to be tested on the risk stripes he owns and be explicit that credit framework mechanics are a 90-day learning commitment, not a claimed skill. Also rehearse the tenure answer: ~7 years professional against a 10+ ask — lead with the seniority of the mandate (sign-off authority, governance committee) rather than the year count.