## Likely technical questions

**1. "Walk us through a reporting process you automated end to end."**
Use STAR Story 6: a Moody's valuation workflow was spreadsheet-driven with limited logging and no versioning, which was not defensible under model-governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, and cut over with a rollback plan. The governance audit closed satisfactorily and the pipeline became the template for adjacent workflows.

**2. "How do you gather requirements when Finance users can't articulate what they need?"**
Use STAR Story 3: during the Calypso to PFaroe migration, a pension client's ALM configuration requirements were being lost between their investment desk and our development team. I scoped requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated developer pushback back into investment language. The client onboarded on schedule and the pattern was reused across the migration cohort.

**3. "What do you know about the metrics Finance teams here track - risk, performance, valuation, expenses?"**
Anchor on evidence: delegated sign-off on valuation and sensitivity outputs for $5-25bn portfolios at Moody's; VaR/CVaR surplus optimization, risk decomposition and contribution-to-risk analysis on Ortec GLASS; funded-status and duration-gap analytics across pension mandates. Be explicit that expense and FP&A reporting is adjacent rather than owned, and that the pension liability and investment-risk content is where I add value on day one.

**4. "Give an example of building a solution where there was no precedent."**
Use STAR Story 1: the buy-side team had no forward-looking liquidity visibility across multi-asset horizons, only manual spreadsheets. I designed configurable time-bucketed cash-flow analytics from T+1 to multi-year, embedded behavioural and prepayment assumptions and macro stress overlays, and re-engineered the upstream workflow into auditable Python. It shipped to production and unlocked analysis clients had been asking for.

**5. "How do you ensure one source of truth and data quality across stakeholders?"**
Use STAR Story 2 plus model-governance committee membership: I held a client release when portfolio sensitivities passed every internal check but did not square with economic intuition, decomposed by asset class, found a curve-calibration edge case, and escalated. The release slipped 48 hours, the client avoided acting on wrong numbers, and the defect was captured in validation tests. Data governance is documentation, reconciliation, and a named escalation path, not a dashboard.

## Questions Saber should ask

1. How is the DA&I prioritized opportunity list actually ranked today - by Finance team demand, by data readiness, or by executive sponsorship - and where does this Manager sit in that decision?
2. Where does the boundary sit between this team and EOD Data & Analytics: does Finance DA&I own semantic/data models and the BI layer, with EOD owning pipelines and infrastructure?
3. Which recurring deliverables (QBR, Audit & Actuarial Committee material) are still manually assembled, and what has blocked automation so far - data lineage, source-system access, or reviewer sign-off habits?

## The one competency gap to prepare

**Power BI / Collibra / Snowflake as named tools.** Saber has Python (pandas, NumPy, Plotly), advanced Excel, SQL on PostgreSQL, and R - but no shipped Power BI dashboards, no Collibra data-dictionary administration, and no Snowflake. Prepared answer: "My visualization and reporting layer has been Python and Excel rather than Power BI, and my data-catalogue work has been documentation and metadata standards inside a model-governance framework rather than Collibra specifically. The underlying skills - dimensional thinking, SQL, defining a metric once and defending it - transfer directly, and I would expect to be building production Power BI within weeks, not months." Do not overclaim; ramp-up honesty plus a concrete learning plan lands better than a bluff that fails a screen-share test.