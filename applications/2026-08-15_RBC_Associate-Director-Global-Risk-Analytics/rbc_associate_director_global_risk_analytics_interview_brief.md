## 5 likely technical questions

**1. "Walk me through how you'd specify and validate a VaR model for a fixed income and rates-derivatives book."**
Anchor on the Ortec work: asset-only and surplus optimization on VaR and CVaR via GLASS, with risk decomposition and contribution-to-risk to see which exposures drive the tail. Cover the specification choices explicitly - historical vs. Monte Carlo simulation, lookback window, risk-factor selection (curve tenors, spread, FX), and full revaluation vs. sensitivity-based P&L approximation. Close on validation: benchmark against an independently-built alternative and check that decomposed contributions are economically explainable, not just numerically stable.

**2. "Tell me about a time a model output looked fine but you didn't sign off."** (STAR Story 2)
A client-delivery run produced portfolio-level sensitivities that passed every internal check but conflicted with the client's economic intuition under a specific rate shock. I held the release under deadline pressure, re-ran sensitivities decomposed by asset class, and isolated a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours, the defect was remediated upstream and captured in validation tests, and I became that Head of Risk's direct escalation contact.

**3. "How do you build a scenario set - and how do you know it's severe enough?"** (STAR Story 1)
At Moody's I led the design of a multi-asset cash flow projection engine supporting base, stress, and reverse-stress scenarios with configurable time buckets from T+1 to multi-year, layering macro stress overlays and behavioral assumptions. Severity calibration comes from two directions: historically-anchored shocks and reverse-stress - solve for the scenario that breaks the constraint, then judge its plausibility. At Ortec I built stochastic scenario generators, so I can speak to both deterministic and distributional approaches.

**4. "How do you validate a derivatives pricing output you didn't build?"**
My Moody's mandate is review, not development: I check curve construction and spread calibration inputs first, then test outputs for internal consistency - do sensitivities aggregate coherently from security level to portfolio level, do rate/FX/inflation instruments respond sensibly to the same shock. Where an independent benchmark exists, I compare; where it doesn't, I stress the pricing at parameter boundaries. Anything mathematically defensible but economically unsupported gets escalated rather than signed.

**5. "What's your Python and SQL footprint - what have you actually shipped?"** (STAR Story 6)
I re-engineered a spreadsheet-driven valuation workflow into a Python pipeline (pandas, NumPy, SciPy) with logging, versioning, and validation controls - parallel-built, shadow-run for two cycles, reconciled, then cut over with a rollback plan. It closed a governance audit and became the template for adjacent workflows. SQL (PostgreSQL) is daily for data extraction and reconciliation. I've also built agentic AI review workflows that cut cycle time ~30-40% on comparable modules, with humans still signing off on governance-critical review.

## 3 questions to ask

1. How is the split between methodology specification and prototype implementation drawn on this team - does the Associate Director own the prototype through to the Risk IT handoff, or hand off at the spec?
2. Where is the biggest current methodology pressure: the VaR/SVaR framework itself, the market data and scenario services layer, or CCR coverage across asset classes?
3. What does the approval path to the senior management committee look like in practice - how many methodology proposals go through in a year, and what typically sends one back?

## The one competency gap to prepare for

**Trading-book and CCR machinery.** The JD names CCR models and SVaR; my exposure is buy-side and balance-sheet portfolios, not a trading desk, and I have no hands-on CCR/PFE/xVA, SVaR calibration, or VaR backtesting-and-exceptions work. Do not claim it. Prepare instead to (a) speak fluently on the concepts - SVaR as a stressed-window recalibration of the VaR engine, PFE as a simulated exposure profile with netting and collateral, backtesting exceptions under a traffic-light regime - and (b) frame the transferable core: risk-factor selection, curve calibration, simulation design, sensitivity consistency, and defensible documentation are identical mechanics. Read the Basel market-risk and CCR standards before the technical round so the vocabulary is precise.