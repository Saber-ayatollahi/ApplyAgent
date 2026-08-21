## 5 likely technical questions

**1. Walk me through a portfolio optimization you ran end-to-end. Why CVaR over VaR?**
At Ortec I ran asset-only and asset-liability (surplus) optimizations on the GLASS platform using both VaR and CVaR objectives. CVaR was preferred where the client cared about the shape of the left tail rather than a single quantile — it is coherent, sub-additive, and far better behaved when the underlying scenario set is fat-tailed from a stochastic ESG. I then ran risk decomposition and contribution-to-risk budgeting and explored near-optimal portfolios around the frontier, because the point is not the single optimal point but how much the allocation can drift before the recommendation breaks.

**2. How do you validate a scenario generator before its output drives an allocation decision?** (STAR 4)
For a Canadian pension client questioning its fixed-income duration positioning, I calibrated a stochastic economic scenario generator to their assumptions, then checked it three ways: reproduction of target moments and term-structure dynamics, funding-ratio distributions under base and stressed regimes, and decomposition of the duration gap's contribution to funding-ratio volatility. The committee adopted a duration-extension recommendation. Validation is about economic defensibility, not just passing statistical tests.

**3. Tell me about a model result that looked right but wasn't.** (STAR 2)
A client delivery produced portfolio-level sensitivities that passed every internal check but did not square with economic intuition under one rate-shock scenario. I held the release, decomposed the sensitivities by asset class, and traced it to a curve-calibration edge case in short-end inversion handling. I escalated to the product owners and the client's Head of Risk. Release slipped 48 hours; the defect was fixed upstream and captured in a regression test.

**4. How do you take a research prototype into tested production code?** (STAR 6)
A valuation workflow at Moody's was spreadsheet-driven with no logging or versioning. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, and cut over with a rollback plan. The governance audit closed clean and the pipeline became the template for adjacent workflows. Shadow-running is my default for anything replacing a live process — including a rebalancing model.

**5. How do you use AI tooling in quantitative work without losing rigor?** (STAR 7)
I run agentic workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts — roughly 30-40% cycle-time reduction on comparable modules. The hard rule is that a human still signs off on anything governance-critical; the AI accelerates the mechanical layer, it does not own the methodology judgement.

## 3 questions to ask them

1. Where does the Balancing process currently create the most model friction — scenario coverage, execution constraints, or the latency between signal and implementation?
2. How does PDRE arbitrate between a methodology that is theoretically cleaner and one that survives the daily investment cycle? What does the Research Committee actually reject?
3. For a 12-month mandate, what would a successful first 90 days look like, and which piece of the rebalancing model stack would I own outright?

## The one competency gap to prepare for

**Total-fund rebalancing/execution mechanics and formal empirical/econometric research at CPP's scale.** My allocation work is advisory and model-build (SAA/TAA studies, optimization, scenario generation, sensitivity engines) — not running a daily balancing programme against live cash and exposure flows, and not factor-investing research per se. Prepared framing: "I have built and signed off on the analytics that sit under an allocation decision, and I have taken models from prototype to tested production. What I have not done is operate the daily balancing cycle — I would expect the first 60 days to be spent learning the execution constraints from the Trading and Beta/Collateral teams before I propose anything." Rehearse one concrete empirical-methods answer (calibration, backtesting, stationarity/regime treatment in the ESG) so the statistics question lands on evidence, not adjectives.