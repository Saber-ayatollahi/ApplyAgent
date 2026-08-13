## Five likely technical questions

**1. "Portfolio VaR moved 40bps week-over-week. Walk me through how you find out why."**
Decompose before explaining: separate position/weight changes from market-data changes from model/parameter changes, then run contribution-to-risk by asset class and factor. At Ortec I did exactly this decomposition work (contribution-to-risk, risk budgeting) around VaR/CVaR optimization on GLASS; at Moody's I review the aggregation logic that turns security-level exposures into portfolio-level metrics, so I know where mis-mapped exposures and stale curves typically hide.

**2. "How do you validate a risk number you didn't produce?"** (Story 2)
Three layers: mathematical reproducibility, economic defensibility, and consistency across aggregation levels. On one delivery, sensitivities passed every internal check but contradicted the client's economic intuition under a specific rate shock. I held the release, re-ran sensitivities decomposed by asset class, isolated a short-end curve-calibration edge case, escalated to product owners and the client's Head of Risk, and got it fixed upstream with a validation test added.

**3. "Explain VaR vs CVaR and when you'd optimize on each."**
VaR is a quantile and ignores tail shape; CVaR averages the tail beyond it and is coherent/sub-additive, which makes it better behaved in optimization. At Ortec I ran both asset-only and asset-liability (surplus) optimizations on VaR and CVaR in GLASS, and deliberately explored near-optimal portfolios around the frontier because point-optimal solutions are fragile to input estimation error.

**4. "How do you make a manual reporting process reliable?"** (Stories 1 and 6)
Parallel-build, shadow-run, reconcile, cut over with rollback. I migrated a spreadsheet-driven valuation workflow into a Python pipeline with logging, validation, and versioning — ran shadow mode for two cycles, reconciled output, then cut over. It closed a governance audit and became the template for adjacent workflows. Same pattern for the multi-asset cash-flow projection engine I designed for base, stress, and reverse-stress scenarios.

**5. "How do you validate derivatives sensitivities across rates, FX, and inflation?"**
Check pricing outputs against independent recalculation, then test internal consistency: do bucketed key-rate durations sum to the total duration, do sensitivities behave monotonically under parallel and non-parallel shocks, do scenario P&L and delta-based approximations reconcile within tolerance at portfolio aggregates. Breaks in those identities almost always point to calibration or mapping issues rather than the pricer.

## Three questions to ask

1. Where does QAR's validation responsibility end and the risk-system vendor's begin today — which numbers does the team recompute independently versus reconcile?
2. How is the reporting stack split between Databricks/Power BI and Python-native analytics, and where is the team investing next?
3. How does risk analytics for private and illiquid asset classes get integrated into enterprise-wide measurement alongside public markets?

## The one competency gap to prepare for

**Named reporting/BI stack — Databricks, Power BI, Aladdin.** No hands-on production experience with any of the three. Prepared answer: "I've built the analytics and reporting layer in Python/SQL on a vendor risk platform (PFaroe DB/PM) and delivered stakeholder-ready risk summaries from it; I've used Plotly/matplotlib for visualization rather than Power BI, and I've been the vendor-side counterpart to Aladdin shops as a competitor. Picking up Power BI semantics and Databricks/Spark on top of advanced Python and SQL is a weeks-not-months curve — the harder part, knowing whether the number is right, is what I already do." Do not claim any of the three as experience.
