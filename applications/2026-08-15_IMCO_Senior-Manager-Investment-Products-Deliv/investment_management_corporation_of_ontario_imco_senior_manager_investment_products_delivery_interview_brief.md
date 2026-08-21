## Likely technical questions (with model answers)

**1. "Walk me through how you'd gather and document business requirements from an investment team that doesn't know what it wants."**
At Moody's, during the Calypso-to-PFaroe migration, a pension client's ALM configuration requirements were being lost between their investment desk and our development team. I scoped the requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated dev pushback back into investment language. The client onboarded on schedule and the configuration pattern was reused across the rest of the migration cohort — that reuse is the real test of whether requirements were documented properly.

**2. "How would you build a data validation framework for converted data and incoming feeds — reasonability, accuracy, completeness?"**
I ran this pattern when migrating a spreadsheet-driven valuation workflow to Python under model-governance audit: parallel-build, shadow-run for two cycles, reconcile line-by-line, then cut over with a rollback plan. Accuracy and completeness are reconciliation tests against the source of truth; reasonability is the harder one — it needs economic tolerance bands set with the business, not just IT. I'd instrument the pipeline with logging and exception routing so breaks surface as owned items, not as silent drift.

**3. "Tell me about a time you held the line on a number under delivery pressure."**
A client run produced portfolio sensitivities that passed every internal check but didn't square with the client's economic intuition under one rate-shock scenario. I held the release, decomposed sensitivities by asset class, and traced it to a curve-calibration edge case in short-end inversion handling. I escalated to the product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**4. "You've worked mostly with public and liability-side data. What changes with private markets data?"**
Honest answer: my depth is multi-asset public markets, actuarial liabilities, and total-portfolio analytics — at Ortec I modelled every major investment-product type against liabilities and economic variables for SAA work, which included private-asset sleeves at the allocation level. What I haven't owned is deal-level private markets monitoring. The differences I'd expect to manage are valuation lag and staleness, capital call and distribution cash-flow modelling, look-through exposure, and manager-reported data quality — all of which make the data dictionary, source-of-truth mapping, and validation tolerances the central design problem rather than a compliance afterthought.

**5. "How do you prioritize a backlog when PE, Credit, Infrastructure and Real Estate all want their thing first?"**
I'd sequence on two axes: dependency (what unblocks the most downstream capability — usually reference data and the integrated data layer) and decision value (which reporting gap is actually changing an investment or oversight decision this quarter). At Moody's I sequenced PO requests the same way, and I surfaced the trade-off explicitly to stakeholders rather than absorbing it silently — that transparency is what keeps senior stakeholders trusting the roadmap when their item moves.

## Questions Saber should ask

1. "Where does the integrated platform stand today — is this a greenfield design phase, or are you stabilizing and extending selections already made (portfolio monitoring, CRM, ETL, BI)?"
2. "Who owns the source of truth for private markets valuations and cash flows today — Investment Operations, Finance, or the deal teams — and what breaks most often between them?"
3. "How is success measured for this seat at the 12-month mark: delivered capability, adoption by the investment teams, or reduction in manual reporting effort?"

## The competency gap to prepare for

**Private markets portfolio monitoring tooling and BI stack.** The JD names Chronograph, iLevel, Yardi, AllVue, Burgiss, 73 Strings, Aladdin, Bloomberg, plus Tableau/Power BI. Saber has none of these hands-on; his platform depth is PFaroe DB / PFaroe PM / Calypso / Ortec GLASS, with Python, SQL, Excel and Plotly for visualization. Prepare a 30-second answer: name the platforms he has implemented, describe the transferable pattern (requirements -> configuration -> validation -> adoption), and state plainly that he has learned three institutional platforms from cold and expects to do the same here. Do not bluff a tool name.