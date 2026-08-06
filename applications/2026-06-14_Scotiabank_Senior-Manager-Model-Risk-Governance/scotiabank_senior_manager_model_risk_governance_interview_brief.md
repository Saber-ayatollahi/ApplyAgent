## Likely technical questions

**1. Walk us through how a model risk management framework should be structured under OSFI E-23, and what you would prioritize in the first 90 days.**
E-23 (effective 2027-05-01) widens scope to include AI/ML, sharpens functional separation between development, validation, and use, and raises expectations on inventory completeness and tiered risk rating. First 90 days: gap-assess the current Framework/Policy/Standards against the final guideline; map the existing model inventory to the revised scope (including AI/ML and end-user computing); and re-baseline the model risk rating methodology so tiering drives the cadence of performance monitoring and revalidation. I would do this in lockstep with MVA, BGRO, Audit, and Finance so the framework reflects how the Bank actually decides.

**2. Tell us about a time you escalated a model output. What did you do and what was the outcome?**
(STAR Story 2.) A client-delivery run produced portfolio-level sensitivities that passed internal checks but did not square with the client's economic intuition under a specific rate-shock. I held the release, decomposed sensitivities by asset class, identified a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk, and walked through a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was captured as a validation test. I became that Head of Risk's direct escalation contact.

**3. How would you design model performance monitoring that is consistent across model types — credit, market, operational, AI/ML — without becoming bureaucratic?**
Start from the risk rating: tier drives metric set, frequency, and threshold severity. For each tier define a minimum monitoring spec (back-testing or benchmarking metric, stability/PSI, input-data drift, materiality of breaches) and let model owners add type-specific tests on top. Exceptions land in one issue-management workflow with severity, owner, and SLA — so the framework is one process with calibrated parameters, not many. The win is traceability into policy and into the Board pack.

**4. How do you ensure model inventory completeness — including end-user computing and AI/ML — and what would you do with SAS MRM (or equivalent) to support it?**
Two-track: a top-down discovery cycle (business-line attestations against a defined model definition, run on a fixed cadence) and a bottom-up control (intake gating tied to NIRA, RCSA, and change management so new or modified models cannot go live without an inventory record). In SAS MRM I would codify the E-23 fields — tier, owner, validator, monitoring metrics, last review date, issue links — so the inventory becomes the system of record for attestations, regulatory reporting, and the Board view.

**5. Walk us through governance documentation you have personally authored or owned.**
At Moody's I author the documentation that sits behind delegated sign-off: assumption registers, validation evidence, exception logs, escalation memos, and the runbooks for the cash-flow projection engine and IRRBB analytics. At EY I drafted governance and control documentation for IFRS 17/IFRS 9 implementations. At Ortec I produced ALM and scenario-generator model documentation that supported client-side model risk reviews. The common thread is documentation built to defend the model under independent challenge — not just to satisfy a template.

## Questions Saber should ask

1. How is the model risk rating methodology currently set up, and where do you see the biggest tension between the rating, the monitoring cadence, and the revalidation calendar?
2. As OSFI E-23 reaches its 2027 effective date, what does the target operating model look like for AI/ML coverage and for material subsidiaries — and where is the governance team in that build-out today?
3. How does this role's mandate interact day-to-day with MVA and BGRO — where does Model Risk Governance own the answer versus convene the answer?

## Competency gap to prepare for

**SAS MRM / IBM OpenPages hands-on and Spanish.** I have not configured SAS MRM or OpenPages directly — my inventory and attestation work has been on Moody's internal governance tooling and bespoke client environments. Prepare to frame this as a tooling-translation question (the data model and workflow concepts are common across platforms) and to commit to a specific ramp plan. Spanish is a flagged asset for material-subsidiaries work; be honest that it is not in the toolkit today.