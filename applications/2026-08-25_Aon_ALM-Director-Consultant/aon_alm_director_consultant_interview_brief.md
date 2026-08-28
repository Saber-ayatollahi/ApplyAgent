## Likely technical questions

**1. Walk me through how you would build a stochastic ALM projection for a life balance sheet.**
Use Story 1: the Moody's cash flow projection engine — configurable time buckets (T+1 through multi-year), base/stress/reverse-stress scenarios, behavioural cash flow and prepayment assumptions, macro stress overlays, all on auditable Python pipelines. Add the Ortec side: economic scenario generators calibrated to client assumptions, funding-ratio distributions under base and stressed regimes. Be explicit that the liability side of my direct build experience is pension-actuarial, and that the asset/reinvestment and projection machinery ports directly.

**2. How do you set an SAA when the objective is matching liabilities rather than maximising return?**
Story 4: for a pension client questioning duration positioning against a liability-duration extension, I decomposed duration-gap contribution to funding-ratio volatility across stochastic scenarios, then ran surplus (asset-liability) optimization on VaR and CVaR in GLASS and tested near-optimal portfolios around the frontier for robustness. The committee adopted the duration extension. The framing point: optimise the surplus distribution, not the asset distribution, and test that the answer is not knife-edge.

**3. What risk metrics do you rely on for interest rate risk, and where do they break?**
Duration and key-rate duration under parallel and non-parallel shocks, plus full-revaluation scenario runs for convexity and optionality. Where they break: short-end curve inversion and embedded optionality — Story 2, where portfolio sensitivities passed every internal check but failed economic intuition under a specific shock; I decomposed by asset class, found a curve-calibration edge case in short-end handling, held the release 48 hours, and pushed the fix upstream into validation tests.

**4. You'd be onboarding companies onto PathWise. How do you handle a migration where the client's process is the problem?**
Story 3: during the Calypso-to-PFaroe migration, a pension client's ALM configuration requirements were being lost between their investment desk and our development team. I scoped requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated dev constraints back into investment language. Client onboarded on schedule and the configuration pattern was reused across the migration cohort — that reuse is how you make onboarding scale.

**5. How do you make a model production-grade and governable?**
Story 6: a spreadsheet-driven valuation workflow with no logging or versioning would not survive audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled output line by line, then cut over with a rollback plan. Governance audit closed and the pipeline became the template for adjacent workflows. I also sit on the model governance committee covering methodology review, documentation, and benchmarking standards.

## Questions to ask

1. For companies moving onto PathWise, where does the integration usually stall — the liability model conversion, the asset/reinvestment logic, or the reporting-basis reconciliation? Which one would this role own?
2. How is the offshore development team structured today, and what does the Director's supervision of it actually look like day to day — technical review, delivery ownership, or line management?
3. How much of the SAA and optimal-asset-solver roadmap is client-driven versus product-led, and where do you want the next capability increment (economic capital constraints, hedging integration, liquidity measures)?

## The gap to prepare for

**Bermuda BMA framework (BSCR, EBS, economic balance sheet) and participating / index-linked product valuation and capital.** This is a genuine hole — I have not worked a Bermuda reporting cycle, and my liability modelling is pension-actuarial plus IFRS 17/IFRS 9 transformation at EY, not par/IL product valuation. Prepare a 90-second honest answer: name what I know (economic-balance-sheet logic, discount-curve and scenario mechanics, capital measures as constrained optimisation inputs), name what I would learn, and cite IFRS 17 at EY as the proof point that I absorb a new reporting basis fast. Do a 2-3 hour read on BSCR structure, EBS technical provisions and the scenario-based approach, and on par/IL guarantee mechanics before the first round — enough to hold a conversation, never enough to claim it.