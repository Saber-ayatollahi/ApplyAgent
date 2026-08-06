## Likely technical questions

**1. Walk me through how you measure IRRBB — both EVE and NII — for a banking book position.**
At Moody's I oversee interest rate risk under parallel and non-parallel rate shocks aligned with OSFI B-12 / BCBS 368. EVE captures the present-value change of asset, liability, and off-balance-sheet cash flows under prescribed shock scenarios; NII captures the earnings impact over a 12-month horizon under repricing assumptions. The two views are complementary — EVE catches long-duration mismatch risk that NII misses, while NII catches near-term repricing gaps that EVE smooths over.

**2. How do you model behavioral assumptions like prepayment and non-maturity deposits?**
(Story 1 — cash flow engine.) In the cash flow projection engine I led at Moody's, I embedded behavioral cash flow assumptions and prepayment logic on top of contractual cash flows, with macro stress overlays to flex them under rate scenarios. The honest framing: I have built behavioral logic at the engine level; econometric calibration of prepayment / redemption / pull-through curves on retail product data is something I'd lean into RBC's existing methodology to extend.

**3. How do you reconcile and attribute period-over-period changes in IRRBB results to ALCO?**
Attribution decomposes deltas into rate-curve moves, balance-sheet composition changes, behavioral-assumption updates, and model/methodology refinements. (Story 2 — escalation.) I once held a release where portfolio sensitivities passed internal checks but didn't square with the client's economic intuition under a specific shock; I decomposed by asset class, isolated a short-end curve-calibration edge case, and walked the client's Head of Risk through the remediation. That mindset — decompose, defend each leg, escalate when economics don't agree with math — is what I'd bring to ALCO reporting.

**4. Walk through how you'd build an automated ETL pipeline for IRRBB measurement.**
(Story 6 — spreadsheet to Python.) At Moody's I migrated a valuation workflow from spreadsheets into Python and SQL with logging and versioning under model-governance audit. Pattern: parallel-build, run in shadow mode for two cycles, reconcile outputs to the legacy process, then cut over with rollback plan. For IRRBB specifically I'd embed balance-and-control checks at each ETL hop (row counts, notional totals, curve checksums) and version-control the behavioral assumption sets.

**5. How do you operate under a formal model governance framework?**
Delegated sign-off at Moody's means role-based authority over specific outputs — valuation, sensitivities, ALM aggregates — not portfolio investment strategy. The work is independent review of curves, spread calibration, cross-asset interactions, and economic defensibility, with documented escalation when math is right but economics are wrong. The framework parallels SR 11-7 and OSFI E-23 expectations on documentation, challenge, and assumption validation.

## Questions to ask

1. How is the IRRBB Measurement team split between Canadian and US/UK/EU subsidiary coverage, and where would this seat sit in that split on day one?
2. What's the current state of the ETL and reporting automation stack — is the move toward Vertica/Tableau/Blue Prism already in flight, or is this role expected to drive it?
3. How does the IRRBB Measurement team interface with Corporate Treasury, the behavioral-modelling group, and Group Risk Management on methodology change and ALCO reporting cadence?

## Competency gap to prepare for

**QRM and direct bank-treasury experience.** The 'nice to have' calls out QRM, and the role assumes ~2+ years of direct Treasury experience. I have IRRBB measurement, behavioral cash flow modelling, and ALM analytics depth at the vendor / institutional side (Moody's, Ortec) but I have not personally operated QRM nor sat inside a bank treasury function. Frame it as: 'I have done the measurement work that QRM produces, on an analogous platform; learning QRM's specific workflow is weeks, not months — and I bring the methodology grounding to challenge its outputs from day one.'