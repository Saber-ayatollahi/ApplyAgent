## 5 likely technical questions

**1. Walk us through how you would run an asset-liability study for a plan like OMERS.**
From Ortec experience: calibrate a stochastic economic scenario generator to the plan's assumptions (rates, inflation, equity, FX), project assets and liabilities jointly under those scenarios, decompose funded-ratio volatility by contribution-to-risk (rates, equity, currency, credit), then test duration extension, hedging overlays, and leverage strategies against the funding-policy dynamics. Led exactly this for a three-plan university pension merger on a team of three.

**2. How do you think about VaR vs CVaR for total-plan risk, and what are the failure modes?**
VaR is a quantile, CVaR is the expected loss in the tail beyond it. Used both at Ortec for asset-only and surplus optimization on the GLASS platform. CVaR is more informative for fat tails and pension surplus risk where downside dominates; VaR is simpler to communicate. Failure modes: estimation noise in the tail, regime shifts breaking calibration, and treating either as a hard constraint rather than one input. Always pair with stress and reverse-stress.

**3. You're asked to evaluate a tactical asset mix tilt. How do you frame it?**
Frame as marginal contribution to total-portfolio risk and to funded-status volatility, not just standalone return. Run the tilt through the existing scenario set, decompose its contribution-to-risk against the strategic mix, stress it under regime shocks (rates up + equity down, credit widening, liquidity stress), and check the funded-ratio CVaR delta. Then bring the trade-off — expected surplus return vs incremental tail risk — back to the investment team in their language.

**4. How do you stress-test liquidity for a plan with significant private and illiquid exposures?**
From the Moody's cash-flow engine work: project required outflows (benefits, capital calls, derivative margin) against expected inflows under base, stress, and reverse-stress, in time buckets from T+1 out to multi-year. Embed behavioral assumptions where relevant. The reverse-stress angle — what scenario breaks the liquidity plan — is usually more useful than parallel shock sizing.

**5. Tell us about a time your analysis changed a decision.**
Ortec LDI study (STAR Story 4): Canadian pension client questioned fixed-income duration positioning given a liability-duration extension. Built calibrated scenario generator, ran funded-ratio distributions, decomposed duration-gap contribution to funding-ratio volatility, presented explicit SAA recommendations to the investment committee. Committee adopted the duration extension; client returned for follow-on work.

## 3 questions Saber should ask

1. How does the Total Plan Risk team interact with the Total Portfolio Management investment teams day-to-day — is risk embedded in the construction process, or is it primarily an oversight/reporting function?
2. Where is the team on the build-out of the risk analytics program — what is in production today, what is on the 12-month roadmap, and where does this seat get to contribute most?
3. How does the team balance third-party systems (MSCI, Aladdin, Bloomberg) against internal Python-based tooling, and where is the investment going?

## 1 competency gap to prepare for

**No hands-on with MSCI RiskMetrics, BlackRock Aladdin, or Bloomberg risk tooling, and no Power BI experience.** Own this honestly: the methods (factor models, VaR/CVaR decomposition, scenario aggregation) are the same as Ortec GLASS and the Moody's platform; the tool fluency is a 2-4 week pickup, not a capability gap. Lead with Python + SQL fluency on large datasets and frame BI/dashboarding as where the seat will accelerate the existing toolkit.