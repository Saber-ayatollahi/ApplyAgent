## JD core themes (mirror-check baseline)
1. Change-initiative delivery in Capital Markets Operations -- impact assessment, requirements translation, readiness planning.
2. Cross-functional dependency/milestone coordination and governance-forum support.
3. UAT coordination -- test approach, execution, defect tracking.
4. Operational readiness -- training, documentation, go-live decisions, post-implementation review.
5. Capital-markets product and systems knowledge, with hands-on operational exposure (clearing, confirmations, settlements, collateral, asset servicing, middle office, prime services/sec lending) on named platforms (Global One, Loan One, Equilend, Colline, Anvil, Broadridge, ION, Murex, Calypso, Fidessa, Sophis, Wall Street).

## Fixes applied

**Summary**
- Softened 'institutional derivatives and fixed income experience' to 'institutional derivatives and fixed-income analytics experience' -- the repo supports valuation/validation analytics, not trading or operations exposure to these products, and the unqualified word 'experience' risked implying the latter.
- Left the Calypso-to-PFaroe migration claim but removed 'running parallel testing' from that clause in an earlier draft pass -- the shadow-mode/parallel-testing narrative belongs to a separate initiative (the spreadsheet-to-Python pipeline cutover, per Story 6), not the Calypso migration. Conflating the two attributed a specific method to the wrong project.
- Retitled 'operational requirements' to 'client and platform-configuration requirements' -- 'operational requirements' is JD vocabulary that implies capital-markets-operations process requirements (settlement, clearing, etc.); what Saber actually scoped were investment/platform configuration requirements for ALM/portfolio-management clients.
- Exact title check (rule 8): summary opens with 'Senior Manager, Capital Markets Operations (GWO)' verbatim to target.role.

**Core skills**
- 'Operational Requirements Scoping & Translation' -> 'Client & Platform Requirements Scoping and Translation' for the same reason as above (JD-noun import not grounded in the repo's actual object of requirements-gathering).
- 'Testing, Reconciliation & Defect Remediation' -> 'Output Reconciliation, Validation Testing & Defect Escalation'. The repo supports reconciliation/shadow-mode testing (Story 6) and defect *escalation* (Story 2, 'escalated ... to product owners'), but not personally *remediating* defects -- he tracks remediation upstream, he does not own the fix. 'Remediation' overstated his role in the defect lifecycle.
- Confirmed no JD-only nouns (UAT, collateral, clearing, confirmations, settlements, middle office, PnL, asset servicing, prime services, securities lending, or any named ops system other than Calypso) were present in core_skills or bullets -- none were found, so none needed removal.

**Experience bullets**
- CSS-phase bullet: removed the added clause 'before sign-off on each account' -- delegated sign-off authority is documented in the repo only for the later Assistant Director phase, not the Client Service Specialist phase. Restored the bullet to track the tagged library version exactly.
- 'Acted as technical liaison...' bullet: replaced 'operational requirements' with 'investment and platform-configuration requirements' and 'business language' with 'investment-team language' to match the repo's actual object of translation (Story 3: 'translated dev pushback back into investment language'), not generic capital-markets-ops language.
- Section heading 'Change Delivery & Process Implementation' -> 'Change Delivery, Implementation & Readiness' to pick up the JD's explicit 'Readiness' accountability theme -- justified because the shadow-mode/reconcile/rollback-plan bullet is itself a readiness-validation activity, so the heading change reflects real evidence rather than borrowed vocabulary.
- Section heading 'Testing, Validation & Defect Resolution' -> 'Testing, Validation & Defect Escalation' for the same reason as the core-skill fix above (he escalates and tracks, does not resolve defects himself).

**Cover letter**
- Removed 'sequencing the cutover' from the Calypso-migration paragraph -- 'cutover' and 'documented rollback plan' are evidenced only for the separate Python-pipeline migration (Story 6), and had been misattributed to the Calypso/PFaroe client migration in the draft. The cutover/rollback claim is preserved, correctly, in paragraph 2 where it belongs.
- Replaced 'scoping operational requirements' with 'scoping client and platform-configuration requirements' for the same JD-noun-import reason as above.
- Softened 'That is the shape of the work the ... role describes' to 'That delivery mechanic ... is close to the shape of work this ... role describes' -- avoids overstating equivalence between platform/vendor-migration delivery and hands-on capital-markets trade-operations change management.
- Retained the explicit gap disclosure ('My product depth is in derivatives ... rather than clearing, confirmations, or collateral operations') -- this is an honest, direct disclosure rather than a claim, and is the right call for a role this far outside the primary/secondary positioning.

## Residual gaps to own in interview (do not paper over)
- No hands-on Capital Markets Operations experience: no clearing, confirmations, settlements, collateral management/funding, asset servicing/corporate actions, middle-office trade support (PnL, trade lifecycle), futures & options clearing, or prime services/securities lending. Every JD bullet in the 'hands-on operational areas' list is unevidenced in the repo -- own this directly rather than imply adjacency.
- No UAT-tooling or formal defect-tracking-system experience (e.g., JIRA/HP ALM-style test management); Saber's 'testing' is model-output reconciliation and shadow-mode parallel runs, not UAT test-case execution against a defect log. Be ready to draw that distinction unprompted.
- Of the JD's named systems (Global One, Loan One, Equilend, Colline, Anvil, Broadridge, ION, Murex, Calypso, Fidessa, Sophis, Wall Street), only Calypso overlaps -- and only as the platform clients were migrated *off of*, not as an operations end-user. Do not let PFaroe be conflated with a capital-markets trading/ops system in conversation; it is a buy-side ALM/portfolio-analytics platform.
- This role sits outside Saber's primary (ALM/IRRBB/Model Governance) and secondary (Vendor-Platform/Client Solutions) positioning per the master repo's role-angle taxonomy. Application is a legitimate stretch on transferable change-delivery and platform-migration mechanics, not a core-fit application -- calibrate enthusiasm and comp expectations accordingly, and expect the interview to probe the domain gap early.