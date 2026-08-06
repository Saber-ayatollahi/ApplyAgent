## Likely technical questions

**1. Walk me through how you'd measure structural interest rate risk on a banking book, EVE vs NII.**
EVE captures the present-value impact of rate shocks on all banking-book cash flows and is the long-horizon economic view; NII captures the near-term earnings impact over a rolling 12-24 month window. Both need to be run under parallel and non-parallel scenarios (steepener, flattener, short-up, short-down). At Moody's I oversee exactly this dual view at portfolio-level aggregates, with curve construction and key-rate duration as the diagnostic layer underneath.

**2. How do you handle behavioral assumptions for non-maturity deposits and prepaying mortgages?**
Both are the heart of banking-book ALM: NMDs need a core/non-core split and a behavioral repricing profile calibrated to historical beta and decay; prepaying mortgages need a CPR model conditioned on rate incentive and seasoning. I embedded behavioral cash flow assumptions and prepayment logic directly into the projection engine at Moody's, and I'm comfortable that the assumption layer needs as much governance as the model layer.

**3. How would you think about hedging a duration gap with swaps vs balance-sheet repositioning?**
Derivative overlays (pay-fixed receive-float, or the reverse) give you fast, surgical duration adjustment without disturbing customer franchise, but introduce hedge-accounting complexity and counterparty exposure. Balance-sheet repositioning is slower but cleaner from a P&L and accounting standpoint. The right answer is usually a blend: overlay for the immediate gap, term-funding and asset mix for the structural gap. At Ortec I ran exactly this trade-off via leverage-overlay analysis on the UPP study.

**4. Tell me about a model output you held back from release.**
(STAR Story 2.) A client run produced sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, identified a curve-calibration edge case in short-end inversion handling, and escalated to the PO and the client's Head of Risk. Release slipped 48 hours; the defect was remediated upstream and added to validation tests.

**5. How do you present an IRRBB result to a non-technical ALCO audience?**
Lead with the answer (the EVE / NII number against limit), then the two or three drivers, then the scenario in which the answer changes. Always show what's *not* in the number (assumption sensitivity, model uncertainty). I prepare this kind of synthesis for senior Moody's stakeholders and presented at Ortec to pension investment committees -- the principle is the same: respect the audience's time and give them what they need to decide.

## Questions Saber should ask

1. How is the BSM team's analytical work currently split between in-house tooling (QRM, internal models) and vendor platforms, and where would this seat be expected to push the framework next?
2. What's the current state of behavioral-assumption governance for non-maturity deposits and prepayment -- is there an annual recalibration cycle, and who owns challenge?
3. How does the team interact with the GRM IRRBB validation function, and what does a healthy modeller-validator relationship look like in your view?

## Competency gap to prepare for

**QRM hands-on, hedge accounting under IFRS 9, and bank-specific NMD / prepayment calibration.** Saber has not used QRM directly and hasn't booked hedge-accounting designations himself. Frame as: deep IRRBB and cash-flow-engine experience on an analogous platform (Moody's), IFRS 9 transformation exposure from EY, and a fast learning curve on QRM specifics. Don't claim QRM in the resume; own it as the obvious first thing to ramp on if asked.