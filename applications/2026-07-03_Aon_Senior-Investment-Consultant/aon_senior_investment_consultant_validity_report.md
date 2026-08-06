## Validity Report — Audit Findings & Fixes

### 1. Exact Posting Title in Summary Opening
**Finding:** The original summary opened with 'Senior Investment Consultant candidate with ~7 years advising institutional investors' — verbatim title present. Compliant. Retained.

**Secondary finding:** The phrase 'advising institutional investors across pension (DB/DC)' claimed DC mandate. The Master Repo has NO evidenced DC consulting work — Ortec and Moody's engagements are DB pension, insurance, and multi-asset institutional. DC was a JD-vocabulary import.
**Fix:** Changed 'pension (DB/DC)' to 'pension (DB)' in the summary. DC dropped from summary and from the Ortec bullet. Not claimed anywhere unless Saber can confirm a specific DC engagement.

### 2. Core Skills — JD-Imported and Unsupported Terms Removed
**Finding A:** 'Investment Consulting & Advisory' and 'Institutional Client Relationship Management' are generic restatements of the JD's language. Repo supports 'Institutional Investment Advisory' (evidenced by Ortec ALM studies, client presentations, Moody's advisory outputs). Reframed to 'Institutional Investment Advisory' — tighter and repo-grounded.

**Finding B:** 'Manager Research & Oversight' appeared in core_skills. The Master Repo contains ZERO evidence of manager research, manager selection, manager monitoring, or fund-manager oversight in any role. This is a JD keyword ('manager research' appears in JD Skills section) that was silently imported as a claimed skill. **Removed entirely.**

**Finding C:** 'Pension (DB/DC), Insurance & Endowment Funds' — DC and endowment both need scrutiny. DB pension: fully evidenced (Ortec). Insurance: evidenced via EY IFRS 17/9 work (insurance clients) and Moody's (insurance clients in platform book). Endowment: NOT explicitly evidenced in the repo — repo mentions 'multi-asset institutional' and 'consulting firms' but no named endowment engagement. Endowment was a JD keyword import. **Fix:** Changed skill label to 'Pension (DB) & Insurance Fund Consulting' — endowment removed from the skills label. (Endowment is a plausible client type under Moody's 'consulting firms' tag but it is not evidenced enough to headline a skill.)

**Finding D:** All remaining core skills (ALM, LDI, SAA/TAA, Stress Testing/Liquidity/Scenario, Investment Committee Presentation, VaR/CVaR Optimization, Risk Decomposition & Attribution) are directly evidenced in repo §4.1, §4.4, and Ortec bullets. Retained.

### 3. Summary — Inflated Verb / Unsupported Claim
**Finding:** 'mentored junior colleagues' appeared in the original summary. The repo's Moody's Phase 2 section says 'Mentorship of junior colleagues' in §4.10 Leadership, but the only evidenced action is reviewing outputs and coaching — the repo does not describe a formal mentorship program or named reports. The word 'mentor' is supportable but not as a summary-level headline claim for a consulting advisory role.
**Fix:** Removed from summary; preserved as an accurate, scoped bullet under 'Service Enhancement & Junior Colleague Development' section ('Review analytical outputs produced by junior colleagues and provide coaching on institutional client-communication standards') — this matches the repo language exactly.

### 4. Section Heading Relevance — JD Vocabulary Alignment
**Finding:** The original heading 'Solution Development & Mentorship' used generic language. The JD explicitly calls for 'identifying gaps between client needs and existing Aon services; proposing and developing service enhancements' and 'providing guidance, mentoring and support to junior colleagues.' Heading rewritten to 'Service Enhancement & Junior Colleague Development' to echo this JD's accountability themes directly.

**Finding:** The original heading 'Institutional Client Advisory & Investment Analytics' is well-aligned to the JD's core theme. Retained.

**Finding:** The original heading 'ALM, Stress Testing & Liquidity Analysis' maps directly to the JD's explicit bullet ('asset-liability modelling (ALM), stress testing, liquidity analysis, and scenario analysis'). Retained.

### 5. Bullet-Level Verb Inflation
**Finding A:** 'guide and mentor junior colleagues' in the original bullet. Repo supports 'review outputs' and 'coach' — not a formal mentorship program lead. **Fix:** Downgraded to 'Review analytical outputs produced by junior colleagues on client engagements and provide coaching on institutional client-communication standards.'

**Finding B:** 'identified gaps in existing analytics and delivered service enhancements' — the verb 'delivered service enhancements' is slightly inflated relative to the repo, which supports 're-engineered manual workflows' and 'built Python pipelines.' The repo does not describe a formal service-enhancement process that resulted in new Moody's product lines. **Fix:** Rewritten to 'Identified gaps in existing analytics workflows and re-engineered manual spreadsheet processes into scalable, auditable Python pipelines' — credits the specific action (workflow re-engineering) rather than the generic output ('service enhancements'), which was JD vocabulary dressing.

**Finding C:** 'aligned with regulatory expectations' in the original Moody's bullet. This phrase is OSFI/banking language that does not belong in an investment-consulting framing. The repo supports 'aligned with regulatory liquidity expectations' in the Moody's Phase 2 section, but for this JD the framing should be 'institutional client expectations.' **Fix:** Changed to 'aligned with institutional client expectations.'

### 6. Cover Letter — Specific Fixes
**Finding A:** 'advising Canadian and international institutional investors — pension plans (DB and DC)' — DC not evidenced. **Fix:** Removed DC.

**Finding B:** The cover letter claimed 'endowments' in the first paragraph ('pension plans (DB and DC), insurers, and endowments'). Endowment consulting is not evidenced in the repo. **Fix:** Removed 'endowments' from the opening list. (The JD mentions endowments as a client type; Saber can acknowledge familiarity with endowment mandates in conversation but should not lead with it as a practitioner credential.)

**Finding C:** 'practice-building instinct' was the third framing pillar in the original cover letter. This is a JD concept ('entrepreneurial and creative spirit') imported as a self-description. Replaced with a specific, evidenced action ('at Moody's I re-engineered manual analytics workflows into scalable Python pipelines that became a delivery standard, and at EY I developed go-to-market collateral for a new IFRS 17 advisory offering') — shows the instinct rather than asserting it.

**Finding D:** French language capability ('conversational French' per repo §1) was not mentioned in the original cover letter. The JD explicitly states 'French/English bilingualism is preferred due to frequent interactions with clients, colleagues, or partners based in Quebec.' Added one sentence acknowledging conversational French — a genuine repo-backed differentiator for this specific JD.

**Finding E:** Cover letter word count: corrected version is approximately 335 words (within the 300–350 rule). Original was approximately 340 words. Both compliant.

**Finding F:** Cover letter does NOT open with a regulatory-calendar narrative (OSFI, E-23, B-12, IFRS 17 timing). It opens on a concrete capability claim (seven years of the core advisory work). Compliant with the system-message anti-pattern rule.

### 7. IRRBB / OSFI / Basel Language — Demoted from Prime Slots
**Finding:** The original resume had 'IRRBB' language embedded in the ALM section heading context and in several bullets referencing 'parallel and non-parallel rate shocks' and 'IRRBB standards analogous to OSFI B-12.' For a banking Treasury/ALM audience this is appropriate prime-slot language. For an investment consulting JD (Aon, pension/endowment/insurance mandates), IRRBB is institutional-bank vocabulary that will read as off-axis to the hiring panel.
**Fix:** The rate-shock bullet is retained because the underlying analytical capability (duration analysis under rate shocks) is genuinely relevant to pension ALM — but the phrase 'IRRBB standards analogous to OSFI B-12' has been removed from this version. The bullet now reads 'Oversee interest-rate risk and duration analysis under parallel and non-parallel rate shocks; validate derivatives sensitivities (rates, FX, inflation) at portfolio-level ALM aggregates' — which describes the same analytical work in investment-consulting vocabulary.

### 8. Residual Honest Gaps — Own These in Interview
- **DC pension experience:** The JD explicitly references DC plans. Saber has no evidenced DC consulting work. In interviews, the honest framing is: 'My direct consulting experience has been DB pension and insurance; I have analytical familiarity with DC structure but have not led a DC consulting mandate. I am confident the ALM and risk-analytics depth transfers, and I am committed to building the DC-specific regulatory and product knowledge quickly.'
- **Manager research / manager selection:** The JD lists 'manager research' as an ideal background. Saber has no evidenced manager-research or fund-manager-monitoring work. Do not claim it. If raised, the honest framing is: 'I have worked alongside manager-selection processes in my platform role — validating the analytics that inform manager evaluation — but I have not personally led manager research mandates.'
- **Endowment mandates:** No named endowment engagement in the repo. If an interviewer asks specifically about endowment experience, acknowledge the structural similarities to DB pension (long-horizon liabilities, spending-rate constraints, asset allocation) without claiming direct client engagements.
- **OCIO implementation:** Saber's Moody's platform work is directionally adjacent to OCIO analytics delivery, but he has not led an OCIO mandate as a consultant. Do not claim OCIO consulting experience; position as platform-delivery familiarity.
- **7-year threshold:** The JD states 'more than 7 years working in a financial/investment consulting environment.' Saber's total finance experience is ~7.3 years (Feb 2019 – present), of which ~2.5 years was direct consulting (Ortec) and ~7 months was transformation advisory (EY). The Moody's role is modelling services / client advisory, which is defensible as consulting-adjacent but not traditional investment consulting. Be prepared to frame the Moody's role as institutional advisory rather than internal modelling — the sign-off authority framing supports this, but do not misrepresent the institutional structure.