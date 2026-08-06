## Likely Technical Questions

**1. Walk us through how you would evaluate a new external investment manager for one of our DB pension mandates.**
Start with the mandate's role vs. liabilities - duration contribution, expected return, diversification vs. existing managers. Then evaluate the manager on strategy coherence, risk-adjusted performance vs. an appropriate benchmark, style drift indicators, and operational/ESG factors. At Ortec I did exactly this exercise for pension clients across public and private mandates, benchmarking candidates against liability objectives rather than absolute return alone (STAR: LDI study that shifted a pension fund's SAA).

**2. How do you think about liability hedging and derivative overlays for a defined benefit plan?**
Start with liability duration and key-rate exposure, decide the hedge ratio in light of funded status and risk appetite, then choose the instrument mix (physical bonds vs. swaps vs. futures) based on capital efficiency and collateral considerations. For the UPP three-plan merger I modelled duration, currency, inflation, and leverage overlays alongside the funding policy - and today at Moody's I validate the derivative sensitivities that feed those hedging portfolios.

**3. Explain VaR vs. CVaR and how you have used them in portfolio construction.**
VaR is the quantile loss threshold; CVaR (Expected Shortfall) is the average loss conditional on breaching it - CVaR is coherent and captures tail severity, which matters for pensions. At Ortec I ran both asset-only and asset-liability (surplus) portfolio optimization on VaR and CVaR via GLASS, then used risk decomposition and near-optimal frontier analysis to test whether allocation recommendations were robust to small parameter changes.

**4. How do you integrate ESG into manager assessment and portfolio monitoring?**
ESG works best when integrated into the underwriting - assessing whether the manager's process actually incorporates material ESG factors, then monitoring for consistency post-hire rather than treating it as a separate scoring exercise. My EY IFRS 17 work sat next to insurers' responsible-investing reporting builds, and at Moody's I contribute to sustainability-aware analytics feeding client reporting.

**5. A monitoring run shows a manager underperforming their benchmark by 200bps over 12 months. Walk through your diagnostic.**
First decompose - is it factor exposure (duration, credit, style), security selection, or trading costs? Then contextualize against the strategy's expected drawdown pattern and peer group. Finally check for style drift by comparing current holdings to the mandate. Only after that decomposition would I recommend action. My Moody's escalation experience (STAR: mathematically defensible but economically wrong) taught me to always decompose before concluding.

## Questions Saber Should Ask

1. How is the pension investment team structured between DB and DC oversight, and where would this role's time weight land across manager selection, monitoring, and hedging?
2. What does the current liability hedging portfolio look like, and where is the team focused on evolving it - hedge ratio, instrument mix, or overlay strategy?
3. How does the team balance in-house analytics vs. consultant input, and how much of the tooling stack is Python/Power BI vs. Excel today?

## Competency Gap to Prepare For

**Power BI and DC / participant-capital-accumulation options.** Saber has advanced Excel and Python but has not shipped Power BI dashboards, and his pension work has been predominantly DB (Ortec, UPP). Prepare a one-minute answer: acknowledge Power BI as a near-term ramp from his SQL/Python foundation (he has picked up analytics tools quickly before), and lean into transferable frame on the DC side - participant-outcome analytics is stochastic projection with a different objective function, which is home turf from Ortec.