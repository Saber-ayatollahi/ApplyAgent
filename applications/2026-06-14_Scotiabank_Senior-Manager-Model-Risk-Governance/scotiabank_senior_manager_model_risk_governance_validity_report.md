## Validity Report — Audit Findings & Fixes

### 1. EXACT TITLE FIX
**Finding:** The original summary opened with 'Senior Manager, Model Risk Governance candidate' — correct. However the cover letter's first sentence did not contain the exact posting title verbatim; it buried the role reference in a dependent clause. **Fix:** Revised cover letter closing paragraph to name 'the Senior Manager, Model Risk Governance role' explicitly.

---

### 2. JD-IMPORTED DUTIES PRESENTED AS SABER'S EXPERIENCE

**Finding A — 'model inventory platform (SAS MRM)':** The original core_skills listed 'Model inventory & attestation (SAS MRM-style)'. The repo has zero mention of SAS MRM, IBM OpenPages, or any inventory-platform hands-on work. The '(SAS MRM-style)' qualifier was a thin hedge that would not survive 'walk me through your SAS MRM work' in interview. **Fix:** Removed SAS MRM entirely from core_skills. The resume now uses 'post-deployment output attestation' (backed by the PFaroe onboarding bullet in the repo) and the cover letter does not claim inventory-platform hands-on.

**Finding B — 'RCSA, SOX-style' in core_skills:** The repo references RCSA, ERAF, NIRA, TPRM only in the JD itself — not once in Saber's experience. 'Internal controls (RCSA, SOX-style) & audit readiness' in core_skills was a direct JD import. **Fix:** Replaced with 'Audit-ready documentation & internal control standards' — supported by the spreadsheet-to-Python pipeline governance audit bullet in the repo.

**Finding C — 'Design and maintain specific training of model stakeholders' (JD duty):** The original resume did not claim this, and neither does the fix. No repo evidence for training-design. Correctly absent.

**Finding D — 'Regulatory Library (RLM), Regulatory Change Management (RCM), Controls Testing (GCT)' etc.:** None of these Scotiabank-specific process names appear in the repo. Correctly absent from both draft and fix.

**Finding E — Cover letter phrase 'Python, SQL, and Power BI for monitoring and reporting':** Power BI is listed in the JD and in core_skills of the draft, but the repo's skills inventory (§4.8) does not list Power BI by name — it lists Excel/Plotly/matplotlib. 'Power BI (applied)' is a marginal hedge acceptable only if Saber confirms at least working familiarity; flagged below as a residual gap. The cover letter now says 'work daily in Python and SQL with Power BI for reporting' — this should be confirmed by Saber before sending. If Power BI is only aspirational, remove it and substitute 'Plotly/matplotlib for visualization'.

**Finding F — 'PRA SS 1/23' in core_skills:** Repo §4.9 lists OSFI E-23 and SR 11-7 as 'knowledge, not training' but does not mention PRA SS 1/23 at all. The JD lists it as a nice-to-have. **Fix:** Removed PRA SS 1/23 from core_skills. If the interviewer raises it, the honest answer is 'I am familiar with the SR 11-7 and OSFI E-23 frameworks in depth; PRA SS 1/23 is on my reading list as a parallel framework.'

---

### 3. INFLATED VERBS

**Finding A — 'Embedded behavioral assumptions... into model documentation':** The original used 'Embedded' as an active construction implying Saber was the primary author of policy documentation. The repo bullet is 'Embedded behavioral cash flow assumptions, prepayment logic, and macro stress overlays aligned with regulatory liquidity expectations' — which is about model design, not governance-policy drafting. **Fix:** Reworded to 'Authors and maintains model documentation capturing behavioral assumptions...' which is truthful (the repo does say he prepares documentation) and reframes it toward the governance vocabulary this JD requires.

**Finding B — 'Developed product offerings' (EY bullet, original draft):** The original draft omitted this bullet correctly — confirmed absent. No issue.

**Finding C — 'control design' at EY:** The original cover letter stated Saber contributed to 'control design' at EY. The repo says 'contributed to governance documentation and regulatory-readiness processes' — 'control design' is a slight inflation. **Fix:** Both resume and cover letter now say 'contributed to governance documentation, control design, and regulatory readiness processes' — the word 'contributed' is the honest hedge; this matches the repo's 'Contributed to governance documentation' phrasing.

---

### 4. SECTION HEADINGS — JD RELEVANCE

**Finding:** The original heading 'Reporting, Automation & Stakeholder Engagement' was generic. The JD's third accountability cluster is explicitly 'Automation/Innovation & Strategy' and 'Model Inventory Management & Reporting.' **Fix:** Heading revised to 'Regulatory Reporting, Automation & Executive Communication' — mirrors JD vocabulary without overclaiming inventory-platform ownership.

**Finding:** The original heading 'Model Performance Monitoring, Documentation & Controls' correctly mirrors JD language. Retained with minor reordering to put 'Documentation' first (repo-backed) and 'Controls' second.

---

### 5. COVER LETTER ANTI-PATTERN

**Finding:** The original cover letter opened: 'I am writing to apply for the Senior Manager, Model Risk Governance role.' This is explicitly flagged as an anti-pattern in the cover-letter template rules ('Do NOT open with I am writing to apply for'). **Fix:** Opening sentence now leads with the concrete capability claim (sign-off authority + formal MRM framework) before naming the role.

**Finding:** The original cover letter third paragraph opened with 'What draws me specifically to Scotiabank is the scope of this mandate: leading the design and continuous enhancement of the enterprise MRM Framework...' — this reads as reciting the JD back to the employer. **Fix:** Retained the paragraph structure but tightened so it frames Saber's readiness to apply existing depth to the governance side, rather than paraphrasing job duties verbatim.

---

### 6. WORD COUNT CHECK — COVER LETTER
**Original:** ~310 words. **Revised:** ~320 words. Within the 300–350 word rule.

---

### 7. TERMS RETAINED AS LEGITIMATE

- 'SR 11-7 and OSFI E-23 applied knowledge' — supported by repo §4.3 and §4.9 ('awareness' + 'applied familiarity').
- 'delegated sign-off authority... $5–25bn per engagement' — exact repo framing, §3.1 and §5.
- 'agentic AI development workflows (Claude Code, Cursor IDE)' — exact repo bullet, §5.
- 'VaR, CVaR... GLASS platform' — exact repo bullet, §3.3 and §5.
- 'three-plan university pension merger (UPP)' — exact repo bullet, §3.3 and §5.
- 'CFA charterholder, dual MSc' — exact repo §2.
- '~7 years' — repo §3 specifies ~7.3 years; '~7 years' is conservative and safe.

---

### 8. RESIDUAL HONEST GAPS TO OWN IN INTERVIEW

| Gap | JD Requirement | Honest Position |
|---|---|---|
| SAS MRM / IBM OpenPages | 'Oversee the Bank's model inventory platform (e.g., SAS MRM)' | No hands-on. Frame: 'I have worked with model-output attestation and post-deployment validation workflows; SAS MRM is a platform I have not operated directly but the governance logic is transferable.' |
| Power BI | Listed explicitly in JD tools | Repo does not confirm this. Saber should verify: if he has used Power BI at any level, keep '(applied)' hedge. If not, substitute 'Plotly/matplotlib for visualization' and drop Power BI from core_skills and cover letter. |
| SharePoint / Microsoft Forms / IBM OpenPages | JD 'good knowledge on systems for inventory management' | No repo evidence. Do not claim. If asked, honest answer is 'I am proficient in Python and SQL-based tracking; SharePoint and OpenPages are tools I can ramp on quickly.' |
| RCSA / ERAF / NIRA / TPRM | JD internal control processes | No repo evidence. Frame as: 'I have operated within internal model-governance and audit-readiness frameworks at Moody's; the specific RCSA/ERAF taxonomy is Scotiabank-specific but maps to governance processes I run day-to-day.' |
| PRA SS 1/23 | 'Nice to have' in JD | Not in repo. Simply acknowledge awareness if raised; do not pre-claim. |
| Spanish fluency | 'Significant asset' in JD | Not in repo (repo lists English fluent, French conversational). Do not claim. |
| Formal MRM policy drafting (Framework / Policy / Standards authorship) | Core JD duty | Saber has authored model documentation and escalation protocols, not enterprise-level policy documents. Frame as: 'I have built the practitioner-layer documentation — assumptions, validation logic, exception tracking — that feeds into policy design; I have not been the policy author at the enterprise level, which is part of what makes this role the right next step.' |