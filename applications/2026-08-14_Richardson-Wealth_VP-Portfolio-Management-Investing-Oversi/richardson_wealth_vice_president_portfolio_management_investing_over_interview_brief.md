## Likely technical / role questions (with model answers)

**1. "This role is about advisor workflows — proposal, IPS, suitability, rebalancing. What's your exposure?"**
Be direct: my platform work has been institutional (pension funds, asset managers, consultants on PFaroe DB/PM), not retail advisory. What transfers is the pattern — I sat between client investment teams and product owners during the Calypso→PFaroe migration, scoped their decision logic into structured PO requests, and translated dev constraints back into investment language (STAR Story 3). The vocabulary changes; the translation job does not. I'd spend my first 60 days shadowing advisors the way I shadowed investment desks.

**2. "How would you approach model lifecycle governance for model portfolios — approvals, versioning, documentation, drift?"**
I'd anchor on what I do on Moody's model governance committee: methodology review, documentation and benchmarking standards, and model-performance assessment before anything reaches a client. Translated here: a versioned model record with a named approver, a change-notification workflow tied to that version, and embedded tolerance checks (drift, concentration, risk-band) that generate exceptions rather than relying on advisor vigilance. Governance only works when the control is in the workflow, not in a policy PDF.

**3. "Tell me about a time you held the line on a number under delivery pressure."**
STAR Story 2: a client run passed every internal check but the portfolio sensitivities didn't square with economic intuition under one rate shock. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case at the short end, escalated to the product owners and the client's Head of Risk, and walked through remediation. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was fixed upstream and captured in validation tests. I became that Head of Risk's direct escalation contact.

**4. "You'd need to influence Directors and VPs across Compliance, Ops, Data and Technology without authority. Example?"**
EY IFRS 17 (STAR Story 5): finance, actuarial and IT were out of sync on data sourcing and CSM mechanics. I built shared requirements documentation, walked each function through the others' constraints, then narrowed it to the three decisions that actually needed executive sign-off and escalated only those. The milestone was hit and the documentation was reused on later engagements. Influence comes from shrinking the decision set, not from winning debates.

**5. "How do you get manual workflows onto a platform without breaking live delivery?"**
STAR Story 6: a spreadsheet-driven valuation workflow at Moody's had no logging or versioning and wouldn't survive a governance audit. I parallel-built the Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, then cut over with a rollback plan. Audit closed satisfactorily and the pipeline became the template for adjacent workflows. Same playbook applies to advisor tooling: shadow, reconcile, cut over, keep the exit.

## Questions Saber should ask

1. "Where does the current advisor journey break most expensively today — proposal-to-IPS, rebalance execution, or the review cycle — and how is that measured now?"
2. "Richardson Wealth and IA Private Wealth have different books and likely different platforms. Is the mandate one converged experience, or a common capability layer with two front ends? That changes the sequencing entirely."
3. "Who owns the data standards today — benchmarks, security master, pricing, performance calculation? Is this role accountable for those standards or a consumer of them?"

## The one competency gap to prepare for

**Canadian dealer / advisor-channel domain: KYC, IPS, suitability obligations (CIRO), managed-account and discretionary structures, NIGO and custody operations.** Saber has never worked inside an investment dealer. Do not bluff mechanics. Prepare a 60-second honest frame — institutional platform delivery + model governance + suitability-adjacent controls (risk tolerance, concentration, drift) is the transferable core — and do 3-4 hours of reading on CIRO suitability/KYC obligations and Canadian managed-account structures so the vocabulary is fluent even though the tenure isn't there. Pair it with a concrete question back to the interviewer; curiosity reads better than a thin claim.