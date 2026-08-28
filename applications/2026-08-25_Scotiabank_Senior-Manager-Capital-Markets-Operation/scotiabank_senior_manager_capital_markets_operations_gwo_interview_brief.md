## Likely technical / role questions

**1. "Walk me through the Calypso-to-PFaroe migration. How did you scope it and how did you get it live?"**
Use STAR Story 3. Client investment-desk requirements were being lost in translation to the dev team and delaying onboarding; I structured them into Product Owner requests, walked the PO through the investment team's decision logic, and translated dev pushback back into investment language. All assigned accounts migrated, outputs were validated post-deployment, and the configuration pattern was reused for the rest of the cohort. Emphasise that scope discipline (what is configuration vs. what is a build) was the lever.

**2. "How would you structure a test approach for a new operations platform release?"**
Anchor on STAR Story 6: parallel-build, shadow-run for two cycles, reconcile old vs. new output line by line, cut over with a rollback plan. Coverage is driven by business scenarios that clients actually run, not by code paths. Be explicit that I have done this as output/model validation and reconciliation rather than as a formal UAT lead — and that the discipline transfers directly to defect logging, triage, and sign-off criteria.

**3. "Tell me about a time you held or delayed a go-live."**
STAR Story 2. Portfolio-level sensitivities passed every internal check but did not square with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, found a short-end-inversion curve-calibration edge case, escalated to product owners and the client's Head of Risk, and walked through remediation. 48-hour delay; client avoided acting on wrong numbers; the case became a standing validation test. I became their direct escalation contact.

**4. "How do you manage dependencies across Technology, Risk, Compliance and Operations?"**
STAR Story 5 (EY IFRS 17). Finance, actuarial, and IT were out of sync on data sourcing and CSM mechanics. I built shared requirements documentation, walked each function through the other functions' constraints, isolated the three decisions that needed executive sign-off, and escalated them cleanly. Milestone was hit and the documentation was reused on later engagements. The transferable point: dependencies fail at the seams, so document the seams first.

**5. "What capital markets products do you actually know?"**
Be precise, not expansive. Direct depth: rates, FX and inflation derivatives valuation and sensitivity validation; fixed income and yield-curve construction/spread calibration; portfolio-level aggregation from security level. Ortec added multi-currency and inflation hedging analysis and actuarial liabilities. Do not claim CDS, NDFs, structured products, repo mechanics, clearing or settlement operations as hands-on.

## Three questions to ask

1. "Which change initiatives are already in the GWO book for the next 12 months — regulatory-driven, platform-replacement, or process consolidation? Where does this seat sit on that mix?"
2. "When operational readiness says 'not ready' and the program plan says 'go', who actually holds the go/no-go pen in GWO — and how often has it been exercised?"
3. "What does the current split look like between build partners in Technology and the operations teams accepting the change? Where does hand-off usually break down today?"

## The one competency gap to prepare for

**Capital markets back- and middle-office domain fluency.** Every named operational area in the JD — OTC clearing/confirmations/settlements, collateral management, corporate actions, middle-office PnL and trade support, F&O clearing, securities lending — is outside my direct experience, as are the named ops platforms (Global One, Colline, Equilend, Broadridge, ION, Murex, Fidessa). Prepare a 60-second, non-defensive answer: (a) name the gap first, (b) show the adjacent asset: I have validated the valuation and sensitivity layer that sits directly downstream of those flows, and I have migrated clients off Calypso, (c) commit to a concrete 90-day ramp — sit with each ops function, map the trade lifecycle end-to-end, and re-derive the control points myself before proposing anything. Before the interview, read up on the confirmations/settlement lifecycle and collateral margin call flow well enough to ask an intelligent question, not to claim experience.