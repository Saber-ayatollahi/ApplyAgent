## Likely technical questions (with model answers)

**1. Walk me through how you would validate a logistic regression PD model for a Canadian retail credit portfolio.**
Frame as four lenses: conceptual soundness (variable selection, economic rationale, segmentation), data integrity (sampling window, default definition, missing-data treatment, multicollinearity via VIF), statistical performance (AUC/Gini, KS, calibration plots, Hosmer-Lemeshow, out-of-time backtest), and benchmark challenge (build a parallel XGBoost or alternative-specification model in Python to test whether the champion's discriminatory power survives). Close with documentation and governance — escalate any economically indefensible coefficient signs, which mirrors the escalation discipline I use at Moody's on derivatives sensitivity outputs.

**2. Tell me about a time you held back a model output that passed internal checks.**
Use Story 2 from the bank. A client-delivery run produced portfolio sensitivities that passed all internal validation but didn't square with the client's economic intuition under a specific rate-shock scenario. I held the release under deadline pressure, decomposed sensitivities by asset class, isolated a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk, and ran the remediation. Release slipped 48 hours; client avoided acting on wrong numbers; the defect went into validation tests. That is the muscle EMRM is hiring for.

**3. How would you build a benchmark model to challenge a champion XGBoost credit model?**
Two-layer approach. First, a transparent statistical benchmark — penalized logistic regression with the same feature set — to isolate how much lift the non-linear/interaction terms actually deliver versus the linear baseline. Second, an alternative non-linear specification (random forest or gradient-boosted alternative) trained on the same window to test specification robustness. Compare AUC, calibration, and decile-level rank-ordering on a hold-out and out-of-time sample, and stress for population stability (PSI). Document where champion and benchmark disagree — those segments are where the model risk lives.

**4. How do you think about model risk in machine learning models versus traditional regression?**
The validation toolkit shifts but the principles don't. ML adds explainability risk (SHAP / partial dependence to make the black box defensible), overfitting risk (cross-validation discipline, hold-out and out-of-time testing), stability risk (PSI on inputs, drift on outputs), and data-leakage risk (feature engineering that peeks at the target). OSFI E-23 explicitly brings AI/ML into scope, so documentation has to cover training data lineage, hyperparameter choices, and monitoring triggers — not just point-estimate performance.

**5. Walk me through your Python and SQL stack and a recent piece of code you'd be willing to defend in code review.**
Daily stack: Python (pandas, NumPy, SciPy, scikit-learn) under Git, with SQL (PostgreSQL) for extraction against large data sets. Recent piece: I led the design of a multi-scenario cash-flow projection engine — re-engineered from a manual spreadsheet workflow into an auditable Python pipeline with embedded logging, validation tests, and shadow-run reconciliation before cutover. The governance bar was the same as a validation deliverable: anyone reading the repo should be able to reproduce the output and trace each assumption to its source. That's the standard I'd bring to EMRM benchmark builds.

## Sharp questions to ask

1. How is the credit-model book in Canadian Banking segmented across PD/LGD/EAD, application versus behavioural, retail versus small business — and where on that map is the highest validation backlog today?
2. How does EMRM split work between initial validation and ongoing monitoring under the materiality-and-uncertainty rating, and where would this seat sit on that split?
3. As OSFI E-23 brings AI/ML explicitly into model risk scope, how is EMRM evolving its validation playbook for ML champion models — and is the team building internal ML benchmarking tooling?

## Competency gap to prepare for

**Direct retail credit-risk model development experience.** The Master Repo evidences model validation, governance, and quant-modelling depth, but not hands-on PD/LGD/EAD development on a Canadian retail book. Prepare to: (a) own the gap honestly — frame as model-validation-side rather than developer-side credit experience; (b) demonstrate fluency in the methodology (Basel IRB parameter framework, default definition, downturn LGD, EAD CCF) through reading; (c) lean on transferable evidence — logistic-regression and ML grounding from the MSc, stochastic credit-style scenario work at Ortec, and the validation discipline at Moody's that translates one-for-one.