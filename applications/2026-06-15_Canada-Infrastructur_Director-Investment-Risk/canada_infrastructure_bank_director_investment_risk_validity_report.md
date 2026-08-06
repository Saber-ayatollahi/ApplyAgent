## Validity Report — Adversarial Audit

### Audit Scope
Every summary sentence, core_skill entry, section heading, and bullet was tested against: (a) the Master Repository as ceiling on claims; (b) the JD keyword list as the relevance target; (c) the seven named audit rules.

---

### Changes Made

**Rule 8 — Exact posting title in summary opening**
The original summary opened with 'Director, Investment Risk candidate with ~7 years across multi-asset institutional risk analytics'. The word 'institutional' before 'risk analytics' is accurate but slightly vague. The fix retains the phrase and confirms the exact title 'Director, Investment Risk' appears verbatim in sentence one. No inflation introduced.

**Rule 6 — Prime-slot relevance: section headings**
Original Moody's Phase 2 heading 1 was 'Multi-Asset Investment Risk Measurement & Oversight'. This was correct but had a redundant 'Multi-Asset' prefix that echoed a generic platform framing. Trimmed to 'Investment Risk Measurement & Oversight' to echo the JD's own accountability vocabulary directly. The other two headings ('Scenario Analysis, Stress Testing & Cash-Flow Projection' and 'Analytics Engineering & Stakeholder Reporting') map cleanly to the JD's scenario/stress and Python/modelling themes — retained unchanged.

**Rule 6 — IRRBB / OSFI B-12 / Basel vocabulary absent from prime slots**
Audit confirmed: no IRRBB, OSFI B-12, or Basel language appears in the summary, core_skills, or section headings of this draft. This is correct for a CIB investment-risk JD. ALM is retained in the summary only as an adjective qualifying the sign-off authority context ('valuation, sensitivity, and ALM outputs'), which is repo-supported and not misleading in an investment-risk context. No change needed.

**Rule 7 — JD-keyword imports not evidenced in repo**
Cross-checked every core_skill noun and every tool/process-domain in the draft against the Master Repository:
- 'Investment Risk Measurement & Oversight': evidenced (Moody's sign-off, Ortec GLASS mandates). RETAINED.
- 'VaR & CVaR Portfolio Optimization': evidenced explicitly (Ortec §3.3, §5 tagged bullets). RETAINED.
- 'Risk Decomposition & Attribution': evidenced explicitly (Ortec §3.3, §4.4, §5). RETAINED.
- 'Scenario Analysis & Stress Testing': evidenced (Moody's cash-flow engine, Ortec stochastic generators). RETAINED.
- 'Multi-Asset Sensitivity Analytics': evidenced (Moody's derivatives validation, portfolio-level aggregates). RETAINED.
- 'Stochastic & Monte Carlo Modelling': evidenced (Ortec scenario generators §3.3, §4.7). RETAINED.
- 'Liability-Driven Investment (LDI)': evidenced explicitly (Ortec §3.3, §4.1, §5). RETAINED.
- 'Python, SQL, Advanced Excel': Python evidenced (§4.8 Advanced); SQL evidenced (§4.8 Intermediate); Excel evidenced (§4.8 Advanced). RETAINED.
- 'CFA · Dual MSc Quant Foundation': credential facts from §2. RETAINED.
No JD-imported nouns found without repo backing. No removals required on this axis.

**Rule 2 — Inflated verbs**
All bullets reviewed against repo verbs:
- 'Led design and implementation of an enterprise multi-asset cash-flow projection engine' — repo §3.1 Phase 2 states 'Led design and implementation of an enterprise multi-asset cash flow projection engine'. Exact repo language. RETAINED.
- 'Architected configurable time-bucketed liquidity-gap analytics' — repo §3.1 Phase 2 states 'Architected configurable time-bucketed liquidity gap analytics'. Exact repo language. RETAINED.
- 'Built and interpreted stochastic economic scenario generators' — repo §3.3 states 'Built and interpreted stochastic economic scenario generators'. Exact repo language. RETAINED.
- 'Performed asset-only and asset-liability (surplus) portfolio optimization' — repo §3.3 states 'Performed portfolio optimization — both asset-only and asset-liability (surplus)'. RETAINED.
No verb inflation found. All verbs match or are conservative relative to repo.

**Rule 1 — All bullets traceable to tagged library (§5)**
Every bullet was traced:
- Moody's sign-off bullet → tagged [ALM][VAL] bullet in §5. CONFIRMED.
- Curve construction / escalation bullet → [VAL][ALM] escalation bullet in §5. CONFIRMED.
- Derivatives validation bullet → [QUANT][ALM] bullet in §5. CONFIRMED.
- Cash-flow projection engine → [ALM] bullet in §5. CONFIRMED.
- Time-bucketed liquidity-gap analytics → [ALM] bullet in §5. CONFIRMED.
- Behavioral assumptions / macro overlays → [ALM][VAL] embedded behavioral bullet in §5. CONFIRMED.
- Python pipelines → [VEN] re-engineered spreadsheet bullet in §5. CONFIRMED.
- Agentic AI workflows → [VEN][AI] bullet in §5. CONFIRMED.
- Investment-committee narratives → [ALM][VEN] analytical summaries bullet in §5. CONFIRMED.
- PFaroe onboarding → [VEN] onboarding bullet in §5. CONFIRMED.
- Technical liaison / PO scoping → [VEN] migration bullet in §5. CONFIRMED.
- Calypso migration → [VEN] migration bullet in §5. CONFIRMED.
- EY bullets → [CON][ALM] and [CON] bullets in §5. CONFIRMED.
- Ortec VaR/CVaR optimization → [QUANT][ALM] GLASS bullet in §5. CONFIRMED.
- Ortec stochastic generators → [ALM][QUANT] bullet in §5. CONFIRMED.
- Ortec ALM/LDI / SAA/TAA → [ALM][CON] bullets in §5. CONFIRMED.
- Ortec cash-flow / hedging / actuarial → [ALM][QUANT] and [ALM] bullets in §5. CONFIRMED.
- Ortec investment committee / UPP → [CON] and [ALM][QUANT] bullets in §5. CONFIRMED.
All bullets confirmed traceable. No invented accomplishments.

**Rule 3 — Skills/tools not grounded in repo**
All nine core_skill entries confirmed against §4. No removal required.

**Rule 4 — Named regulations claimed as capability**
No CCAR, FRTB, Basel, OSFI B-12, or OSFI E-23 appear in core_skills or section headings. 'IRRBB' appears only in the summary as 'ALM outputs' context tied to the sign-off authority framing — not claimed as standalone expertise in the prime slots. Consistent with repo §4.1 which lists OSFI B-12 as 'awareness and applied familiarity'. No flags.

**Rule 5 — Cover-letter claims not supported by resume/repo**
Original cover letter opened: 'I am applying for the Director, Investment Risk role at the Canada Infrastructure Bank.' This is a textbook anti-pattern per the cover-letter template rules ('never open with I am writing to apply for'). FIXED: opening rewritten to lead with the concrete capability claim (sign-off authority) and name the exact posting title by sentence two.
All other cover-letter factual claims traced to repo and resume. No inflation found.

**Cover-letter word count**
Corrected cover letter body: approximately 310 words (within 300–350 target). Confirmed.

**Cover-letter paragraph structure**
Paragraph 1: Concrete capability claim tied to employer/role. Paragraph 2: Practitioner depth (Ortec VaR/CVaR/LDI + Moody's cash-flow/Python). Paragraph 3: CIB-specific hook + availability. Three paragraphs confirmed.

---

### Residual Honest Gaps — Own in Interview

1. **Infrastructure asset class**: Saber has zero direct infrastructure investment exposure. The cover letter correctly names this as 'the learning curve I am most motivated to climb' — do not walk that back. In interview, frame it as: the analytical toolkit (VaR, risk decomposition, scenario analysis, long-horizon cash flows) is identical; the asset-class cash-flow mechanics are learnable and CIB would be the environment to learn them.

2. **Illiquid-asset valuation**: CIB's book is predominantly illiquid (greenfield/brownfield infrastructure loans, equity co-investments). Saber's valuation experience is in liquid multi-asset portfolios and derivatives. In interview, lead with the scenario/stress/sensitivity toolkit and acknowledge that private-asset mark methodology is a gap — frame it as adjacent to the stochastic and DCF modelling in the repo.

3. **Standalone investment-risk ownership**: Saber's sign-off authority is on analytical outputs delivered to clients, not on a proprietary investment portfolio's risk framework. In interview, distinguish clearly: the role asks him to build and own CIB's investment-risk framework; his evidence is delivering the analytics that feed equivalent frameworks at institutional clients. That is a one-step transfer, not a like-for-like match.

4. **Direct reports / team leadership**: The Director title at CIB likely carries people management. The repo does not evidence formal direct-report management (only 'mentorship of junior colleagues' in §4.10). Do not claim team leadership; instead note experience coordinating cross-functional delivery and mentoring, and signal readiness to grow into formal management.

5. **'~30–40% cycle-time reduction' (agentic AI)**: This is a repo-supported estimate ('estimated 30–40%'). In interview, be prepared to clarify this is an internal team estimate on comparable modules, not a formally measured productivity study. The honest qualifier is in the repo and is preserved in the bullet.