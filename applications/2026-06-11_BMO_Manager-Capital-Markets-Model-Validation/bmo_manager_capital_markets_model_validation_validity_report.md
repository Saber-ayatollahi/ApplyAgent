## Validity Report — Adversarial Audit

### JD Core Themes (used as the relevance anchor)
1. Independent model validation and effective challenge (assumptions, benchmarks, documentation, replicability)
2. Model risk quantification, deficiency identification, escalation, and conditions-for-use documentation
3. Governance: model inventory, sign-off records, regulatory/audit representation
4. Capital markets / derivatives scope (the specific instrument domain)
5. Stakeholder communication and cross-functional influence

---

### Changes Made

#### Summary
- **Deleted** 'capital markets analytics' from the opening phrase. The repo does not support Saber having a capital-markets (sell-side trading book) background; the phrase was JD-imported. Replaced with 'derivatives analytics, balance-sheet risk, and ALM modelling' — all repo-supported.
- The remainder of the summary was clean and retained unchanged.

#### Core Skills
- **Changed** 'Derivatives Valuation (Rates, FX, Inflation)' → 'Derivatives Valuation Review (Rates, FX, Inflation)'. The repo supports *reviewing and validating* derivatives outputs, not primary derivatives pricing/valuation as a developer. Adding 'Review' scopes the claim truthfully and matches the JD's validation frame.
- **Changed** 'Model Documentation & Inventory Reporting' → 'Model Documentation & Governance Reporting'. 'Inventory Reporting' is a JD phrase (model inventory attestations) but the repo does not evidence Saber maintaining a model inventory; 'Governance Reporting' is supported by the governance-framework operation described in the Moody's bullets.
- **Changed** 'Stakeholder Engagement & Governance Reporting' → 'Stakeholder Engagement & Escalation'. The original listed 'Governance Reporting' twice in effect; 'Escalation' is distinctly repo-supported (escalating economically indefensible outputs to Heads of Risk) and directly maps to the JD's escalation accountability.
- All other core skills retained — each is grounded in repo §4.3, §4.8, §4.1, and §4.2.

#### Moody's — Phase 2 bullets, Section 1 ('Independent Validation & Effective Challenge')
- Bullet 1: No change — fully repo-supported and phrasing matches §5 tagged bullets exactly.
- Bullet 2: No change — repo-supported ('Validated derivatives pricing outputs across rates, FX, and inflation — ensured consistency of sensitivities and scenario impacts at portfolio-level ALM aggregates'). 'Against developer results for replicability' language added in original draft is a light JD echo but is logically implied by the repo's cross-checking description and is not a fabricated claim.
- Bullet 3: No change — 'escalates outputs lacking mathematical or economic defensibility' is verbatim from repo §3.1 Phase 2. 'Documents conditions for use' was in the draft — this is a model-governance documentation function repo-supported by the SR 11-7/E-23 framework bullet; retained.

#### Moody's — Phase 2 bullets, Section 2 ('Stress Testing, Benchmarks & Methodology')
- **Heading changed**: Original heading 'Stress Testing, Benchmarks & Methodology' → 'Stress Testing, Benchmarks & Methodology Review'. The JD's accountability is reviewing/challenging methodology, not developing it; the heading now reflects that accurately.
- **Bullet 1 verb downgraded**: Original said 'Oversees interest-rate and duration analytics under parallel and non-parallel rate shocks, applying frameworks analogous to Basel IRRBB and OSFI B-12 to benchmark and challenge model outputs.' Changed to 'Reviews interest-rate and duration analytics under parallel and non-parallel rate shocks, benchmarking model outputs against expected behaviour to identify deficiencies and recommend methodology changes.' Reason: (a) 'Oversees' implies managerial authority over a team doing this work — the repo says Saber personally performs this review, not that they manage others doing it. (b) 'Applying frameworks analogous to Basel IRRBB and OSFI B-12' is a JD-adjacent regulatory-name drop that is not a capital-markets-model-validation vocabulary word; the JD does not mention IRRBB or B-12 at all. Removed to avoid irrelevant vocabulary in a prime slot (Rule 6 — relevance). The factual substance (parallel/non-parallel rate shock review, benchmarking, deficiency identification) is retained and maps to JD accountability.
- **Bullet 2 verb downgraded**: Original said 'Led design of an enterprise multi-asset cash-flow projection engine supporting base, stress, and reverse-stress scenarios — embedded behavioral assumptions, prepayment logic, and macro stress overlays.' The repo describes this as 'Led design and implementation' but in the context of a MODEL VALIDATION resume, claiming full design/build authorship on a cash-flow engine is an overclaim relative to the validation frame the JD requires, and could also mislead interviewers about Saber's role (the repo Phase 2 context is that this was a Moody's internal modelling-services function, not a bank's in-house validation unit). Changed to 'Contributed to the design of an enterprise multi-asset cash-flow projection engine... — reviewed and validated embedded behavioral assumptions, prepayment logic, and macro stress overlays for analytical defensibility.' This is still truthful (Saber did contribute to design and did validate those components) but correctly foregrounds the validation activity that the JD cares about. 'Led design' is preserved in repo for ALM-primary resumes where it is the right frame.
- Bullet 3: No change — repo-supported ('Reviews aggregation logic converting security-level exposures into portfolio-level risk metrics').

#### Moody's — Phase 2 bullets, Section 3 ('Governance, Documentation & Stakeholder Reporting')
- **Heading retained** — directly maps to JD accountability themes 3 and 5.
- Bullet 1 (SR 11-7/E-23): No change — repo-supported.
- Bullet 2 (Python/AI): No change — repo-supported; 'estimated 30–40%' qualifier preserved as repo requires.
- Bullet 3: Minor change — removed 'balance-sheet sensitivities' (ALM/IRRBB vocabulary not requested by this JD) → replaced with 'model outputs, scenario impacts, and sensitivity results' which is more accurately framed for a model-validation context. The substance is repo-supported.

#### EY and Ortec bullets
- All bullets retained unchanged — each traces directly to §5 tagged bullets or §3.2/§3.3 experience. No fabrications detected in these sections.

#### Cover Letter
- **Opening paragraph**: The original draft placed the cover letter in the 'cover_letter' field as a honesty-note (not a letter). Replaced with a proper 300–350-word, three-paragraph cover letter per the template rules.
- Opening sentence leads with concrete capability claim (sign-off authority, challenge discipline) tied to the BMO role — not a regulatory-calendar narrative. Compliant with cover-letter anti-pattern rules.
- 'Capital markets analytics' from the summary's prior phrasing does NOT appear in the cover letter — the honest framing is 'derivatives pricing outputs across rates, FX, and inflation' which is repo-supported without overclaiming sell-side trading-desk experience.
- Paragraph 2 specifics (SR 11-7/E-23 governance, Python pipelines, Ortec stochastic validation, EY governance documentation) are all repo-traced.
- Paragraph 3 company-specific hook references 'diverse model portfolio, regulatory auditor representation, and validation strategy across new model types' — all drawn from the JD's own language and mapped to Saber's actual sign-off/challenge/documentation evidence. No fabrication.
- Word count: approximately 320 words. Compliant.

---

### Residual Honest Gaps — Own in Interview, Not on Resume

1. **Capital markets = sell-side trading book**: The JD title says 'Capital Markets Model Validation.' In bank MRM, this typically means trading-book models (pricing models for derivatives desks, VaR, PnL explain, potentially FRTB SA/IMA). Saber's derivatives validation is on buy-side/ALM institutional portfolios at Moody's — the methodology is closely related but the institutional context is different. Frame as: 'My derivatives validation experience is on the buy-side institutional side; the pricing mathematics — curve construction, spread calibration, rates/FX/inflation sensitivities — is the same. I am ramping on the sell-side desk-specific nuances and am comfortable doing so.'

2. **No direct FRTB, CCR/PFE/xVA, or VaR backtesting on a trading book**: These are standard capital-markets MRM topics at a Big 6. Saber has analogous stress testing and scenario work but not hands-on trading-book capital machinery. Frame as applied-knowledge and ramp willingness. Do not claim these as capabilities.

3. **Model inventory and inventory attestation**: The JD specifically calls out 'model inventory and model inventory attestations.' Saber's governance work is documented at the sign-off/challenge-memo level but the repo does not evidence formal model-inventory management (maintaining a numbered inventory, attestation cycles). Acknowledge as a process Saber understands from the governance-framework context and is ready to own operationally.

4. **Title level**: BMO is hiring a Manager (5–7 years); Saber is at ~7.3 years and Asst. Director at Moody's. Prepare a credible answer to 'why a lateral move in title?': the honest answer is that a Big 6 bank MRM seat provides institutional capital-markets model scope, regulatory-exam experience, and a career track into Director/VP MRM that is not available on the buy-side vendor side. This is a genuine domain expansion, not a demotion.

5. **'Benchmark & Replication Testing' as a core skill**: Saber cross-checks sensitivity outputs against developer results (repo-supported). Full benchmark model construction (building an independent replication of a pricing model from scratch) is not explicitly evidenced in the repo. If asked in technical interview, scope the answer to 'cross-validation of outputs against developer results and independent sensitivity replication' rather than claiming full independent-model rebuild capability.

6. **'Leads research and development for validation of new model types'** (JD accountability): Saber can speak to leading the cash-flow engine contribution and the stochastic scenario generator work at Ortec as evidence of research-level model development. However the JD implies this in a bank MRM context (new exotic structures, new asset classes being traded). Be ready to address this as 'I have led model-type expansion work in my current context and am prepared to do the same in a bank MRM framework.'