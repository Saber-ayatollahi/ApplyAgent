## 5 likely technical questions

**1. "Walk me through how you validate a model you did not build."**
Start with intended use and materiality, then assumptions and data, then independent reproduction of key outputs, then benchmarking against an alternative specification, then sensitivity/stress behaviour, then documentation and findings. At Moody's this is the standing process: curve construction, spread calibration, and cross-asset interactions are reviewed before production release, and anything without mathematical or economic support is escalated rather than signed.

**2. "Give me a case where you rejected or held a model output."** (STAR Story 2)
A client run produced portfolio sensitivities that passed every internal check but conflicted with economic intuition under one rate shock. I held the release, decomposed sensitivities by asset class, isolated a short-end-inversion curve-calibration edge case, escalated to product owners and the client's Head of Risk, and the defect was remediated upstream and captured in validation tests. Release slipped 48 hours; the client did not act on wrong numbers.

**3. "How do you approach ongoing model performance monitoring?"**
I sit on the model governance committee, where model-performance assessment, benchmarking, and documentation standards for client-delivered analytics are set. Practically: define expected behaviour ex ante, monitor output stability and sensitivity consistency across cycles, compare against a benchmark or challenger view, and treat drift or unexplained regime behaviour as a finding with an owner and a date.

**4. "How would you validate a credit risk / ECL-type model without having built one?"**
Be honest first: my build experience is valuation, rates, and cash-flow/stress models, not PD/LGD scorecards. Then the transferable structure: segmentation and data lineage, discriminatory power and calibration testing, override and behavioural assumptions, macro-scenario linkage, and back-testing against realised outcomes. IFRS 9 and IFRS 17 delivery at EY put me alongside the finance and actuarial teams standing up impairment reporting, so the reporting end of the chain is familiar.

**5. "What does your Python/R work actually look like?"** (STAR Stories 6 and 7)
I re-engineered spreadsheet valuation workflows into Python pipelines — parallel build, two shadow cycles, output reconciliation, cut-over with rollback — which closed a model-governance audit on logging and versioning. I also built agentic AI workflows (Claude Code, Cursor) for first-pass code review, validation scaffolding, and anomaly detection, cutting cycle time ~30–40%, with human sign-off retained on governance-critical review. R and SQL are intermediate; SAS I would need to pick up.

## 3 questions Saber should ask

1. How is QRC's coverage split between wholesale credit models and the trading, pricing, and securitization models — and which side would this AVP own in year one?
2. What is the current state of the model inventory and the annual-review backlog, and how are findings tracked to closure with developers?
3. Where has the Canada Branch's validation work drawn the most regulator or internal-audit attention recently, and how does that shape the 2026 validation plan?

## The one competency gap to prepare

**Wholesale credit risk modelling and ALLL/CECL/ML validation.** No PD/LGD/EAD development or ML model validation in the record, and no SAS. Prepare a crisp, non-defensive answer: name the gap, show the validation framework is model-agnostic, cite one credit-model concept studied properly (e.g., discrimination vs. calibration, or macro-scenario conditioning in ECL), and offer the CFA credit curriculum plus IFRS 9 delivery as the on-ramp. Do not claim hands-on credit-model development in any round.