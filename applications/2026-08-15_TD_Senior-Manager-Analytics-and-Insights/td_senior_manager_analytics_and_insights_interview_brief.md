## Likely technical questions (with model answers)

**1. "Walk me through a manual reporting process you automated end to end."**
At Moody's a valuation workflow was spreadsheet-driven with limited logging and no versioning - unacceptable under model-governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two production cycles, reconciled output line by line, then cut over with a rollback plan. The governance audit closed satisfactorily and the pipeline became the template for adjacent workflows. (STAR Story 6)

**2. "Tell me about a time you challenged a result that looked fine."**
A client run produced portfolio sensitivities that passed every internal check but did not square with economic intuition under one rate shock. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case, and escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and the defect was captured in validation tests. (STAR Story 2)

**3. "How do you turn a deep-dive analysis into something an executive acts on?"**
At Ortec I ran funding-ratio distributions under base and stressed regimes for a pension client, decomposed duration-gap contribution to volatility, and presented an explicit recommendation - not a data dump - to the investment committee. They adopted the recommendation and returned for further studies. The rule I work to: lead with the decision, support with two or three numbers, keep the full analysis in the appendix. (STAR Story 4)

**4. "What is your tooling stack for analytics and reporting?"**
Python (pandas, NumPy, SciPy) daily for pipelines and analytics; SQL/PostgreSQL day to day for data extraction; advanced Excel; Plotly and matplotlib for visualization; Git and CI/CD for versioning; Claude Code and Cursor for automated code review and validation scaffolding. Be direct: Tableau/Power BI and Databricks are not in my production history - the semantic-layer and data-modelling thinking transfers, and I would expect to be productive in a BI tool within weeks, not months.

**5. "How would you approach anomaly detection on availability and incident data?"**
Same pattern I use on portfolio data: define the expected behaviour first (baseline by system, geography, change window), then flag deviations against it rather than against a static threshold. I already run automated anomaly-detection scaffolding inside my validation workflows at Moody's, and I built time-bucketed analytics (T+1 through multi-year) at Moody's where the whole point was surfacing where a gap emerges, not just that one exists. (STAR Story 7 + cash-flow engine)

## Three questions Saber should ask

1. What does the current reporting stack actually look like end to end - source systems, data warehouse, and the BI layer - and how much of the monthly/weekly pack is still assembled by hand?
2. When the VP takes resilience metrics to senior leadership, which two or three numbers do they get challenged on most, and what would 'better' look like in six months?
3. Where does this role's mandate stop relative to second-line risk and the GTS control functions - am I producing the measurement, or also owning the recommendation into recovery-process change?

## The one competency gap to prepare for

**Resilience domain fluency (BCM / DR / Availability / Operational Resilience) plus named BI tooling.** Do not claim either. Prepare a 60-second answer that (a) names the gap plainly, (b) pivots to the two domains learned cold and fast (IFRS 17 at EY in seven months; liquidity/behavioural cash-flow modelling at Moody's), and (c) shows homework - read TD's operational-resilience disclosures and OSFI B-13/E-21 style operational-resilience expectations before the interview so the vocabulary is at least credible. Also expect the '10+ years' filter: answer as ~7 years professional plus graduate financial-modelling work, never '10+'.