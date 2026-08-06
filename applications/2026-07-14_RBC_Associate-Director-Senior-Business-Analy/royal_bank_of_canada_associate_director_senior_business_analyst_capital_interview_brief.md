## Likely technical questions

**1. Walk me through how you turn an ambiguous business request into a data specification.**
Use Story 3 (bridging client investment team and dev org): scope the business decision logic first, structure it into Product Owner requests, then translate dev pushback back into business language. Emphasize documenting success/acceptance criteria and validating outputs post-deployment — the exact BA loop RBC describes.

**2. How do you ensure data quality and validation on a client-metrics or profitability calculation?**
Draw on the security-level to portfolio-level aggregation review and the model-governance committee role: independent review of aggregation logic, economic-defensibility checks, and Story 2 (held a release that passed all checks but was economically wrong — decomposed by asset class, found a curve-calibration edge case, escalated). Frame as validation protocols + escalation processes.

**3. Show me how you'd use SQL / data modeling on a large, data-intensive initiative.**
Cite the spreadsheet-to-Python/PostgreSQL pipeline migration (Story 6) run in shadow mode for two cycles with reconciliation and a rollback plan. Honest scope: Python advanced, SQL intermediate (PostgreSQL day-to-day). Be ready to talk through joins, validation queries, and reconciliation logic rather than claim data-warehouse architecture.

**4. Describe a large-scale delivery you led end-to-end.**
Story 1 — the enterprise cash-flow projection engine: scoping, requirements, design of time-bucketed analytics, engineering handoff, and production release. Cover milestones, risks, and business impact (forward-looking liquidity visibility clients were asking for; manual-time reduction).

**5. How do you influence senior stakeholders when they disagree with your analysis?**
Story 2 / Story 4: held the line on a wrong-but-passing output under deadline pressure and became the client Head of Risk's direct escalation contact; and the Ortec LDI study that shifted a committee's SAA. Hold analytical integrity while preserving the relationship.

## Sharp questions for Saber to ask

1. How mature is the current Client Revenue Analytics / Client Wallet data foundation — are we defining specs greenfield, or migrating and rationalizing existing reference data?
2. Where does the profitability calculation logic live today, and who owns the reconciliation between Risk and Finance figures?
3. What does the Agile operating model look like across the BA, engineering, and front-office stakeholder groups — how are acceptance criteria signed off?

## The one gap to prepare for

**Direct Capital Markets front-office product depth (credit exposures, new issuances, trade lifecycle, CIB/Global Markets trades) and Tableau/AWS-Azure hands-on.** The JD wants 10 years and CM product fluency; Saber has ~7 years and buy-side/ALM/risk-analytics depth, not sell-side desk experience. Own it honestly: position transferable strength (risk metrics, return calculations, reference-data governance, requirements-to-engineering translation) and frame CM product knowledge as fast-ramp adjacent — do NOT claim trade-lifecycle or Tableau/cloud-build experience the repo doesn't support.