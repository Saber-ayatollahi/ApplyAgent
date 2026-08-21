# Interview Brief — RBC, Director, Operational Risk Governance (Global Security)

## 5 most likely technical/behavioural questions

**1. "This role sits in Global Security. You have no information-security background — why you?"**
Be direct, then pivot to portability. The governance machinery I run at Moody's — framework design, independent review and challenge, documentation and benchmarking standards, escalation protocols, committee reporting — is domain-agnostic; what changes is the risk taxonomy, not the control architecture. My track record on domain switching is evidenced (chemical engineering → financial modelling MSc → ALM advisory → model governance + CFA in 2024), each transition made deliberately, not accidentally. I would expect to spend my first 90 days learning the security risk taxonomy from the SMEs while immediately upgrading how controls are documented, tested, escalated, and reported.

**2. "Walk me through a control framework you designed and implemented." (STAR 6)**
A Moody's valuation workflow was spreadsheet-driven with limited logging and no versioning — not acceptable under model-governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line-by-line, and cut over with a documented rollback plan. The governance audit closed satisfactorily and the pipeline became the template for adjacent workflows. Key point for the panel: the control was designed so it could be *tested and evidenced*, not just asserted.

**3. "Tell me about a risk event you escalated under pressure." (STAR 2)**
A client-delivery run produced portfolio sensitivities that passed every internal check but contradicted economic intuition under a specific rate shock. Under deadline pressure I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case (short-end inversion handling), and escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was fixed upstream and captured in permanent validation tests. I became that Head of Risk's direct escalation contact.

**4. "How do you influence and coordinate across functions when you have no direct authority?" (STAR 5)**
At EY, a Canadian insurer's IFRS 17 program had finance, actuarial, and IT out of sync on data sourcing and CSM mechanics. I built shared requirements documentation, walked each function through the *other* functions' constraints, then isolated the three decisions that genuinely needed executive sign-off and escalated only those. The milestone was hit and the documentation was reused on later engagements. The transferable method: make constraints visible, minimize the number of items you escalate, and escalate them cleanly.

**5. "How do you identify, quantify, and prioritize risks across a complex environment?"**
Two evidenced approaches. At Ortec I ran asset-only and surplus optimization on VaR and CVaR through the GLASS platform, with risk decomposition and contribution-to-risk attribution so clients could see which exposures actually drove tail outcomes, plus near-optimal frontier analysis to test whether the recommendation was robust or knife-edge. At Moody's I led the design of a multi-scenario engine covering base, stress, and reverse-stress conditions with time-bucketed analytics from T+1 to multi-year. Prioritization comes from attribution, not from a heat map colour.

## 3 sharp questions to ask

1. "Where does this role sit relative to the Global Security first line — is the mandate to challenge and govern the security organization's controls, or to build and run the control framework inside it? The escalation path differs a lot between those two."
2. "Which of the enterprise-wide initiatives in flight is furthest behind, and what does 'on time' actually mean for it — a regulatory commitment date, an internal audit finding closure, or an internal roadmap?"
3. "How is AI-driven and automated risk monitoring being scoped here — as tooling the team consumes, or as something this role is expected to design? And where does that intersect with OSFI E-23's coverage of AI/ML models?"

## The one competency gap to prepare for

**Operational-risk-specific machinery: RCSA, KRIs, loss-event data collection, operational risk taxonomy, FINTRAC/AML obligations, and RBC's risk appetite statement cascade — plus the security domain itself (IT security architecture, information security management).** None of this is in the evidenced record and none of it is on the resume. Before the interview: read the Basel Principles for the Sound Management of Operational Risk, RBC's public risk-appetite and enterprise risk framework disclosures in the annual report, and be ready to say plainly, "I have run three-lines-of-defence-style independent review and challenge in model risk; I have not personally run an RCSA cycle, and I would want the first quarter to learn how yours is scoped." Honest naming of the gap plus a concrete learning plan beats bluffing — and the panel will test it.