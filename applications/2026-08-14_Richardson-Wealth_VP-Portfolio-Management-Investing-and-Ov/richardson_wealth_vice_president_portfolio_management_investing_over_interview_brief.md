## 5 likely technical / role questions

**1. "Walk me through how you'd design model lifecycle governance for a set of model portfolios — approvals, versioning, documentation, change notification."**
I sit on Moody's model governance committee, which owns methodology review, documentation and benchmarking standards, and model-performance assessment for client-delivered analytics. My frame is: a model isn't approved until three things exist — a documented methodology, a benchmark it is measured against, and a named owner for the escalation path when output stops being defensible. Change notification is the same discipline applied downstream: whoever consumes the output must be told what changed and why before they act on it.

**2. "Give me an example of holding the line on a control when there was delivery pressure."** *(STAR Story 2)*
A client-delivery run produced portfolio-level sensitivities that passed every internal check but didn't square with the client's economic intuition under a specific rate shock. I held the release, re-ran sensitivities decomposed by asset class, and traced it to a curve-calibration edge case at the short end. I escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers, the defect was fixed upstream and captured in validation tests, and I became that Head of Risk's direct escalation contact.

**3. "How do you get an investment team and a development team to agree?"** *(STAR Story 3)*
During the Calypso-to-PFaroe migration, a pension client's configuration requirements were getting lost between their investment desk and our development organization. I scoped the requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated dev's constraints back into investment language. The client onboarded on schedule and the configuration pattern was reused across the rest of the migration cohort — which is the scalability test, not the single client.

**4. "You've replaced manual workflows with automated ones. How did you do it without breaking live delivery?"** *(STAR Story 6)*
A spreadsheet-driven valuation workflow had limited logging and no versioning — not acceptable under model-governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled output line by line, then cut over with a rollback plan. The audit finding closed and the pipeline became the template for adjacent workflows. Shadow-run-then-cut-over is how I'd approach any advisor-facing platform migration where the current process still has to work tomorrow morning.

**5. "What portfolio analytics matter most in an advisor-facing experience, and how do you standardize them?"**
At Ortec I ran asset-only and surplus optimization on VaR and CVaR with risk decomposition and attribution, and presented the results to pension investment committees; at Moody's I review the aggregation logic that turns security-level exposures into portfolio-level risk metrics. The lesson from both: analytics are only trusted when the inputs are standardized first — benchmark, pricing source, and performance calculation convention agreed once. Contribution-to-risk and concentration diagnostics are what actually change a conversation, but they are meaningless if two systems disagree on the denominators.

## 3 questions Saber should ask

1. This role spans Richardson Wealth and IA Private Wealth — are the two firms on a common portfolio management and performance stack today, or is convergence part of the mandate? Where does the current data disagreement hurt most?
2. Who holds the approval authority for a model portfolio change today, and what does the audit evidence trail look like end-to-end? I'd want to know whether I'm formalizing an existing governance forum or standing one up.
3. The success measures reference advisor adoption and reduced NIGO/exception rates — what's the current baseline, and which of those does leadership weight most heavily in year one?

## The one competency gap to prepare for

**Canadian dealer / advisory-channel domain: KYC, IPS, suitability, CIRO obligations, and advisor-facing dealer operations.** Saber's governance, analytics, and platform-migration experience is institutional (pensions, asset managers, insurers) — not retail advisory. Prepare a 45-second honest answer: "I have not run a dealer's suitability program. What I have done is embed regulatory requirements into system design at EY on IFRS 17 and 9, and build auditability into analytics pipelines at Moody's. The mechanics of IPS alignment and suitability evidence are a vocabulary I'd learn in the first 60 days; the discipline of making a control provable in a system is what I already do." Do NOT claim tax-aware rebalancing, householding, trading/custody operations, or NIGO-rate ownership.