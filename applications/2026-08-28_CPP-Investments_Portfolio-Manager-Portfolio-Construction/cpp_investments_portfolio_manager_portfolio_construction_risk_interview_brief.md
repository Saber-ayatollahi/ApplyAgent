## Likely technical questions (with model answers)

**1. "Walk me through how you'd assess whether a multi-strategy portfolio is genuinely diversified."**
At Ortec I ran asset-only and surplus optimization on VaR and CVaR in GLASS, then decomposed contribution-to-risk by strategy and factor rather than reading weights. The decisive test was near-optimal frontier analysis: I generated portfolios in the neighbourhood of the optimum to see whether the risk contributions and rankings were stable, or whether apparent diversification was an artifact of the correlation and return inputs.

**2. "How do you avoid over-fitting an optimizer to historical inputs?"**
Two defences. First, robustness testing — the near-optimal frontier work above, plus stress and sensitivity runs where I perturb correlation and return assumptions and see whether the recommendation survives. Second, forward-looking stochastic scenarios rather than historical windows: I built and calibrated economic scenario generators at Ortec to produce distributions of funding and portfolio outcomes under base and stressed regimes.

**3. "Give an example of challenging a number that looked fine."** (STAR Story 2)
A client delivery run produced portfolio sensitivities that passed every internal check but did not square with the client's economic intuition under a specific rate-shock scenario. I held the release, re-ran sensitivities decomposed by asset class, isolated a curve-calibration edge case in short-end inversion handling, and escalated to product owners and the client's Head of Risk. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**4. "Tell me about a complex, ambiguous mandate you led."** (STAR Story 4 / UPP)
The three-plan university pension merger: three single-employer plans combining into a new jointly-sponsored plan, with no precedent model. On a team of three I built and validated the model capturing all funding-policy dynamics and evaluated duration, currency, inflation and leverage overlay strategies. Separately, a Canadian pension client's duration-gap study I presented led their committee to adopt a duration extension.

**5. "How would you communicate a complex portfolio-risk view to an investment committee?"**
Lead with the decision, not the method: what changes, what it costs, and what breaks it. At Ortec I presented ALM and allocation findings on site to pension investment committees; at Moody's I prepare senior-stakeholder summaries translating exposures, scenario impacts and sensitivities into committee-ready narratives. The analytical appendix backs the one-page recommendation, never the reverse.

## Questions to ask

1. How does SRO arbitrate between a strategy's standalone risk-adjusted return and its marginal contribution at the One Fund level — is there an explicit capital-efficiency or diversification hurdle, or is it judgment-led per review cycle?
2. Where does the portfolio construction and risk framework feel least mature today — the analytics, the data plumbing across EPM and SSG, or the governance cadence that turns analysis into a decision?
3. What separates a strong first year in this seat from an outstanding one: depth on a few strategic reviews, or building a reusable analytical capability the department runs on afterwards?

## The one competency gap to prepare for

**Hedge fund strategy fluency and market-neutral alpha construction.** The repo shows multi-asset institutional and pension portfolios — long-horizon, liability-aware — not internally/externally managed hedge fund books, capital efficiency at the strategy level, or public-equity/commodity alpha sourcing. Do not claim it. Prepare an honest bridge: the analytical apparatus is identical (marginal contribution to risk, CVaR tails, correlation stability, capacity and scalability constraints, robustness of the optimizer), and read up on market-neutral construction, leverage and margin/capital efficiency, and manager-level exposure aggregation before the first round so the vocabulary is fluent even though the mandate type is new.