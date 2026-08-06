## Likely Technical Questions

**1. Walk us through how you would size and measure investment risk for an illiquid, long-duration infrastructure portfolio.**
Frame it as a three-layer measurement stack: (i) bottom-up sensitivity and exposure analytics — duration, key-rate, FX, inflation — same toolkit I apply on multi-asset portfolios at Moody's; (ii) portfolio-level VaR/CVaR with explicit acknowledgement that historical-simulation VaR breaks down on illiquid assets, so the workhorse is stochastic scenario generation calibrated to long-horizon macro factors, the approach I used on pension ALM studies at Ortec; (iii) decomposition and attribution so risk is allocated to drivers (rates, inflation, sector, single-name) leadership can actually act on.

**2. How do VaR and CVaR differ, and why does that matter for an institutional portfolio?**
VaR is a quantile of the loss distribution; CVaR is the expected loss conditional on breaching it — coherent, subadditive, and far more honest about tail behavior. At Ortec I ran both asset-only and asset-liability (surplus) optimization on VaR and CVaR via GLASS; CVaR is the metric I anchor on when the loss distribution is fat-tailed or asymmetric, which is the norm for illiquid and infrastructure exposures.

**3. Tell us about a model output you held back because it didn't make economic sense.**
[STAR Story 2] A client delivery passed every internal mathematical check but produced sensitivities that didn't square with the client's intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, identified a short-end curve-calibration edge case, escalated to the product owner and the client's Head of Risk, and remediated upstream with a new validation test. The 48-hour delay protected the client from acting on wrong numbers and made me their direct escalation contact thereafter.

**4. How do you design a meaningful stress test for a portfolio with infrequent market data?**
Start from the risk factors, not the assets. At Ortec the scenario generators were calibrated on macro factors — rates, inflation, growth, FX, credit spreads — and exposures were mapped to those factors. That structure lets you apply coherent base, stress, and reverse-stress scenarios even when an individual asset has no observable mark. At Moody's I built the same logic into the multi-asset cash-flow projection engine, with macro overlays and behavioral assumptions embedded directly.

**5. Walk us through risk decomposition and risk budgeting — when is each useful?**
Decomposition tells you where risk is currently sitting (contribution-to-risk by asset, factor, or sleeve); risk budgeting tells you where you've decided it should sit. At Ortec I used both to test the robustness of SAA recommendations — near-optimal portfolios around the efficient frontier — and to advise investment committees on whether observed risk concentrations were intentional or drift. For CIB's book the same logic surfaces hidden inflation, rate, and sector concentrations across infrastructure sleeves.

## Questions to Ask

1. How is investment risk currently governed alongside credit risk at CIB — is there a single risk committee, or distinct lanes, and where does this role sit relative to investment decision-making?
2. What does the current measurement stack look like — VaR/CVaR, scenario engine, factor model — and where does leadership see the biggest measurement gap on long-duration illiquid exposures?
3. How does the team currently handle illiquidity and sparse-mark issues in portfolio-level analytics, and what would success in the first 12 months of this role look like?

## Competency Gap to Prepare For

**Direct infrastructure-asset experience.** My institutional-risk toolkit is transferable, but the asset-class knowledge — concession structures, availability payments, regulated-utility cash-flow mechanics, project-finance covenants — is something I will be ramping on. Own it directly: the analytics are the same discipline I have applied for seven years; the asset-class learning curve is the part I am most motivated to climb and is a six-month ramp, not a multi-year one. Avoid claiming infrastructure-deal exposure I don't have.