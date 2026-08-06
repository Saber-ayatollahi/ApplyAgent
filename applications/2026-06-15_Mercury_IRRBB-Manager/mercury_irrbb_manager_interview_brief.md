## Likely technical questions & model answers

**1. Walk us through how you would design a cash flow engine for a bank balance sheet from scratch.**
At Moody's I led exactly this build for a multi-asset platform. I'd start by inventorying instrument types and identifying cash flow drivers (contractual, behavioral, optionality), then architect a configurable time-bucketed projection layer (T+1 → multi-year) so the same engine serves NII forecasting, EVE valuation, and liquidity gap. Behavioral overlays (prepayment, deposit decay, betas) sit as pluggable modules so assumptions can be re-calibrated without re-engineering the core. The whole thing runs in Python with logging and reconciliation hooks for auditability.

**2. How do NII and EVE differ, and when does each one mislead you?**
NII is an earnings view — income simulated forward under rate scenarios over a 1-3 year horizon — so it's sensitive to repricing timing, deposit betas, and reinvestment assumptions. EVE is a present-value view of all on- and off-balance-sheet cash flows, so it captures long-dated optionality and duration mismatch that NII won't see in a short horizon. NII can look benign when EVE is bleeding (e.g., long fixed assets funded by NMDs in a rising-rate regime), and vice versa. You need both, plus parallel and non-parallel shocks, to avoid being blindsided.

**3. How would you model non-maturity deposits — betas and decay?**
NMDs are the largest behavioral wildcard. I'd segment by product and customer type, estimate a deposit beta (the pass-through of policy rate to deposit rate) from historical regression with regime controls, and model decay using a survival curve estimated on account-level history. Both get sensitivity-tested — a ±20% beta shift and a faster/slower decay scenario — because the EVE result is highly sensitive to those assumptions, and that's the first thing validators and auditors probe.

**4. Tell me about a time you held back a model output that looked correct.** *(STAR Story 2)*
A client run produced sensitivities that passed all internal checks but didn't match the client's economic intuition under a specific rate-shock scenario. Under deadline pressure, I held the release, decomposed sensitivities by asset class, and identified a curve-calibration edge case in short-end inversion handling. Escalated to product owners and the client's Head of Risk, walked through remediation. Delayed 48 hours; client avoided acting on wrong numbers; defect captured in validation tests. I became their direct escalation contact afterward.

**5. How would you approach vendor selection for an ALM system?**
I'd anchor on the modeling requirements first: instrument coverage, behavioral-model flexibility (can you script your own NMD/prepayment logic, or are you stuck with vendor defaults?), scenario engine capability, and audit/documentation tooling. Then operational fit — run-time at monthly production cadence, data integration with source-of-record systems, and governance hooks for model validation. From my Moody's seat I've seen the implementation side of QRM-class platforms and PFaroe — the deal-breaker is usually behavioral-model flexibility and run-time, not the headline NII/EVE math.

## Questions Saber should ask

1. **Where in the vendor-selection process is the team today** — long-list, short-list, or already converging? And what's driving the timing (regulatory milestone, internal forecast cycle, board commitment)?
2. **How is the modeling team organized relative to Finance, Treasury, and Risk** — does the IRRBB Manager own the assumptions outright, or are betas/decay curves jointly governed with the deposit-product owners?
3. **What does the model validation function look like at Mercury today**, and how will it scale as the cash flow engine moves into monthly production? (Signals seriousness about governance and tells Saber what the audit footprint will look like.)

## One competency gap to prepare for

**Hands-on QRM / Empyrean / BancWare experience.** Saber has built and validated cash flow / ALM engines at Moody's and used GLASS at Ortec, but not these specific named platforms. Prep: review QRM and Empyrean architecture at a feature-level (instrument coverage, behavioral model libraries, scenario engine, reporting layer) so he can speak credibly to vendor evaluation criteria, and reframe his Moody's PFaroe + cash flow engine work as direct transferable platform experience. Lead with *'I've been on the implementation side of comparable institutional ALM platforms — the evaluation framework transfers; the UI doesn't.'*