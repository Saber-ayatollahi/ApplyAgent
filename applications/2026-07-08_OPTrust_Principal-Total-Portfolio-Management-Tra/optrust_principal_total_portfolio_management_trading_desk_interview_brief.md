## Likely technical questions

**1. Walk us through how you would size a liability hedge for a pension plan given a parallel rate move plus a curve steepening.**
> At Ortec I ran exactly this decomposition for pension clients: separate the duration-gap contribution to funded-ratio volatility from the key-rate contribution, price the swap/bond overlay that closes the gap in the sensitive tenors, then stress-test residual convexity and basis risk under stochastic scenarios. The trade-off is always cost of carry versus funded-status stability - I would frame the recommendation against the plan's SAA and liquidity budget.

**2. How do you validate a derivatives pricing output you don't trust?**
> STAR Story #2 - at Moody's, I held a client release when portfolio-level sensitivities passed internal checks but didn't square with the client's economic intuition under a specific shock. Decomposed by asset class, isolated a short-end inversion edge case in curve calibration, escalated to product and the client's Head of Risk. Delay was 48 hours; client avoided acting on wrong numbers; became their direct escalation contact after that.

**3. Tell us about a stochastic scenario generator you built or used - what were the calibration choices?**
> At Ortec I built and interpreted ESGs for pension ALM studies. Key choices: real-world vs risk-neutral calibration (real-world for funded-status projection, risk-neutral for hedge pricing), mean-reversion parameters on rates, credit-spread regime dependence, and FX/inflation cross-correlations. Validation was through moment matching against historical distributions and sanity checks on tail behavior at the 1-in-20 and 1-in-100 percentiles.

**4. How would you use VaR and CVaR in a total-portfolio construction context, and what are their limitations?**
> At Ortec I ran surplus optimization on both metrics using GLASS. VaR gives a threshold, CVaR gives the expected loss beyond it - CVaR is coherent and subadditive, so I prefer it for cross-asset aggregation. Limitations: both are backward-looking in calibration; both under-represent regime shifts. I supplement with near-optimal frontier analysis and reverse-stress testing to check that allocations aren't fragile to small parameter changes.

**5. Give me an example of an AI-enabled tool you have actually shipped, not just experimented with.**
> STAR Story #7 - I built agentic review workflows using Claude Code and Cursor IDE that do first-pass code review, generate validation scaffolding, and draft documentation on our Python analytics pipelines. Human still signs off on governance-critical review. Cycle time on comparable validation modules dropped 30-40%. The design principle was that the LLM handles pattern-matching work and I keep the judgment calls - matches the JD's AI-enabled tools ask.

## Questions to ask them

1. How does the Funding, Liquidity and Trading desk allocate risk budget between the alpha-generation mandate and the liability-hedging book - is there an explicit tracking-error frame, or is it managed at the total-portfolio level?
2. Where do you see the biggest headroom for AI-enabled tooling on the desk right now - pricing, TCA/execution analytics, or portfolio-construction workflows?
3. What does the collaboration model look like between this desk and the internal risk, middle office, and external-manager oversight teams during a fast-moving macro event?

## The one competency gap to prepare for

**Sell-side execution / trade-lifecycle experience.** My background is buy-side analytics and model governance, not desk-side execution. I have priced, validated, and constructed hedges; I have not sat on a trade blotter placing derivative trades with sell-side counterparties. Prepare an honest framing: strong on pricing, risk, portfolio construction, and post-trade analytics; will need to build execution-workflow and sell-side-relationship muscle in the first 6-12 months. Reinforce with the UPP overlay work at Ortec (leverage, currency, inflation overlays sized to Funding Policy) as the closest adjacency.