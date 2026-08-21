## JD core themes (mirror check)
1. Client/BD leadership — pursuits, proposals, C-suite/PE-sponsor advisory, practice growth
2. Engagement economics & delivery management — budgeting, staffing, team leadership, risk management
3. Hands-on technical/analytical depth — SQL, Python/R, statistical modeling, optimization, simulation, BI
4. Enterprise AI solution leadership — Predictive/Generative/Agentic AI, RAG, model lifecycle (validation, monitoring, explainability)
5. Mentoring, thought leadership, reusable assets

The draft correctly avoids claiming themes 1, 2, and the RAG/Predictive-AI/monitoring-explainability slice of theme 4 — none of these are evidenced in the Master Repo. Good restraint; no fixes needed there beyond the cover-letter fix below.

## Fixes made

1. **Unsupported bullet addition (Rule 1 — bullet-library fidelity).** The Moody's escalation bullet had an added clause — 'mentoring junior colleagues on review and documentation standards' — that is not in the tagged bullet library (the source bullet only covers escalation and holding back indefensible outputs). Removed the clause; bullet now matches the library's '[VAL][ALM]' escalation bullet.

2. **Inflated verb (Rule 2).** Governance-committee bullet used 'shaping methodology review... standards' where the repo's own language is 'participates in.' Downgraded to 'contributing to' to match the evidenced level of involvement (member/participant, not standard-setter).

3. **Skill hedge (Rule 3 adjacent / honesty).** 'SQL (PostgreSQL) & R' → 'SQL (PostgreSQL) & R (working knowledge)'. Repo flags R as 'Intermediate — historical use,' and the JD explicitly names R, so an unhedged claim risks a live-coding or tooling-depth question landing badly. Hedged, not removed, since R is genuinely evidenced.

4. **Thin-evidence flag, not removed (Rule 3).** 'Mentoring & Methodology Standards' renamed to 'Methodology Standards & Peer Mentoring.' Repo §4.10 lists 'Mentorship of junior colleagues' as an evidenced skill, so it stays inside the ceiling — but Section 6's STAR bank literally has 'Story 10 — difficult client/mentoring situation' marked '(to fill).' There is no concrete instance backing a formal team-mentoring claim. Keep on the resume as a skill line (permitted), but do not lead with it in interview as 'proven mentoring of managers' — that is the JD's ask, not Saber's evidenced depth. Reframe honestly as informal peer review/coaching during code and validation review.

5. **Cover-letter tenure inflation (Rule 5).** 'nearly four years' for the combined Ortec (~2.5y) + EY (~0.6y) tenure overstates by ~9 months; actual combined tenure is ~3.2 years. Corrected to 'just over three years.'

6. **Cover-letter capability overclaim (Rules 5 & 7 — JD noun import).** Paragraph 3 originally claimed ownership of 'validation, monitoring, and explainability' for AI systems. 'Monitoring' and 'explainability' are JD vocabulary (model lifecycle: validation, monitoring, explainability) with zero repo support — Saber validates and documents, he does not have evidenced AI-model monitoring/explainability tooling experience. Rewrote to 'nobody owns the validation and documentation discipline behind them' — grounded in his actual Moody's governance-committee and escalation work.

## Verified clean (no fix needed)
- No regulatory-framework name-drops (OSFI/IRRBB/Basel/CCAR/SR 11-7) anywhere in resume or cover letter — correctly de-emphasized per the retired/opportunistic framing.
- Exact JD title 'Senior Manager, Analytics Insights' appears verbatim as the resume summary's opening clause (Rule 8) and in the cover letter's ask sentence.
- Section headings ('Analytical Quality Assurance, Governance & Standards' / 'Analytics Solution Design & Data Engineering' / 'AI-Enabled Delivery & Executive Insight') mirror this JD's own accountability language (quality assurance of deliverables, solution design/methodology-setting, AI-enabled delivery) rather than importing ALM/banking-specific groupings.
- No RAG, Predictive AI, budgeting, staffing, or pursuit/proposal claims anywhere — these are real, unaddressed gaps against the JD (see below), correctly left unclaimed rather than fabricated.
- Year framing stays at '~7 years,' consistent with the ~7.3-year rule; no '8+'/'10+' language.
- Sign-off framing ($5-25bn per engagement, ~$50bn cumulative) matches the repo ceiling exactly, no inflation.

## Residual honest gaps to own in the interview
- **No formal team-leadership, staffing, or P&L/budget experience** — the JD wants '5+ years in a leadership role managing teams' and 'engagement economics (planning, budgeting, staffing).' Saber's story is IC-plus-review authority and cross-functional coordination (EY, Ortec, Moody's), not people-management or budget ownership. Be ready to reframe: 'I've owned the technical/quality bar and client relationship, not headcount or P&L — that's the deliberate stretch of this move.'
- **No pursuit/proposal/business-development track record.** Client onboarding (Moody's) and investment-committee presentations (Ortec) are adjacent but not the same as originating pursuits or writing proposals. Own this directly rather than implying BD scope.
- **Mentoring claim is thin.** No STAR story currently backs formal mentoring of managers/teams (Story 10 in the repo is an unfilled placeholder). Fill this before the interview with a real, specific instance, or answer honestly that mentoring so far has been informal (code/validation review), not formal people development.
- **RAG-based systems and Predictive AI are not evidenced.** If asked directly, be candid: hands-on experience is with agentic/generative-AI coding workflows (Claude Code, Cursor), not RAG architectures or predictive-model production deployment.