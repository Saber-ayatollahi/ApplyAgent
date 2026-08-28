## Five likely technical questions

**1. "A full-repricing risk run produces sensitivities that pass every internal check but look wrong. What do you do?"**
Hold the release. I did exactly this at Moody's: re-ran sensitivities decomposed by asset class, isolated a curve-calibration edge case in short-end inversion handling, escalated to product owners and the client's Head of Risk, and walked them through remediation. Release slipped 48 hours, the client avoided acting on wrong numbers, and the defect was captured in validation tests upstream. Mathematically defensible and economically defensible are two different bars.

**2. "How do you think about the market data required to value a book — what breaks first?"**
My sign-off mandate covers curve construction, spread calibration, and cross-asset interaction review before production release. The failure modes I see most often are calibration at curve boundaries, stale or inconsistent spread inputs across instruments valued off the same curve, and inconsistent scenario shifts applied to correlated inputs. I validate outputs for rates, FX, and inflation instruments, and I check sensitivity consistency once instrument-level analytics aggregate to portfolio level.

**3. "Design and maintain economic scenarios — walk me through building a scenario set."**
At Ortec I built and interpreted stochastic economic scenario generators calibrated to client assumptions, then ran funding-ratio distributions under base and stressed regimes and decomposed which risk factors drove the tails. At Moody's I extended that to deterministic overlays: parallel and non-parallel rate shocks, behavioral cash-flow assumptions, prepayment logic, and macro stress and reverse-stress overlays inside a multi-asset cash-flow projection engine I led the design of.

**4. "How do you write a model spec for developers and then test their implementation?"**
Both halves of that loop are my day job. During the Calypso→PFaroe migration I scoped client investment-team requirements into structured Product Owner requests, translated dev pushback back into investment language, and validated model outputs post-deployment. On the testing side, when migrating a spreadsheet workflow to a Python pipeline I parallel-built, ran shadow mode for two cycles, reconciled outputs line by line, then cut over with a rollback plan.

**5. "You're an Assistant Director — what does 'sign-off authority' actually mean?"**
Moody's delegates sign-off by role within a formal governance framework, not by title. Mine attests to the defensibility of specific analytical outputs — valuation, sensitivity, ALM — not to a client's investment strategy. I also sit on the model governance committee covering methodology review, documentation and benchmarking standards, and model-performance assessment.

## Three questions to ask

1. How are the FE team's product groups carved up today, and which product family would this VP's small group own — and where is the current model backlog deepest?
2. With 10M+ positions a day under full repricing, where does the performance budget force approximation in the models, and who arbitrates the accuracy-versus-throughput trade-off?
3. How does the handoff work between FE model specs and the development organization — and how do model validators and client representatives feed changes back into the spec cycle?

## The one competency gap to prepare for

**Building pricers versus validating them, in a compiled stack.** My evidence is reviewing and validating derivatives pricing outputs (rates, FX, inflation), not constructing arbitrage-free pricers for exotic IR/FX or securitized products in C++/C#. Prepared framing: I have the pricing theory (CFA, MSc Financial Modelling, PDE/numerical-methods background), the validation and benchmarking discipline, and prototype-level Python; my prototyping-to-spec-to-test contribution is immediate, and compiled-language implementation is where I would lean on the developers and ramp. Do not claim exotic-book or securitized-product modelling, C++/C#, or direct line management of reports — mentorship and senior review authority are the honest claims.