## BMO Director, Model Validation — Interview Brief

### 5 Most Likely Technical Questions & Model Answers

**1. Walk me through how you approach independent model review for an ALM cash-flow model. What are the key failure points you look for?**
Draw on Story 2 and the Moody's governance bullets. Start with curve-construction and calibration integrity (short-end inversion handling, spread calibration edge cases), then move to behavioral assumption defensibility (prepayment logic, prepayment speed vs. rate environment), then aggregation logic (security-level to portfolio-level — are sensitivities additive in the way the model assumes?). Emphasize the distinction between mathematically defensible and economically defensible — Story 2 is the concrete example: the model passed all internal checks but the portfolio-level sensitivity was wrong under a specific shock because of a curve-calibration edge case. The escalation held the release 48 hours; the client's Head of Risk became the direct escalation contact afterward.

**2. How do you validate a stochastic scenario generator? What does 'valid' mean in that context?**
From the Ortec record: a stochastic ESG is valid if (a) the marginal distributions of each risk factor are calibrated to historical or market-implied moments, (b) the correlation structure across factors is preserved under the simulation, (c) the tail behavior under stressed scenarios is economically plausible, and (d) the outputs pass mean-reversion / drift checks over long horizons. At Ortec I built and interpreted these for interest-rate, inflation, and currency factors. The validation approach was to benchmark generated paths against historical episodes (e.g., 2008, 2020) and against analytic approximations where available.

**3. Describe your experience with IRRBB analytics — specifically EVE and NII sensitivity under non-parallel shocks.**
At Moody's I oversaw interest-rate risk and duration analysis under both parallel and non-parallel rate shocks, aligned with OSFI B-12 / Basel IRRBB standards. The non-parallel case (steepener, flattener, twist) requires decomposing sensitivity by maturity bucket — key-rate duration analysis — and checking that the portfolio-level aggregate is consistent with position-level sensitivities. I independently reviewed these outputs and escalated curve-calibration edge cases that distorted short-end repricing. I can speak to EVE (PV of equity under shock) vs. NII (earnings impact over a 12-month horizon) as conceptually distinct measures requiring different validation logic.

**4. You migrated a spreadsheet workflow to Python under governance audit. How did you manage the model change risk?**
Story 6 directly. Parallel-built the Python pipeline; ran it in shadow mode for two production cycles alongside the live spreadsheet; reconciled output cell by cell; prepared a rollback plan before cutover. The governance audit required: (a) version control (Git) from day one, (b) embedded logging so every run was traceable, (c) documented reconciliation results signed off before migration. Audit closed without findings; the pipeline became the template for adjacent workflows.

**5. How do you handle a situation where a model developer pushes back on your validation finding?**
Story 2 again. The answer is: hold the line on the analytical finding, but be precise about what the finding is. 'This output is wrong' is not a finding. 'This portfolio-level sensitivity is inconsistent with the position-level decomposition under a short-end inversion because of how the curve is interpolated in the 3m–1y segment' is a finding. The specificity makes the pushback harder and the remediation clearer. Escalate if the developer and validator cannot agree — escalation is a feature of a healthy governance framework, not a failure.

---

### 3 Sharp Questions Saber Should Ask

1. **"What is the current split between model development and independent validation within the team — and how does BMO's governance framework define the boundary between the two functions for ALM and treasury models?"** (signals governance sophistication; surfaces whether the role is pure validation or includes development)
2. **"Which model families are highest priority for the validation roadmap over the next 12–18 months — is it the IRRBB EVE/NII models, liquidity stress models, or the behavioural models (prepayment, non-maturity deposits)?"** (shows you know the landscape; lets you map your depth to their needs)
3. **"How is BMO preparing for OSFI E-23's 2027 effective date — specifically the functional-separation requirements and the expanded AI/ML model coverage?"** (demonstrates regulatory awareness at the right level without overclaiming)

---

### 1 Competency Gap to Prepare For

**Banking-book model validation at a Schedule I bank (internal deposit/NMD models, internal prepayment models, OSFI-specific regulatory submissions).** Saber's IRRBB and ALM depth is real and directly transferable, but it was built on the institutional buy-side (pension funds, asset managers) rather than inside a bank's treasury. The gap is: (a) no direct experience validating non-maturity deposit (NMD) behavioural models or internal rate-transfer pricing models, and (b) no hands-on OSFI examination or MRM examination support experience. Frame this as: 'I've validated the same model families from the analytics-vendor side — including reviewing the outputs that your internal models produce — and I understand the regulatory intent of B-12. The bank-specific procedural layer (exam prep, MOU with OSFI, formal MRM policy) is the part I would ramp on fastest, and my OSFI E-23 awareness means I already understand the direction of travel.'