## Likely technical questions

**1. "How do you construct a stress scenario for a fixed income portfolio, and where does it add value over VaR?"**
VaR/CVaR gives a distributional view — at Ortec I optimized asset-only and surplus portfolios directly on VaR and CVaR and decomposed contribution-to-risk to find the drivers. Stress scenarios answer the question VaR can't: what a specific, coherent rate/FX/spread path does to the book. At Moody's I build base, stress, and reverse-stress paths into the cash-flow projection engine, with parallel and non-parallel shocks plus macro overlays, so the scenario is economically narratable to a committee rather than just a percentile.

**2. "Tell me about a time you challenged a portfolio manager or a modelling result."** (STAR Story 2)
A client delivery produced portfolio sensitivities that passed every internal check but didn't square with economic intuition under one rate-shock scenario. I held the release under deadline pressure, re-ran sensitivities decomposed by asset class, and traced it to a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours; the client avoided acting on wrong numbers, the defect was fixed upstream and captured in validation tests, and I became that Head of Risk's direct escalation contact.

**3. "How do you validate a derivatives pricing and sensitivity output?"**
Start at the inputs — curve construction and spread calibration — then check that sensitivities are internally consistent across rates, FX, and inflation and that they aggregate coherently from security level to portfolio level. I look for sign and magnitude consistency across shock sizes, cross-asset interaction behaviour, and whether the scenario response is monotone where theory says it should be. Anything that survives the math but fails economic defensibility gets escalated, not signed.

**4. "A market risk model methodology change is proposed. How do you assess impact?"** (STAR Story 6)
Parallel-run discipline. When migrating a governed valuation workflow from spreadsheets to Python, I shadow-ran the new pipeline for two full cycles, reconciled output line by line, documented drivers of every difference, and cut over with a rollback plan. Same approach applies to a methodology change: quantify the delta on representative portfolios and tail scenarios, attribute it to specific assumption changes, and take the benchmarking and documentation package to the governance committee.

**5. "How do you turn macroeconomic views into portfolio and financial projections?"** (STAR Story 4)
At Ortec I built and calibrated stochastic economic scenario generators to client assumptions, ran funding-ratio and balance-sheet distributions under base and stressed regimes, then decomposed how much of the volatility came from duration gap versus other exposures. For one pension client that analysis produced an explicit duration-extension recommendation the investment committee adopted. The discipline is the same for a treasury investment book: a macro theme is only useful once it is a calibrated scenario with attributable P&L and sensitivity impact.

## Questions Saber should ask

1. How is coverage divided between the CIO securities portfolio and the broader Treasury balance sheet, and where does this VP sit in the pre-trade review and limit-setting sequence?
2. When a market risk model or methodology change is proposed, how do the coverage team, quantitative research, and model review split ownership of the impact assessment — and what does the approval path look like?
3. Which parts of the daily risk workflow are still manual today, and how much appetite is there for rebuilding them (Python/tooling) versus running them as-is?

## The one competency gap to prepare for

**Sell-side daily market risk production: Bloomberg, limit frameworks, and securitized products.** Saber has not run a daily VaR/limit-monitoring cycle on a bank trading or investment book, has not used Bloomberg professionally, and his securitized-product exposure is behavioral cash-flow and prepayment modelling — not ABS/MBS relative-value analytics. Prepared framing: "I have been the independent review and challenge layer on the analytics that feed those processes, at $5-25bn portfolio scale, and I have built the engines that produce them. Bloomberg and your internal risk systems are tooling I will be productive on inside weeks; the judgement about whether a number is economically defensible is what took seven years." Do not claim Bloomberg, FRTB, or CCAR hands-on experience.