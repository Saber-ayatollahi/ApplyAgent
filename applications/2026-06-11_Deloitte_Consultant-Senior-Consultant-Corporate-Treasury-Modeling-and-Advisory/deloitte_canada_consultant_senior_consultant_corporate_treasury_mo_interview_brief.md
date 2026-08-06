## Likely technical questions

**1. Walk me through how you would build or validate a structural interest rate risk model for a bank's banking book.**
I'd start from the balance-sheet segmentation (rate-sensitive vs. non-rate-sensitive, behavioural overlays for NMDs and prepayment), build the repricing gap and key-rate duration views, then run EVE and NII under parallel and non-parallel shocks. At Moody's I oversee exactly this analysis under IRRBB-style frameworks; validation is curve construction, spread calibration, behavioural assumption reasonableness, and economic defensibility of the resulting sensitivities.

**2. How do you approach liquidity stress testing and cash-flow projection for a treasury balance sheet?**
I led the design of an enterprise multi-asset cash-flow projection engine supporting base, stress, and reverse-stress scenarios at Moody's, with configurable time-bucketed liquidity gap analytics from T+1 through multi-year horizons. The hard part is the behavioural layer — prepayment logic, deposit run-off, draw-down assumptions — and ensuring the stress overlays are internally consistent rather than just additive shocks.

**3. Explain Fund Transfer Pricing and how you'd validate an FTP model.**
FTP allocates a cost or credit of funds to each business unit based on tenor, optionality, and liquidity characteristics, so the resulting NIM reflects true contribution. Validation is about the curve choice (matched-maturity vs. weighted average), treatment of behavioural products and contingent liquidity, and whether the framework produces the right incentives. My ALM and curve-calibration work at Moody's translates directly.

**4. Tell me about a model where the output passed every internal check but you still escalated.**
(Story 2.) At Moody's a client-delivery run produced sensitivities that passed internal checks but didn't square with the client's intuition under a specific rate-shock scenario. I held the release, decomposed sensitivities by asset class, identified a short-end curve-calibration edge case, escalated to product and the client's Head of Risk, and walked through the remediation. Release slipped 48 hours; defect was fixed upstream and added to the validation test set.

**5. How would you use Python or VBA to industrialise a spreadsheet-driven ALM workflow?**
(Story 6.) I migrated a spreadsheet-driven valuation workflow at Moody's into a Python pipeline by parallel-building it, running in shadow mode for two cycles, reconciling output, then cutting over with a rollback plan. The key controls are versioned inputs, logging at each transformation step, deterministic seeds for any stochastic component, and a documented reconciliation pack — which is what closes a governance audit.

## Questions Saber should ask

1. How is the Corporate Treasury Modeling team's engagement mix split today between model development, model validation, and strategic treasury advisory — and where is it heading over the next 12-18 months?
2. What's the typical client profile (Big Six, mid-tier banks, insurers, foreign-bank subsidiaries) and the most common modelling pain points you're being asked to solve — IRRBB methodology refresh, LST, FTP redesign, or something else?
3. How does this team partner with Deloitte's market risk, credit modelling, and AI/ML practices on cross-discipline engagements, and what does the career path from Senior Consultant to Manager look like inside Financial Engineering and Modeling?

## Competency gap to prepare for

**Fund Transfer Pricing depth.** My ALM, IRRBB, and liquidity-modelling experience is hands-on; FTP I understand methodologically (matched-maturity curves, behavioural overlays, contingent liquidity premium) but have not personally built an FTP framework end-to-end at a deposit-taking institution. I will refresh on standard FTP design choices (single-pool vs. multiple-pool, behaviouralised vs. contractual, liquidity premium add-ons) before any technical round, and frame my answer as 'methodology I can validate and develop, with build experience on the adjacent IRR and liquidity components rather than the FTP module itself.'