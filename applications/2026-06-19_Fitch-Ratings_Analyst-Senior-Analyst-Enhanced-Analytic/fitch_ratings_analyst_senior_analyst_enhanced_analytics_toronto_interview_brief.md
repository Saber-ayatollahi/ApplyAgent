## Likely Technical Questions

**1. Walk us through a time you connected data from disparate sources to surface a non-obvious insight.**
Use Story 1 (cash-flow projection engine): the team needed forward-looking liquidity visibility but data lived in security masters, market-data feeds and client position files. I designed time-bucketed analytics joining these sources in Python, embedded behavioral assumptions, and surfaced refinancing-risk concentrations that the prior spreadsheet view had hidden. Emphasize the data-engineering judgment (key choices, schema reconciliation) not just the financial output.

**2. How do you approach building an Excel/VBA application that analysts will actually use day-to-day?**
Draw on the spreadsheet-to-Python migration (Story 6) but invert it for Excel: analysts want speed, transparency and a familiar interface. Approach: separate the calc layer from the UI, version-control the VBA, write reconciliation tests against a Python reference, and shadow-run before cutover. The PFaroe onboarding work (Story 3) shows the same instinct - translate analyst needs into structured requirements.

**3. Describe your SQL/Python workflow when mining a large data set you have not seen before.**
Profile first (row counts, null rates, key cardinalities), then build a small reproducible notebook with parameterized SQL pulls, then push stable logic into a pipeline with logging and validation. Mention the Moody's pattern: PostgreSQL day-to-day, pandas for analytics, plotly for quick visual sanity checks before committing to a research narrative.

**4. How would you produce a data-driven research report for an external audience? What's different from an internal one?**
External work has to be defensible line by line - methodology box, data sources, limitations, reproducible figures. Reference the Moody's analytical summaries for client Heads of Risk and the Ortec investment-committee presentations: same discipline of pairing a strong narrative with an auditable data appendix.

**5. You don't have direct corporate-credit-rating experience. How will you get up to speed?**
Honest framing: CFA curriculum covered corporate credit analysis; Ortec and Moody's work covered fixed income, spreads and scenario analysis at the portfolio level; the gap is the rating-criteria specifics and the CIPF sector lenses. Plan: read Fitch's master criteria for two or three sectors in the first month, sit with coverage analysts, and use the data-engineering work as the bridge while the credit fluency builds.

## Questions Saber Should Ask

1. What does the current data stack look like end-to-end - which pieces are Oracle vs Mongo, where does Qlik Cloud sit, and where are the biggest gaps the team wants this hire to close in year one?
2. How do you decide which Enhanced Analytics products become external Fitch research vs. internal-only analyst tools? Who owns that call?
3. What does a successful first 12 months look like for this role - more shipped infrastructure, more research output, or more analyst adoption of the tools?

## Competency Gap to Prepare For

**Qlik Cloud and corporate-credit-rating domain depth.** The JD lists Qlik Cloud as a nice-to-have BI tool and assumes interest in corporate credit. Saber has Plotly/matplotlib and Excel/Python visualization experience plus CFA-level credit knowledge, but no production Qlik dashboards and no rating-agency experience. Prep: skim Qlik Cloud's developer docs to speak credibly about the data model and scripting layer; read two recent Fitch CIPF sector reports before the interview so corporate-credit vocabulary is fluent.