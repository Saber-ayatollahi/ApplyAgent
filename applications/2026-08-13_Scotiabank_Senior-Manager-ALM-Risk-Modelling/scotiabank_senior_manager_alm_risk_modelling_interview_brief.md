# Interview Brief — Scotiabank, Senior Manager, ALM Risk Modelling

## 5 most likely technical questions

**1. "Walk us through how you'd model a balance sheet position start to finish."**
Use the cash flow projection engine (STAR Story 1): the prior state was spreadsheet-driven and unauditable, so I specified the contractual cash flow spine first, layered behavioural assumptions (prepayment, macro overlays) on top, made the time bucketing configurable T+1 to multi-year, then rebuilt the upstream workflow as a Python pipeline with logging so every run is reproducible. Close on how I test: shadow-run against the incumbent, reconcile, then cut over with a rollback plan (Story 6).

**2. "How would you approach a mortgage prepayment or deposit behaviour model?"**
Be explicit that my hands-on behavioural work is prepayment logic and macro overlays inside a projection engine, not retail deposit econometrics on bank customer data. Then reason it through: rate incentive (contract vs. market), seasoning, seasonality, and borrower/segment controls as covariates; a hazard or logistic specification estimated on historical loan-level data; out-of-sample and out-of-time testing; sensitivity of EVE/NII to the elasticity parameter so business partners can see what the assumption is worth.

**3. "Explain parallel vs. non-parallel shocks and why they give different answers."**
A parallel shift moves duration exposure; non-parallel shocks (steepener, flattener, short-up/long-down) expose repricing mismatch and key-rate duration concentration that a parallel shock nets out. I run both at Moody's on multi-asset institutional balance sheets, and my sign-off covers whether the curve construction and short-end handling behave sensibly under those shocks — one real defect I caught was a short-end inversion edge case in calibration (Story 2).

**4. "Tell us about a model output you refused to sign off."**
STAR Story 2: sensitivities passed every internal check but contradicted the client's economic intuition under one rate shock. I held the release, decomposed the sensitivities by asset class, isolated a curve-calibration edge case in short-end inversion handling, escalated to Product and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the defect was fixed upstream and captured in the validation test suite.

**5. "What does a software engineering mindset mean in a modelling team?"**
Version control, tests before refactors, no logic living in a workbook cell, and documentation generated alongside the code. Concretely: I migrated a spreadsheet valuation workflow into Python (pandas/NumPy/SciPy) with embedded logging and validation, run it under Git/CI, and built agentic review workflows in Claude Code and Cursor for first-pass code review and validation scaffolding — ~30-40% cycle-time reduction on comparable modules, with a human still signing off on governance-critical review.

## 3 sharp questions to ask
1. How do the team's model choices land in FTP and the Bank's rate positioning — is the modelling team in the room when the transfer-pricing curve treatment of behavioural balances is set, or is that handed downstream?
2. What does the current behavioural model inventory look like (prepayment, non-maturity deposits, options/pipeline), and what's the recalibration and backtesting cadence for each?
3. Where is the line between this team's development work and Model Risk Management's independent validation — and how much of the Senior Manager's time is model build versus challenge-response and stakeholder defence?

## The one competency gap to prepare for
**Retail deposit behaviour econometrics on bank customer data, plus FTP mechanics.** My behavioural work is prepayment logic and macro overlays inside institutional ALM projection engines, and my liability depth is actuarial/pension, not core-deposit attrition and repricing beta estimated on a Big-6 retail book; I have never owned an FTP curve. Prepared framing: I have built and calibrated stochastic models from data, own the statistical toolkit (hazard/regression, Monte Carlo, Python), and have signed off on the outputs that feed EVE/NII — the deposit-specific dataset and FTP plumbing are learnable in weeks, not the modelling judgment. Do not claim deposit-model or FTP ownership.