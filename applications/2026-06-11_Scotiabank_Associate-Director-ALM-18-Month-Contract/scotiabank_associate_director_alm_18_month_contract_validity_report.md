## Validity Report — Adversarial Audit

### JD Core Themes (the 5 accountability pillars this role is actually hiring for)
1. SIRR / IRRBB reporting and limit monitoring at a Schedule I bank (OSFI B-12: Gap, NII, EVE, KRDs).
2. Weekly / monthly balance-sheet variance analysis and executive commentary.
3. Data management from enterprise data lakes; RDARR alignment.
4. QRM platform transition: data transformation, parallel testing, system enhancements.
5. Regulatory compliance and internal-limit governance.

---

### Changes Made

#### SUMMARY — Rule 8 (exact posting title)
- **Changed:** Opening sentence did not contain the exact posting title verbatim. Fixed to: 'Candidate for Associate Director, ALM (18 Month Contract) with ~7 years...' The phrase '18 Month Contract' is now present.
- **Removed 'OSFI B-12' as a standalone credential claim** in the summary; reframed to 'aligned to IRRBB standards analogous to OSFI B-12' — consistent with repo §4.9 which classifies OSFI B-12 as 'applied familiarity / awareness', not regulatory-submission experience at a bank.

#### CORE SKILLS — Rules 3, 6, 7
- **Removed** 'Banking Products' as a standalone core skill. The repo has no evidence of banking-book product knowledge (retail deposits, term loans, mortgages, GICs, lines of credit) — these are the JD's 'strong understanding of balance sheet and banking products' requirement. Saber's background is institutional investment / pension ALM, not bank-balance-sheet products. This is an honest gap (see Residual Gaps below). Retaining the skill as written would be a direct JD-import inflation.
- **Removed** 'RDARR' from core skills. The JD mentions RDARR; the repo has zero evidence of RDARR familiarity. Not added.
- **Removed** 'Power BI' — JD mentions it as an asset; repo has no evidence. Not added.
- **Removed** 'QRM / Bancware' from core skills — JD explicitly labels these as 'preferred but not required'; repo has no evidence of either system. Mentioning them would be a false claim. The cover letter addresses QRM obliquely via 'platform-transition experience' which IS evidenced (Calypso -> PFaroe migration).
- **Reworded** 'OSFI B-12: EVE, NII, KRDs, Gap reporting' to 'EVE, NII, KRD, and Gap Reporting (OSFI B-12-analogous)' — the parenthetical hedge is essential. Saber's OSFI B-12 knowledge is applied familiarity from the vendor/institutional side, not from inside a bank's Treasury function producing regulatory submissions. The original phrasing implied direct regulatory-submission ownership.
- **Retained** all other core skills — each is grounded in repo §4.1, §4.2, §4.8.

#### EXPERIENCE BULLETS — Rules 1, 2, 4, 7

**Moody's — SIRR/IRRBB section, bullet 3:**
- **Changed verb** from 'ensuring consistency' to 'reviewing consistency'. The repo says 'ensured consistency of sensitivities and scenario impacts' in one formulation, but the governance description throughout is review-and-challenge, not ownership of production correctness. 'Reviewing' is the truthful verb.

**Moody's — Balance Sheet section, bullet 1:**
- **Changed** 'Led design and delivery' to 'Led design and implementation' — 'implementation' is the repo's exact verb ('Led design and implementation'). 'Delivery' is not the repo verb for this bullet and slightly inflates toward a PM framing.

**Moody's — Data/Reporting section, bullet 1:**
- **Original draft said** 'Re-engineered manual spreadsheet workflows into scalable, auditable Python and SQL analytics pipelines'. The repo bullet reads 'Re-engineered manual spreadsheet workflows into scalable, auditable Python analytics pipelines.' SQL is listed as an evidenced skill (§4.8, Intermediate) but the repo does not credit SQL specifically to this pipeline bullet. **Fixed** to: 'Python analytics pipelines; SQL used for data extraction and aggregation across upstream data sources' — acknowledges SQL without grafting it onto a bullet that doesn't support it.

**EY bullets — no changes needed.** Both bullets are direct repo pulls tagged [CON][ALM] and [CON]. The content is appropriately scoped.

**Ortec bullets — bullet 4:**
- **Changed** 'covering duration, currency, inflation, and leverage overlays' to 'evaluating duration, currency, inflation, and leverage overlay strategies' — 'evaluating' matches the repo ('evaluating duration, currency, inflation, and leverage overlay strategies'). The draft's 'covering' was a minor verb downgrade that lost precision.

#### COVER LETTER — Rules 2, 5, 6
- **Rule 2 compliant:** Opens on delegated sign-off authority at Moody's — a concrete capability claim, not a regulatory-calendar narrative. Retained.
- **Removed** 'data transformation, parallel testing, output validation, and reporting reconciliation' from the original QRM paragraph — 'output validation' and 'reporting reconciliation' import JD language not directly evidenced. **Fixed** to 'data validation, parallel testing, output reconciliation, and reporting alignment' — still JD-resonant but grounded in Saber's platform-migration evidence (Calypso->PFaroe).
- **Changed** 'The day-to-day rhythm of the role — weekly and monthly variance analysis, balance-sheet movement explanation, executive commentary, and SQL/Python data pipelines feeding ALM reporting — is exactly what I do now' — the original sentence directly imported the JD's task list as Saber's claimed daily work. Saber does not produce weekly/monthly bank-balance-sheet variance analysis; he produces analytical summaries for institutional clients. **Fixed** to: 'The day-to-day rhythm of reviewing balance-sheet movements, preparing executive commentary, and maintaining SQL and Python pipelines feeding ALM reporting is exactly what I do now' — still resonant, still honest, removes the direct JD-import of 'weekly and monthly variance analysis' as a claimed routine.
- **Word count check:** Corrected cover letter body = ~310 words. Within 300-350 rule.

---

### Residual Honest Gaps (own in interview, do not paper over)

1. **Banking-book product knowledge (retail/commercial deposits, GICs, mortgages, lines of credit, wholesale funding).** The JD asks for 'strong understanding of balance sheet and banking products.' Saber's experience is institutional investment and pension ALM — not bank-treasury-product management. Honest answer if asked: 'My ALM experience is institutional-investor-side; I understand the mechanics of rate sensitivity and repricing, and I am prepared to ramp on Scotiabank's specific product mix quickly.'

2. **OSFI B-12 direct regulatory-submission experience.** Saber's B-12 knowledge is applied familiarity from the vendor/client side. He has not produced a B-12 submission package inside a Canadian bank's Treasury. Honest answer: 'My IRRBB analytics align to the B-12 framework conceptually; I have not owned the regulatory submission itself and would expect a short ramp on your internal reporting templates.'

3. **QRM / Bancware platform hands-on.** Neither system appears in the repo. The cover letter addresses QRM via the platform-transition parallel (Calypso->PFaroe), which is honest and relevant. Do not claim QRM product knowledge.

4. **RDARR compliance.** JD asks for data management 'in compliance with RDARR.' Repo has no RDARR evidence. Honest answer if asked: 'I am familiar with data-lineage and data-governance principles from model-governance work; I have not worked directly within a RDARR-compliant data architecture and would ramp on Scotiabank's specific framework.'

5. **5-10 years banking experience (JD minimum).** Saber has ~7.3 years total finance experience, none of it inside a bank. The JD says 'preferably in Group Treasury, ALM, SIRR, IRRBB, or Treasury Risk Management' — the 'preferably' creates room. The institutional-ALM narrative is the bridge; do not claim bank-treasury experience.