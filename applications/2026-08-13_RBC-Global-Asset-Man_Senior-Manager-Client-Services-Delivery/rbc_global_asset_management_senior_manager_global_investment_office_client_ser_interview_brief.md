## Five likely questions (with model answers)

**1. "Walk me through how you onboard a complex new client."**
Use STAR Story 3 (Calypso to PFaroe). I scoped the client investment desk's ALM configuration requirements into structured Product Owner requests, walked the PO through the desk's decision logic, and translated development constraints back into investment language. The client onboarded on schedule and the configuration pattern was reused across the rest of the migration cohort - the lesson being that onboarding failures are almost always translation failures, not technical ones.

**2. "Give an example of holding the line on quality under client deadline pressure."**
STAR Story 2. A client-delivery run passed every internal check but the portfolio sensitivities did not square with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**3. "How do you drive process enhancement without disrupting live client service?"**
STAR Story 6. A spreadsheet-driven valuation workflow had no logging or versioning and would not survive governance audit. I parallel-built the Python pipeline, ran it in shadow mode for two reporting cycles, reconciled outputs line by line, then cut over with a rollback plan. The audit closed cleanly and the pipeline became the template for adjacent workflows - change management first, code second.

**4. "How would you use AI/automation to improve client experience here?"**
STAR Story 7. Validation workload was growing faster than headcount, so I built agentic workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts - roughly 30-40% cycle-time reduction on comparable modules, with a human still signing off on anything governance-critical. The same pattern applies to client reporting: automate assembly and exception-flagging, keep judgment and client narrative with the manager.

**5. "What does 'sign-off authority' actually mean at your level?"**
STAR Story 9. Moody's runs a formal governance framework where sign-off is delegated by role, not title. The Assistant Director seat is an individual-contributor role with independent review authority: I attest to the defensibility of specific analytical outputs delivered to a client - typically $5-25bn per engagement - not to the client's investment strategy. That distinction is exactly why the escalation discipline matters.

## Three questions to ask

1. For Enterprise Strategic Clients, where does the current experience break down most often - onboarding hand-offs, reporting turnaround, or cross-platform coordination between GAM, Wealth Management, and Capital Markets?
2. What does the reporting and performance-analytics stack look like today, and is there appetite for the Senior Manager to re-engineer parts of it rather than only coordinate it?
3. How does the MD/Head measure success for this seat in the first 12 months - client-satisfaction metrics, onboarding cycle time, issue-resolution SLAs, or something else?

## The one competency gap to prepare for

**UHNW private-wealth clients and CIRO licensing.** My client base is institutional (pension funds, asset managers, consultants, insurers), not ultra-high-net-worth individuals or their family-office structures, and I do not currently hold a CIRO registration. Prepared answer: name it in the first 20 seconds, then bridge - complex multi-entity structures, bespoke mandates, demanding investment committees, and confidential, high-consequence deliverables are the same operating conditions (UPP three-plan merger as the proof point), and I will complete CIRO licensing on the required timeline. Do not improvise on wealth-management product mechanics, KYC/suitability, or brokerage trade lifecycle - say plainly that these are the pieces I would learn in the first 90 days.