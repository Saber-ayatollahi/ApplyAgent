## Likely Technical Questions

**1. Walk me through how you'd measure IRRBB - EVE vs NII, parallel vs non-parallel shocks.**
EVE captures economic value sensitivity across the full term structure under instantaneous shocks (parallel up/down, steepener, flattener, short-rate up/down per Basel's six prescribed scenarios); NII captures earnings sensitivity over a 12-month horizon under repricing assumptions. At Moody's I run both under parallel and non-parallel shocks, reviewing curve construction and behavioral assumptions before sign-off. The interesting cases are usually non-parallel - a steepener can be benign for EVE but punishing for NII depending on repricing gap.

**2. How do you validate a derivatives pricing output you didn't build?**
Three-layer check: (i) reconcile inputs - curve, vols, fixings, day-counts; (ii) sanity-check sensitivities against analytical intuition (DV01 sign and magnitude vs notional/tenor, gamma behavior near ATM); (iii) scenario-test under known shocks to confirm economic defensibility. At Moody's I held a release on a portfolio where sensitivities passed internal checks but failed economic intuition under a short-end inversion - turned out to be a curve-calibration edge case.

**3. You haven't worked on a sell-side trading book. How does your ALM background translate to enterprise market risk reporting?**
The machinery is shared: VaR, Stressed VaR, and stress testing all rest on scenario design, P&L attribution, and sensitivity aggregation - which is exactly what I do for ALM and IRRBB. The vocabulary differs (trading-book FRTB SBM/IMA vs banking-book EVE/NII) but the analytical spine - shock the curves, revalue, aggregate, attribute - is the same. I'd expect a ramp on RBC-specific products and the proprietary execution framework, but the reporting and analytics work is in my wheelhouse from day one.

**4. Talk about a Python/SQL reporting pipeline you've built end-to-end.**
At Moody's I re-engineered a spreadsheet-driven valuation workflow into a Python pipeline: SQL-backed position store, pandas-based transformation layer, parameterized scenario runs, embedded validation checks and logging, output to a reviewable format. Ran it in shadow mode for two cycles, reconciled against the legacy spreadsheet, then cut over with rollback. Same pattern would apply to migrating locally-hosted Tableau reporting into RBC's proprietary execution framework.

**5. How do you communicate a complex risk finding to a senior stakeholder?**
Lead with the number and the decision it implies, then the driver, then the methodology caveats. At Moody's I escalate to client Heads of Risk on analytical issues - they want "what changed, why, and what should we do" in 90 seconds, not a methodology lecture. I keep a one-page summary template: position, key metric movement, attribution by driver, and recommended action or watchpoint.

## Questions Saber Should Ask

1. How is the BSLR-ALM team's reporting stream currently split between EUC (Excel/Tableau locally hosted) vs the proprietary execution framework, and what's the migration roadmap over the next 12-18 months?
2. Where does this role sit relative to MCCR (Market & Counterparty Credit Risk) and Treasury - who owns methodology vs production vs challenge, and where are the seams the Manager is expected to bridge?
3. What's the most recent IRRBB methodology change the team has pushed through (behavioral assumptions, NMD modelling, basis risk), and what drove it?

## Competency Gap to Prepare For

**Bloomberg / sell-side trading-book products in depth.** JD lists Bloomberg as a proficiency expectation and the broader market-risk machinery (Stressed VaR backtesting, repo desk mechanics, sell-side IR derivatives infrastructure) is adjacent to - not the same as - my buy-side/ALM background. Prep: refresh Bloomberg core functions (YAS, SWPM, FXFA), be ready to talk repo cashflow/discounting at first-principles level, and frame the gap honestly as "applied knowledge, ramping fast on RBC infrastructure" rather than overclaiming.