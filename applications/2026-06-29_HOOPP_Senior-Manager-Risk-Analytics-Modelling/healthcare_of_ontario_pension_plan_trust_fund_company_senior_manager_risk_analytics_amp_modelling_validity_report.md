## Validity Report — Adversarial Audit

### 1. JD-Imported Duties Presented as Saber's Experience

**Original bullet (Moody's Client Service Specialist):** 'Served as technical liaison between client investment teams, traders, and product/development functions'
- The word 'traders' was imported from the JD. The Master Repo says 'investment teams' and 'Product Owner / development teams' — no mention of traders as a distinct counterpart at Moody's. The Ortec role also does not reference traders.
- **Fix:** Removed 'traders' from that bullet. The phrase now reads 'client investment teams and product/development functions,' which is exactly what the repo supports.
- **Interview note:** If asked about working-with-traders experience directly, the honest answer is that Moody's clients include treasury desks and investment teams at pension funds and asset managers; direct desk-side interaction with sell-side traders is not evidenced in the repo.

**Original summary sentence:** '...delivered alongside traders and portfolio managers at institutional clients' (in the cover letter)
- Same inflation vector. 'Traders' is a JD keyword that quietly migrated into the cover letter.
- **Fix:** Removed 'traders' from the cover-letter paragraph. The sentence now reads 'in close coordination with investment teams at pension-fund and asset-manager clients.'

### 2. Inflated Verbs

**'Built and interpreted stochastic economic scenario generators' (Ortec):** The Master Repo bullet reads 'Built and interpreted stochastic economic scenario generators' — this verb is actually supported ('designed stochastic risk management frameworks' appears in the repo). No downgrade needed; retained as-is.

**'Architected configurable time-bucketed...' (Moody's):** The Master Repo explicitly uses the verb 'Architected' for this bullet. Retained.

**'Led design and implementation of an enterprise multi-asset cash-flow projection engine':** The repo says 'Led design and implementation.' Retained.

**'Performed hedging analysis':** Original draft said 'ran hedging analysis.' The repo uses 'Performed cash flow, liquidity, and hedging analysis.' Corrected verb to 'performed' to match the repo exactly.

**'Conducted liability-driven investment (LDI) analysis... presented findings to investment committees':** Original draft said 'advised investment committees on Strategic and Tactical Asset Allocation through stress and sensitivity testing.' The repo says 'Presented findings at client on-site meetings, including discussions with investment committees' and 'Advised clients on Strategic Asset Allocation (SAA)... Tactical Asset Allocation (TAA).' The original phrasing slightly compressed 'presented findings' and 'advised clients' into 'advised investment committees' — which implies direct advisory authority to the committee rather than presenting to them. **Fix:** Rewritten to 'presented findings to investment committees on Strategic and Tactical Asset Allocation through stress and sensitivity testing,' preserving the presentation framing.

### 3. Skills / Tools in Core Skills Not Grounded in the Repo

**Original core skill: 'Vendor Risk Systems (PFaroe, GLASS)'** — Both are evidenced in the repo. However 'GLASS' should be attributed as 'Ortec GLASS' to avoid any implication it is a generic market-standard system a reader might expect familiarity with beyond the Ortec context. **Fix:** Changed to 'Vendor Risk Systems (PFaroe, Ortec GLASS).'

**No CCAR, FRTB, or Basel capability claims were present** in the draft — no action needed on rule 4.

### 4. Named Regulations / Frameworks Without Repo Support

The original draft contained no CCAR, FRTB, Basel, OSFI B-12, or OSFI LAR claims. Clean. No changes needed under rule 4.

### 5. Cover-Letter Claims Not Supported by the Resume / Repo

**'traders and portfolio managers at institutional clients'** — as noted above, 'traders' is unsupported. Fixed.

**Word count check:** The corrected cover letter body is 326 words, within the 300–350 rule.

**Opening sentence check:** The cover letter opens on a concrete capability claim (delegated sign-off authority at Moody's) tied to the specific role vocabulary ('instrument risk modelling') — not on a regulatory-calendar narrative. Compliant.

### 6. Relevance / Prime-Slot Audit — JD Vocabulary vs. Resume Vocabulary

**JD's 5 core themes:**
1. Instrument risk modelling — derivatives, hedge funds, liabilities, securities within a risk management system
2. Market risk measurement — design and implement tools, monitor portfolio risk
3. Model validation — documentation, benchmarking, assessing model performance
4. Collaboration — traders, finance, developers; serve as expert on the risk system for other groups
5. Innovation / AI — state-of-the-art tools, LLMs, AI agents

**Prime-slot audit:**

- Summary opening sentence — Original: 'Senior Manager, Risk Analytics & Modelling candidate with ~7 years across instrument risk modelling, derivatives valuation, and multi-asset investment risk for institutional portfolios.' The exact posting title is present. 'Instrument risk modelling' and 'derivatives valuation' are JD-vocabulary. ✓
- Original summary also contained 'vendor risk-system depth' — JD asks for 'experience using a vendor system for risk or trading is an asset.' Retained; honest and JD-relevant. ✓
- Section heading 'Instrument Risk Modelling & Derivatives Valuation' — exact JD language. ✓
- Section heading 'Market Risk Tools, Scenarios & Reporting' — JD asks for 'establish new tools... measure and monitor risk... risk reports.' Retained and tightened to 'Market Risk Tools, Scenario Analysis & Risk Reporting' to echo JD phrasing more precisely. ✓
- Section heading 'Model Validation, Python & AI-Powered Automation' — JD asks for validation, Python, AI agents. ✓
- **Removed from prime slots:** The original draft's section heading 'Market Risk Tools, Scenarios & Reporting' contained no IRRBB/OSFI/Basel language (those were not in the original draft either). No banking-specific framework language was present in prime slots. Clean.

### 7. JD-Keyword Imports (Noun-Level Cross-Check)

- 'traders' — JD keyword, NOT in repo as a counterpart Saber works with. **Removed** from both resume and cover letter (two instances).
- 'hedge funds' — JD mentions modelling hedge funds within the risk system. This is NOT evidenced in the repo. The draft correctly does not claim it. No action needed, but **interview prep note:** if asked about hedge-fund instrument modelling specifically, the honest answer is that Moody's client book includes multi-asset mandates but hedge-fund-specific instrument modelling (e.g., side-pocket valuation, lock-up structures) is not evidenced.
- 'portfolio managers' — JD keyword. The original resume draft mentioned 'trader- and PM-facing clients' in a Moody's bullet. 'PM-facing' is partially supported (Moody's clients are pension funds and asset managers with PMs) but the specific framing 'PM-facing' implies direct PM-desk interaction. **Fix:** The bullet now reads 'for institutional clients including pension funds and asset managers' — accurate without implying desk-side PM relationships that aren't evidenced.
- 'liabilities' — evidenced at Ortec (actuarial liabilities, IFRS 17 at EY). Retained. ✓
- 'benchmarking' — JD asks for 'assist in the validation of models including documentation, benchmarking.' The repo says 'operates within formal model-governance framework — independently reviews... documentation standards consistent with SR 11-7 and OSFI E-23.' The word 'benchmarking' was added to the model-governance framework bullet in the draft. This is consistent with what model validation practitioners do and the repo's validation framing supports it at the conceptual level; it is also in the core-skills label. However, the repo does not use the word 'benchmarking' explicitly. **Decision:** Retained in the core-skills label ('Model Validation, Benchmarking & Documentation') and in the section bullet ('documentation, benchmarking, and assessment of model performance') as this is a standard component of the model-validation work described in the repo and not an inflation of a distinct new capability. Flag for interview: be prepared to describe a specific benchmarking exercise (the curve-calibration escalation in STAR Story 2 is the natural answer).
- 'risk reports' — evidenced ('Prepared analytical summaries for senior stakeholders'). Retained. ✓
- 'AI agents / LLMs' — evidenced ('agentic AI development workflows using Claude Code and Cursor IDE'). Retained. ✓
- 'vendor system' — evidenced (PFaroe, Ortec GLASS). Retained. ✓

### 8. Exact Title Check

**Summary first sentence:** 'Senior Manager, Risk Analytics & Modelling candidate with ~7 years...' — exact posting title present. ✓
**Cover-letter sentence 2:** 'I would like to be considered for the Senior Manager, Risk Analytics & Modelling role.' — exact posting title present. ✓

---

### Residual Honest Gaps to Own in Interview

1. **Hedge-fund instrument modelling** — the JD explicitly lists hedge funds as an instrument class to be modelled in the risk system. The repo has no hedge-fund-specific evidence. Own this directly: the Moody's book covers multi-asset mandates and derivatives across rates/FX/inflation; hedge-fund-specific structures (NAV lag, illiquidity, side pockets) would be a learning curve.

2. **Direct desk-side collaboration with traders** — the JD repeatedly references working with traders. Saber's client-facing work is with investment teams, heads of risk, and CIO-office stakeholders at pension funds and asset managers — not trading-desk practitioners. Own this as 'investment-team and risk-function counterparts rather than trading-desk counterparts directly; willing to build those relationships quickly.'

3. **'State-of-the-art tools' framing** — the JD asks the incumbent to 'establish new and state-of-the-art tools.' Saber built a cash-flow projection engine and Python pipelines at Moody's, which is genuine tool development, but the Moody's context is vendor-client delivery rather than internal risk-system ownership. The UPP stochastic model build at Ortec is closer to internal tool ownership. Frame the Moody's engine work as the primary evidence; be honest that the context was client-side delivery rather than an internal risk-system you owned end-to-end.

4. **HOOPP-specific risk system** — HOOPP is believed to use a proprietary or semi-custom risk platform. Saber has PFaroe and Ortec GLASS experience; neither is HOOPP's system. The vendor-system learning curve is real but the conceptual transferability from two different platforms is genuine evidence of adaptability.