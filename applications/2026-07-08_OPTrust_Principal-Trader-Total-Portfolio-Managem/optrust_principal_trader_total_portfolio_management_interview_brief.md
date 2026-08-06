## Likely technical questions

**1. Walk us through how you would structure a liability hedging program for a mature pension plan.**
Start from the liability duration profile and key-rate breakdown, then map physical + synthetic (bond forwards, swaps, repo-financed bonds) hedge instruments against it. At Ortec I ran exactly this for Canadian pensions — including the UPP merger study — evaluating duration, currency, inflation, and leverage-overlay strategies against funded-ratio volatility. The trade-off you're solving is hedge ratio vs. return-seeking capital and liquidity headroom for margin/collateral calls in a rates sell-off.

**2. How do you think about generating alpha through rates and FX positioning in a total-portfolio context?**
Alpha at the TPM level has to be sized against its contribution-to-risk at the total-fund level, not standalone. My Ortec work included risk decomposition and contribution-to-risk analysis on VaR/CVaR-optimized portfolios — the same lens applies to a rates or FX active view: what's the risk budget, what's the marginal contribution, and does the position survive under stress and reverse-stress. I would express macro/rates/credit/currency views through the most liquid instrument that carries the exposure cleanly.

**3. Describe a derivatives pricing or risk issue you caught and escalated.**
(Story 2 in the STAR bank.) A client-delivery run produced portfolio sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate-shock scenario. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case at the short end, escalated to product and the client's Head of Risk, and drove the fix into validation tests. Result: 48-hour delay, client avoided acting on wrong numbers, and I became their direct escalation contact.

**4. How would you build an AI-enabled tool to support the trading desk?**
I've done this. At Moody's I built agentic workflows using Claude Code and Cursor for code generation, validation scaffolding, and anomaly detection — ~30-40% cycle-time reduction on comparable modules. For a trading desk I would start with the highest-frequency, lowest-judgment tasks: TCA and commission reporting, break/exception triage, market-data sanity checks, and drafting of pre-trade analytics. Human sign-off stays on execution and risk decisions; AI compresses the plumbing around them.

**5. You've never sat on a trading desk. Why should we believe you can execute?**
Honest framing: I've been on the analytics and portfolio-construction side of the same instruments the desk trades, and I've been the escalation point when those instruments' outputs looked wrong. Execution mechanics — order handling, sell-side relationships, TCA — I would learn on the desk, and I would learn them faster than a career trader would learn the ALM, LDI, and cross-asset risk-decomposition machinery I already carry. The Total Portfolio angle is where my edge is; the execution craft is what I'd absorb from the team.

## Questions Saber should ask

1. How is the alpha budget for the Funding, Liquidity and Trading desk sized within the Total Portfolio, and how has that sizing evolved as the Plan's liability profile has matured?
2. Where in the current TPM tech stack is the biggest gap that an AI-enabled tool could close first — pricing, TCA, portfolio construction, or risk aggregation?
3. How does the desk split responsibility between generating alpha and managing the liability hedging program under stress — is there a formal risk budget or is it collaborative call-by-call?

## The competency gap to prepare for

**Direct sell-side / trading-desk execution experience.** Saber's work has been portfolio-construction, ALM, and validation-side of these instruments — not order-handling, sell-side broker relationships, or live TCA ownership. Prepare a crisp version of Question 5 above, and be ready to name specific things he would want to learn from the desk in the first 90 days (execution venues, RFQ vs. voice for CAD govvies, repo funding mechanics for the leverage overlay).