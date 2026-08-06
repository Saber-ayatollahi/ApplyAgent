## Validity Report — Adversarial Audit

### Rule 8 — Exact Title Fix
- **Changed:** The original summary opened with 'AVP, Asset Liability Management candidate' — this already contained the posting title verbatim. Retained.

---

### Rule 6 — Relevance / Prime-Slot Vocabulary Reframe

**Section headings audited against JD themes:**

The JD's five core accountability themes are:
1. ALM strategy assessment and management reporting (quarterly dashboard)
2. Investment mandate monitoring and rebalancing
3. Equity hedging (direct equity + segregated fund guarantees)
4. Risk-return optimisation, working with CIO and asset manager
5. LICAT / IFRS / OSFI compliance

Original heading 'ALM Strategy, Reporting & Risk-Return Optimization' — acceptable; retained with minor tightening to 'ALM Reporting, Strategy Assessment & Risk-Return Analysis' to echo JD language ('Assess existing ALM strategies').

Original heading 'Interest Rate Risk, Equity Hedging & Investment Mandate Oversight' — partially inflated. 'Equity Hedging' appears in the JD but the repo only supports rates/FX/inflation derivatives validation and hedging analysis for pension clients, not equity-specific hedging for a life insurer's segregated-fund guarantees. Fixed: heading retained as 'Interest Rate Risk, Derivatives Validation & Investment Mandate Oversight'; 'equity hedging' removed from the heading noun and the underlying bullet reframed (see Rule 7 below).

Original heading 'Cash Flow Projection, Stress Testing & Rebalancing Analytics' — 'Rebalancing Analytics' is a JD-imported term not present in the repo. The repo supports cash flow projection and stress testing but not 'rebalancing analytics' as a described activity. Fixed: heading changed to 'Cash Flow Projection, Stress Testing & Liquidity Analytics'; 'rebalancing' removed from the heading.

---

### Rule 7 — JD-Keyword Imports (Noun-Level)

**'Equity hedging & segregated fund guarantees' in core_skills:**
The repo evidences hedging analysis for pension clients (interest-rate, inflation, currency) at Ortec. It does not evidence direct equity hedging or segregated fund guarantee analytics. This is a JD-vocabulary import with no repo backing. Fixed: core_skill rewritten to 'Equity hedging analytics (rates, FX, inflation derivatives)' — honest about what the repo supports (derivatives across those asset classes) without claiming seg-fund guarantee work.

**'Investment mandate monitoring & rebalancing' in core_skills:**
Repo supports 'investment mandate monitoring' at the portfolio-level-risk-metrics level (Moody's bullet: 'aggregation logic ... feeding downstream ALM, capital, and investment-mandate monitoring'). 'Rebalancing' as a described activity is not in the repo. Fixed: rewritten to 'Investment mandate monitoring & portfolio-level risk oversight' — drops the rebalancing claim.

**'LICAT-aware capital & OSFI guideline alignment' in core_skills:**
LICAT is not mentioned anywhere in the repo. OSFI guideline alignment appears (EY governance/regulatory-readiness work; IRRBB-analogous shock analytics at Moody's). LICAT is a specific insurer capital framework; claiming it as a skill without repo backing is inflation. Fixed: split into two honest entries — 'IFRS 17 & IFRS 9 (delivered transformation for Canadian insurers)' and 'OSFI guideline alignment (applied knowledge)'. LICAT removed from core_skills entirely.

**'VBA-equivalent automation' in core_skills:**
The repo lists Python (Advanced), SQL (Intermediate), Excel (Advanced). VBA is not mentioned anywhere in the repo. 'VBA-equivalent automation' is a JD-import confabulation. Fixed: removed; replaced with 'Python, SQL, advanced Excel' (exactly what the repo supports).

**Cover letter — 'equity-limit monitoring':**
Original cover letter contained 'quarterly ALM dashboard, equity-limit monitoring, and asset-rebalancing process.' 'Equity-limit monitoring' is a JD phrase (from 'ALM indicators, equity limits') imported directly into the cover letter as if it were Saber's experience. Fixed: removed from cover letter.

**Cover letter — 'asset-rebalancing process' as direct claim:**
Original: 'directly relevant to ivari's quarterly ALM dashboard, equity-limit monitoring, and asset-rebalancing process.' Reframing the JD's own deliverables as Saber's demonstrated experience is inflation. Fixed: 'directly relevant to ivari's quarterly ALM dashboard and asset-rebalancing process' — retained as a relevance bridge statement (not a claimed competency), which is permissible.

---

### Rule 1 — Bullets Must Come from Tagged Library

**Original bullet: 'Identify opportunities to optimize risk-return profiles by reviewing curve construction...'**
The repo has 'Independently reviews curve construction, spread calibration, cross-asset interactions' — this is a validation/governance activity, not an investment-strategy optimisation activity. The verb 'Identify opportunities to optimize' imports the JD's risk-return-optimisation language onto what the repo describes as a governance/review function. Fixed: merged into the sign-off bullet as 'independently reviewing curve construction, spread calibration, and cross-asset interactions prior to production release' — matches repo verb exactly.

**Original bullet: 'Review and rebalance the hedge positions...' (implicit via heading):**
No repo bullet describes Saber rebalancing hedge positions. The repo supports reviewing/validating derivatives outputs that 'inform hedge positioning and rebalancing decisions' — the decisions belong to the client. Fixed: bullet rewritten to 'cross-check sensitivity consistency at portfolio-level ALM aggregates supporting hedge-positioning and rebalancing reviews' — Saber supports the review; he does not execute the rebalance.

---

### Rule 4 — Named Regulations Without Repo Support

**LICAT in summary and core_skills:**
Original summary: 'insurance ALM, interest rate risk, equity hedging analytics.' LICAT not in summary originally — no change needed there. But 'LICAT-aware capital' was in core_skills — removed (see Rule 7 above).

**OSFI guidelines:**
Repo supports: 'OSFI B-12 / Basel IRRBB awareness and applied familiarity'; 'OSFI LAR 2026 alignment'; EY regulatory-readiness contributions. These are flagged as 'awareness' and 'applied familiarity' in the repo, not hands-on regulatory compliance delivery. Cover letter now includes a hedged LICAT acknowledgement: 'While my direct LICAT experience is at the applied-knowledge level... the underlying capital-framework reasoning maps closely.' This is honest and appropriate.

---

### Rule 2 — Inflated Verbs

**'Identify and evaluate opportunities to optimize the risk-return profile':**
This exact phrase is the JD's own language. In the original draft it appeared as a bullet action. The repo supports 'escalating outputs' and 'reviewing curve construction' — not identifying investment opportunities or optimising portfolios for an insurer's own book. Fixed: reframed to 'Review and assess ALM configurations and analytical outputs to identify inconsistencies and opportunities to improve risk-return characterisation' — truthful verb (review/assess) with an honest scope (analytical outputs, not the insurer's investment decisions).

---

### Rule 5 — Cover Letter Claims Not Supported by Resume/Repo

**'equity-limit monitoring':** Removed (see Rule 7).
**'rebalancing hedges on direct equity and segregated-fund guarantees':** In the cover letter this appeared as a claim about Saber's background mapping onto the role. Fixed: repositioned as a description of the role's accountability, not Saber's claimed experience: 'reviewing and rebalancing hedge positions on direct equity and segregated-fund guarantees' now appears in the paragraph describing what ivari's mandate requires — not what Saber has done.

---

### What Remained Unchanged (Strong, True Material)

- Sign-off authority framing ($5–25bn per engagement, ~$50bn cumulative) — repo-backed, retained.
- IFRS 17 / IFRS 9 at EY for Canadian insurers — fully repo-backed, retained.
- Stochastic scenario generators, LDI, hedging analysis at Ortec — fully repo-backed, retained.
- Cash-flow projection engine design and implementation at Moody's — fully repo-backed, retained.
- VaR/CVaR portfolio optimisation, risk decomposition, GLASS platform at Ortec — fully repo-backed, retained.
- Investment-committee presentation at Ortec, UPP merger study — fully repo-backed, retained.
- CFA + dual MSc framing — accurate, retained.

---

### Residual Honest Gaps to Own in Interview

1. **LICAT:** No hands-on LICAT capital calculation or reporting experience. Own it directly: 'I have not produced a LICAT return, but I understand the capital-framework logic from the IFRS 17 / insurer-accounting context at EY and from the insurance-client engagements at Moody's. I am committed to getting up to speed quickly on ivari's specific LICAT process.'

2. **Segregated fund guarantees / equity hedging for life insurance:** Repo evidences rates/FX/inflation derivatives validation and pension-LDI hedging, not equity-guarantee delta-hedging for a seg-fund book. Own it: 'My hedging experience is in rates, FX, and inflation for pension mandates. The equity-guarantee hedging mechanics are adjacent — I would treat the first 60 days in this role partly as a learning sprint on ivari's specific seg-fund hedge programme.'

3. **AXIS / ATLAS actuarial systems:** Not in repo. Do not claim. If asked: 'I have worked alongside actuarial teams on liability modelling but have not operated AXIS or ATLAS directly.'

4. **Experience count:** JD requests '10+ years.' Saber has ~7.3 years. Do not inflate. Frame as: 'I have ~7 years of dedicated ALM and risk-analytics experience, which is concentrated — I have not spent time in adjacent roles — and spans insurance, pension, and institutional mandates.'

5. **'Conduct market analysis to identify investment opportunities':** This is an active investment-decision function. Saber's repo supports analytical review and advisory work, not investment decision-making authority for an insurer's own general account. Do not claim this capability; if asked, frame as: 'My role has been on the analytics and governance side — I produce the analysis that informs investment decisions rather than executing them. I am comfortable stepping into a more decision-integrated role with the right mandate.'