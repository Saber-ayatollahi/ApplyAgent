## 5 Most Likely Technical Questions

**1. Walk us through how you'd validate a vanilla interest-rate swap pricer.**
Start with curve construction (instruments, bootstrap vs. global fit, OIS-discounting vs. projection curves), then move to cash-flow generation, day-count and business-day conventions, and finally sensitivity checks (DV01, key-rate durations) against an independent re-build. At Moody's I do exactly this for client portfolios - reviewing curve construction, spread calibration, and cross-asset interactions before sign-off, and escalating outputs that are mathematically defensible but economically unsupported.

**2. How would you build a Monte Carlo VaR/ES engine for a multi-asset portfolio?**
Start with the risk-factor universe (rates, FX, inflation, equity, credit), choose a model family (historical-simulation vs. parametric vs. full-revaluation MC), calibrate the joint distribution (covariance, copulas, fat tails), draw scenarios, full-reval the book, and compute VaR/ES at the chosen horizon and confidence. At Ortec I built stochastic economic scenario generators and ran VaR/CVaR optimization on GLASS - including risk decomposition and contribution-to-risk attribution.

**3. What's the trade-off between binomial trees, PDE solvers, and Monte Carlo for derivatives pricing?**
Trees are intuitive and handle American exercise cleanly but scale poorly in dimensionality. PDE solvers (explicit / implicit / Crank-Nicolson) are efficient for 1-2 factor models with early exercise but get hard beyond ~3 factors. Monte Carlo handles high-dimensional and path-dependent payoffs well but is slow for early-exercise (needs LSM) and has discretization bias for SDEs. My Chem Eng MSc gave me the PDE/numerical-methods foundation, and I use MC daily at Moody's for scenario engines.

**4. How do you escalate a model output that 'looks wrong' to a client Head of Risk?**
Real example: a client-delivery run produced sensitivities that passed every internal check but didn't square with the client's economic intuition under a specific rate-shock. I held the release, re-ran sensitivities decomposed by asset class, isolated a curve-calibration edge case (short-end inversion handling), escalated to the product owner and the client's Head of Risk with a remediation plan, and built the case into the validation test suite. The release slipped 48 hours; the client avoided acting on wrong numbers; I became their direct escalation contact.

**5. You haven't worked on a sell-side trading desk. How do you bridge into FRTB / CCR / xVA model work here?**
Honest answer: my hands-on depth is in the valuation, sensitivity, and scenario layer that underlies all of those - derivatives pricing validation, Monte Carlo scenario generation, VaR/CVaR, curve construction. I have applied knowledge of FRTB sensitivities-based and IMA structures, and of CCR/PFE mechanics, but I haven't shipped a desk implementation. I'd ramp into the trading-book capital machinery quickly via Deloitte's existing engagements and team mentorship, and I'd be honest with clients about that arc on day one.

## 3 Sharp Questions for Saber to Ask

1. "How is the Financial Engineering and Modeling group split between model development for clients vs. independent validation/vetting mandates, and where would this hire weight on that spectrum?"
2. "What share of the book is FRTB / CCAR-style stress vs. CDOR/CORRA transition vs. xVA pricing right now, and where is the growth concentrated over the next 18 months?"
3. "How does the Manager vs. Senior Manager decision get made for candidates with a strong quant/model-governance background but adjacent (not direct) sell-side experience?"

## 1 Competency Gap to Prepare For

**Direct sell-side trading-desk experience with FRTB (SBA + IMA), CCR/PFE/xVA model build, and US CCAR submissions.** Saber has applied knowledge and adjacent depth (valuation, sensitivity, scenario engines, governance) but has not personally shipped these on a dealer desk. Prepare a tight 60-second 'how I'd ramp' answer: lean on the Chem Eng PDE / numerical-methods foundation, the Moody's derivatives-validation seat, and a clear willingness to pair with senior team members on first engagements. Do NOT overclaim on the resume - own the gap verbally and pivot to the quantitative and governance strengths that ARE in the repo.