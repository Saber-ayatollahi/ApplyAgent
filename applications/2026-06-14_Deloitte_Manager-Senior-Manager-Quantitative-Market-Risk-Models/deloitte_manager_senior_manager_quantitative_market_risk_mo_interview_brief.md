## Likely Technical Questions

**1. Walk us through how you would validate a Monte Carlo pricer for a Bermudan swaption.**
Draw on Story 2 (escalated economically-wrong output). Cover: convergence diagnostics (standard error vs paths), variance reduction (antithetic, control variates), short-rate model choice (Hull-White vs LMM) and calibration to co-terminal swaptions, regression basis for early-exercise (Longstaff-Schwartz), and sensitivities reconciled vs analytic limits where available. Emphasize the governance step: economic-defensibility check vs trader intuition before sign-off.

**2. How do you calibrate a yield curve and what pitfalls do you watch for?**
Multi-curve OIS-discounting framework: build discount and projection curves separately from cash/FRAs/swaps, bootstrap or global optimization with smooth interpolation (monotone-convex or tension splines). Pitfalls: short-end inversion handling (the actual edge case from Story 2), turn-of-year jumps, basis spreads. Stress-test calibration stability via curve bumps and refits.

**3. What's the difference between VaR and Expected Shortfall, and why did FRTB move to ES?**
VaR is a quantile; ES is the conditional expectation in the tail. ES is sub-additive (coherent), captures tail-shape beyond the quantile, and is less manipulable. FRTB's IMA uses ES at 97.5% with liquidity-horizon scaling and NMRF treatment. Tie to Ortec work: I ran VaR and CVaR portfolio optimization in GLASS and saw firsthand how CVaR drives different allocations under fat-tailed regimes.

**4. Tell us about a model validation finding that mattered.**
Use Story 2 verbatim: portfolio sensitivities passed every internal check but didn't square with client economic intuition under a specific rate-shock; held the release, decomposed by asset class, found a curve-calibration edge case (short-end inversion handling), escalated to PO and client's Head of Risk, 48-hour delay, defect remediated upstream and captured in validation tests, became their direct escalation contact.

**5. How would you approach validating an internal VaR or FRTB-style market-risk model you've never seen before?**
Frame: conceptual soundness (model choice, assumptions, theory), implementation testing (replicate on subset, unit tests, benchmark vs alternative), outcomes analysis (backtesting, P&L attribution, hypothetical vs actual), ongoing monitoring (trigger thresholds), and documentation against SR 11-7 / OSFI E-23. Be honest: I have applied this framework to ALM and derivatives outputs at Moody's; FRTB IMA backtesting specifically is adjacent territory I would scale into quickly.

## Questions Saber Should Ask

1. How is the Financial Engineering and Modeling group's work split today between bank-side model development engagements and validation/vetting mandates — and where is the growth?
2. What does the Manager vs Senior Manager distinction look like in practice on a typical Capital Markets engagement — book of business, team leverage, and client-facing scope?
3. Which of FRTB IMA, CCR/SA-CCR, xVA, or CCAR is the heaviest demand area from your Big-6 clients in the next 12-18 months, and how is the group staffing into it?

## Competency Gap to Prepare

**Counterparty Credit Risk (CCR/xVA) and FRTB delivery experience.** The JD names CCR, xVAs, FRTB, and CCAR. Saber has rates/FX/inflation derivatives validation, VaR/CVaR portfolio analytics, and stochastic scenario engines — strong transferable foundation — but no production FRTB IMA, SA-CCR/IMM, or CVA-desk delivery. Prep: read Gregory's xVA chapter on CVA/FVA/KVA mechanics, refresh FRTB IMA structure (ES, liquidity horizons, NMRF, DRC, P&L attribution test), and have a clear honest framing ready: 'adjacent applied knowledge from derivatives validation and Basel-style market-risk work — I can scale into FRTB/CCR delivery quickly because the underlying math (stochastic simulation, Monte Carlo, sensitivity validation, model governance) is what I do daily.'