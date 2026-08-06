## 5 Most Likely Technical Questions

**1. Walk us through how you would validate a wholesale credit PD model.**
Frame the four pillars: conceptual soundness (segmentation, variable selection, economic intuition), data integrity (sample window, default definition, exclusions), statistical performance (AUC/Gini, KS, rank-order stability, calibration), and ongoing monitoring (PSI on inputs, backtesting on outputs). Close on documentation and findings management — the artefacts have to defend the model to regulators and audit, not just internal users. Tie to the Moody's review-and-challenge work where I escalate outputs that are mathematically defensible but economically unsupported (Story 2).

**2. A model passes statistical tests but the business says the output looks wrong. What do you do?**
This is exactly Story 2 from my Moody's experience. Hold the release, decompose the sensitivities by sub-component, look for the regime where the model's assumptions break (in my case, short-end curve inversion handling), escalate to model owners and the client's Head of Risk, and remediate upstream rather than patching downstream. Mathematically valid is necessary but not sufficient; economically defensible is the bar.

**3. How do IFRS 9 ECL models differ from regulatory IRB credit models, and what does that mean for validation?**
IFRS 9 is point-in-time, forward-looking, and lifetime-ECL for Stage 2/3 — driven by macroeconomic scenarios and SICR (significant increase in credit risk) triggers. IRB is through-the-cycle and capital-focused. Validation implications: IFRS 9 requires heavier scrutiny of the macro scenario design, weights, and SICR thresholds; IRB requires more emphasis on long-run calibration and downturn LGD. My EY IFRS 9 transformation experience covers the methodology and governance layers; my Ortec scenario-generator work covers the stochastic macro inputs.

**4. How would you use Python or R in a validation workflow?**
Replicate the developer's model independently end-to-end (do not trust the developer's code as the validation artefact); build benchmark or challenger models where feasible; automate statistical tests, stability checks, and sensitivity analyses; produce reproducible validation reports with embedded outputs. At Moody's I migrated spreadsheet workflows to Python pipelines with logging, validation, and version control — the same pattern applied to a validation function.

**5. How do you communicate a technical validation finding to a non-technical business owner?**
Lead with the business consequence (what decision could be wrong, what is the magnitude), not the statistical metric. Then show one chart that makes the issue visible. Then the recommendation and the remediation plan. Keep the methodology detail for the appendix and the model developer conversation. This is the muscle I have built preparing analytical summaries for Heads of Risk at Moody's clients.

## 3 Sharp Questions to Ask

1. How is the QRC validation work split between wholesale credit, capital markets, and trading-book models — and where is the team most stretched right now?
2. What is the current state of the model inventory and the annual-review cycle? Is the bottleneck new-model validation, annual revalidation, or findings closure?
3. How does QRC in Canada interact with the global MUFG Model Governance Program — are validation standards and templates set globally, or does Canada have local autonomy on methodology?

## Competency Gap to Prepare For

**Hands-on wholesale credit risk model validation experience (PD/LGD/EAD, ALLL/CECL/IFRS 9 ECL models).** My credit-model exposure is through IFRS 9 transformation at EY (methodology, data, governance) and through stochastic credit-spread modelling at Ortec — not through validating a bank's production PD/LGD models end-to-end. Prepare to (a) demonstrate the transferable validation framework I apply at Moody's on ALM and derivatives outputs maps directly onto credit models, (b) speak credibly on PD/LGD/EAD mechanics, AUC/Gini/KS, PSI, and backtesting from CFA and self-study, and (c) own the gap honestly — the model risk discipline is the same; the asset class is what I will pick up fastest in the first 90 days.