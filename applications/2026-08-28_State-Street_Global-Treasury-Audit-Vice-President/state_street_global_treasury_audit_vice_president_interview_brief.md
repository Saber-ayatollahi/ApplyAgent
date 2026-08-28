## 5 likely technical questions

**1. "Walk me through how you would assess the design effectiveness of controls over IRRBB measurement."**
Start where the numbers are made: curve construction and spread calibration, assumption ownership and approval, scenario design (parallel and non-parallel shocks), model input/output reconciliation, then reporting and escalation. At Moody's I do this review before production release — I check that assumptions are documented, benchmarked, and economically defensible, and that any exception has an owner and an escalation path. Story 6 (spreadsheet → Python with shadow-mode reconciliation) is the auditable-control example.

**2. "How do NII sensitivity and EVE sensitivity differ, and where do auditors most often find weakness?"**
NII is an earnings measure over a defined horizon and is dominated by repricing timing and behavioral assumptions; EVE is a present-value measure over the full life of positions and is dominated by discounting and long-dated cash flows. The weak spots are behavioral assumptions (non-maturity deposits, prepayment) and scenario coverage — assumptions that are never back-tested and shock sets that miss curve twists and short-end inversions.

**3. "Give an example of providing credible challenge under deadline pressure."**
STAR Story 2: sensitivities passed every internal check but conflicted with the client's economic intuition under one rate shock. I held the release, re-ran sensitivities decomposed by asset class, found a short-end inversion edge case in curve calibration, escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the defect was fixed upstream and captured in validation tests; I became that Head of Risk's direct escalation contact.

**4. "How do you validate behavioral cash-flow assumptions in a projection model?"**
I built the behavioral layer of an enterprise multi-asset cash-flow projection engine — prepayment logic, behavioral cash-flow assumptions, and macro stress overlays across base, stress, and reverse-stress scenarios, bucketed T+1 through multi-year. Validation means testing sensitivity of outputs to each assumption, checking the assumption against observed behavior, and confirming stressed behavior moves in the economically correct direction rather than just passing a tolerance check.

**5. "How would you explain a complex Treasury risk finding to a Board committee or a regulator?"**
Lead with the exposure and the decision at risk, not the methodology. At Ortec I presented ALM and LDI studies to pension investment committees: funding-ratio distributions under base and stressed regimes, duration-gap contribution to volatility, then explicit recommendations. Same discipline in audit — state the control weakness, the quantified consequence, and the remediation, with the technical detail held in reserve.

## 3 questions Saber should ask

1. How does the Global Treasury Audit plan split coverage between IRRBB measurement/model usage and the governance layer (ALCO reporting, limits, escalation) — and where does leadership think the current coverage is thinnest?
2. What is the current supervisory posture on Treasury for State Street, and how much of this VP's time is spent in direct regulatory engagement versus audit execution?
3. How does Corporate Audit coordinate independent challenge with Model Risk Management on Treasury models — where does the line sit, and does that create duplication or a gap?

## The one competency gap to prepare for

**No internal-audit-function experience and no non-maturity deposit modeling.** Prepare a crisp two-sentence framing: "My independent review and challenge has been exercised inside a model-governance framework rather than a Corporate Audit function — the judgment, evidence standard, and escalation discipline transfer directly; the audit methodology (risk assessment, scoping, workpaper standards, issue development) is the part I would learn fast, and I have delivered controls-and-governance documentation work at EY." On deposits: be explicit that my behavioral modeling is prepayment and cash-flow-behavior based on institutional portfolios, and that non-maturity deposit modeling is the adjacent extension — do NOT claim it.