## Likely technical questions

**1. Walk us through how you review a fixed-income valuation and its risk sensitivities before sign-off.**
Start with curve construction (inputs, bootstrapping, interpolation choices) and spread calibration, then check price against independent benchmarks. On sensitivities, decompose DV01 / key-rate durations by tenor and cross-check convexity; validate that scenario shifts (parallel and non-parallel) produce economically defensible P&L. If numbers pass math but fail intuition, hold the release — as I did on a client run where a short-end inversion in the curve produced misleading portfolio sensitivities; escalated, remediated upstream, and captured in validation tests.

**2. How do you think about interest-rate risk measurement in an institutional context?**
Two complementary lenses: earnings-at-risk / cash-flow sensitivity, and economic-value sensitivity from duration and convexity. Apply parallel and non-parallel shocks (steepener, flattener, short-end shocks) aligned with Basel Committee IRRBB principles, decompose by product and repricing bucket, and pair with behavioral assumptions (prepayment, non-maturity behavior). At Moody's I run this across multi-asset client portfolios; at Ortec I did the pension-liability version — same math, different balance sheet.

**3. How do you approach liquidity risk and stress testing?**
Build time-bucketed cash-flow projections (T+1 to multi-year), layer base / stress / reverse-stress scenarios, and embed behavioral assumptions and macro overlays. I led the design of the enterprise engine that does this at Moody's — the point is forward-looking liquidity visibility and refinancing-risk assessment, not just a static ladder. Reverse stress in particular forces you to identify the scenario that breaks the book, which is where second-line challenge earns its keep.

**4. Give an example of independent challenge you provided that changed an outcome.**
On a client run at Moody's, sensitivities passed internal checks but didn't square with the client's economic intuition under a specific rate shock. Held the release, decomposed by asset class, identified a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk, and walked through remediation. Release delayed 48 hours; client avoided acting on wrong numbers; defect captured in validation tests.

**5. How would you frame market and credit risk exposures to a non-technical senior stakeholder?**
Lead with the risk-appetite question — where are we versus limits, and what's the trajectory. Then two or three drivers of change (rate move, spread widening, concentration). Then one recommended mitigation with cost/benefit. Avoid Greeks unless asked. My Ortec investment-committee work and my current Moody's client Heads-of-Risk audience have trained this muscle — translate the quant into a decision.

## Questions Saber should ask

1. How is the second-line Credit and Market Risk team currently organized between market, credit, and liquidity coverage, and where does this role sit in that split?
2. What are the most active challenge topics with the first line right now — is it methodology, limits, new products, or reporting?
3. How mature is the risk analytics tooling — is the near-term priority framework build-out, or deepening review depth on existing analytics?

## Competency gap to prepare for

CIBC Mellon is asset-servicing infrastructure — expect probing on custody/asset-servicing balance-sheet mechanics (securities lending exposures, cash reinvestment, FX settlement risk) which is adjacent to but not identical to my institutional-investor client experience. Prepare by reading CIBC Mellon's public disclosures and BNY / State Street analogs; frame my experience as transferable market-risk review on comparable instruments, and ask early in interview how their book differs so I can map my answers to their specific exposures rather than generic ALM.