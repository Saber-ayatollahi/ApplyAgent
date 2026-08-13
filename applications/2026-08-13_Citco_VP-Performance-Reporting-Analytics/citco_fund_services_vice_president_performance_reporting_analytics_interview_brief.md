# Interview Brief — Citco, VP Performance Reporting & Analytics

## 5 likely technical questions + model answers

**1. "Walk me through how you'd stand up liquidity forecasting and commitment pacing for a multi-asset institutional client."**
At Moody's I led the design of an enterprise multi-asset cash flow projection engine supporting base, stress, and reverse-stress scenarios, with configurable time-bucketed liquidity gap analytics from T+1 out to multi-year horizons. The hard part is not the buckets — it's the behavioral layer: embedded prepayment logic, behavioral cash flow assumptions, and macro stress overlays, each documented so a client's Head of Risk can challenge it. Same skeleton applies to commitment pacing: contractual flows plus behavioral drawdown/distribution assumptions, scenario-toggled.

**2. "What risk analytics have you actually produced for institutional portfolios — VaR, attribution, stress?"**
At Ortec Finance I ran asset-only and asset-liability (surplus) portfolio optimization on VaR and CVaR using the GLASS platform, with risk decomposition and contribution-to-risk attribution, and explored near-optimal portfolios around the efficient frontier to test whether allocation recommendations were robust rather than knife-edge. Stress and scenario work came from stochastic economic scenario generators I built and calibrated, used to show funding-ratio distributions under base and stressed regimes.

**3. "How do you ensure reported analytics reconcile to the underlying accounting/position data?"** *(STAR Story 6)*
A valuation workflow at Moody's was spreadsheet-driven with limited logging and no versioning — not defensible under governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, then cut over with a rollback plan. The audit closed cleanly and the pipeline became the template for adjacent workflows. That shadow-run-then-reconcile pattern is how I'd de-risk any reporting migration at Citco.

**4. "Tell me about a time you refused to release a number."** *(STAR Story 2)*
A client run produced portfolio sensitivities that passed every internal check but didn't square with the client's economic intuition under one rate-shock scenario. I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case in short-end inversion handling, and escalated to the product owner and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**5. "You'd be client-facing with pensions, endowments and SWFs — evidence?"** *(STAR Stories 3 & 4)*
Two angles. At Ortec I presented ALM and LDI studies on-site to Canadian pension investment committees, including a duration-extension recommendation the committee adopted. At Moody's I led onboarding for U.S. and Canadian pensions, asset managers, and consultants onto PFaroe DB and PFaroe PM, acted as technical liaison to Product, and today serve as escalation contact for client Heads of Risk on analytics disputes.

## 3 questions Saber should ask
1. Where does the Data Analytics team's mandate currently stop — do you own the performance-measurement calculation layer (TWR/MWR, Modified Dietz) internally, or is that produced upstream in fund accounting and the team's job is aggregation, analytics and client narrative?
2. How is the Solovis footprint evolving relative to Citco-built tooling and the fund-accounting data pipeline — is the 12-month priority platform consolidation, automation of existing reporting, or net-new analytics products for RFP wins?
3. What does the distributed team look like today — headcount by location, current delivery-standard maturity, and which two or three failure modes you'd want a new VP to fix in the first six months?

## The one competency gap to prepare for
**Performance-measurement mechanics and private-markets metrics.** The repo evidences risk attribution (contribution-to-risk, risk budgeting), not Brinson/factor performance attribution, Modified Dietz, TWR/MWR, GIPS, or PME/TVPI/DPI/RVPI. Prepare a crisp, honest position: I have built and validated the return- and cash-flow engines beneath these metrics and can derive them from first principles; I have not owned a GIPS-compliant composite or a private-markets IRR production process. Before interviews, revise Modified Dietz vs. true daily TWR, MWR/IRR mechanics, Brinson allocation-selection-interaction decomposition, and PME construction so the answer is technically fluent rather than defensive. Second, smaller gap: people leadership — frame honestly as senior-review authority and mentorship inside a ~12-person Modelling Services team, plus cross-region client/product coordination, not direct management of a distributed global team.