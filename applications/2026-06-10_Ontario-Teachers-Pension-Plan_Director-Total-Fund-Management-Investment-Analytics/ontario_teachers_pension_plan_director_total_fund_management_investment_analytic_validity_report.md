## Validity Report — Audit Changes & Residual Honest Gaps

### SUMMARY — Changes Made

#### 1. 'Investment analytics leader' → 'Investment analytics professional'
**Flag:** 'Leader' implies direct people-management at scale. The repo describes an IC-plus-senior-review role within a team of ~12. Saber does not hold a people-manager title at Moody's.
**Fix:** Downgraded to 'professional.' Accurate; not self-deprecating.

#### 2. Core skills — removed 'Total Fund analytics & portfolio construction'
**Flag:** 'Total Fund analytics' and 'portfolio construction' are JD-imported duty descriptions, not grounded capabilities in the repo. Saber has *portfolio-level analytics* and *scenario analysis* but has not run a Total Fund construction process.
**Fix:** Replaced with 'Multi-asset portfolio analytics & scenario analysis' — which is fully repo-supported.

#### 3. Core skills — removed 'Predictive modeling, optimization & scenario analysis' as written
**Flag:** 'Predictive modeling' implies ML/statistical forecasting models (regression, time-series, classification). The repo supports stochastic scenario generation and Monte Carlo — not supervised/unsupervised ML predictive modeling. Combining it with 'optimization' and 'scenario analysis' under one label borrowing JD language.
**Fix:** Replaced with 'ALM, liquidity gap & cash flow projection modelling' and kept 'scenario analysis' embedded in the multi-asset analytics bullet. VaR/CVaR optimization is supported and explicitly called out in its own skill.

#### 4. Core skills — removed 'AI / ML model development & agentic workflows'
**Flag:** 'ML model development' is not supported by the repo. The repo explicitly removed TensorFlow/PyTorch and ML frameworks from the evidenced skills. Saber uses Claude Code and Cursor for agentic *development automation* — this is not the same as building ML models for investment analytics.
**Fix:** Replaced with 'AI-assisted development & agentic workflows (Claude Code, Cursor)' — accurate and still JD-relevant for the AI angle.

#### 5. Core skills — removed 'Cross-functional squad & vendor leadership'
**Flag:** 'Leadership' of a squad implies direct people management or squad-lead authority. The repo supports *coordination within* and *delivery from* cross-functional squads, and translation of requirements to Product Owners. Does not support squad leadership in the headcount/people sense.
**Fix:** Reworded to 'Cross-functional squad delivery & vendor/product liaison' — accurate.

#### 6. Resume bullet — 'Lead aggregation and modeling of multi-asset public-market portfolio data' (Moody's, Investment Analytics section)
**Flag:** This sentence is lifted near-verbatim from the JD ('Lead aggregation and modeling of public market portfolio data'). The underlying activity is supported by the repo (aggregation logic, security-to-portfolio conversion), but the verb 'Lead' in this context implies ownership of a data engineering function, which is not repo-supported.
**Fix:** Rewritten as 'Review and validate aggregation logic converting security-level exposures into portfolio-level risk metrics — covering duration, cross-asset interactions, and scenario impacts — feeding downstream ALM and investment-committee reporting.' Truthful verb ('review and validate') with accurate scope.

#### 7. Resume bullet — 'leverage monitoring' added to cash flow engine bullet
**Flag:** 'Leverage monitoring' appears in the JD and was added to the cash flow engine description. The repo's cash flow engine description mentions 'funding optimization, refinancing risk assessment, and asset-allocation decisions' — not leverage monitoring specifically. The engine is an ALM/liquidity engine; leverage monitoring is a separate analytics capability.
**Fix:** Removed 'leverage monitoring' from the cash flow engine bullet. Retained 'funding optimization' and 'refinancing risk assessment' per repo. 'Leverage overlays' does appear in the Ortec bullet (repo-supported) and was retained there.

#### 8. Cover letter — 'leverage' framing
**Flag:** The original cover letter referenced 'funding, leverage, and cross-asset exposures' as engine outputs. As above, leverage monitoring is not a named output of the repo-described cash flow engine.
**Fix:** Revised to 'funding, cross-asset exposures, and balance-sheet risk' — all repo-supported.

#### 9. Cover letter word count check
**Original:** ~340 words (within 300–350 rule).
**Revised:** ~340 words — compliant.

#### 10. Cover letter — 'product engineering leadership' framing removed
**Flag:** The JD calls for 'hands-on product engineering leadership.' The draft did not explicitly claim this, but the phrase 'product engineering discipline' was used implicitly. Given Saber's role is IC/analytics lead (not an engineering-org people manager), this was not inserted.
**Status:** No overclaim present; flagged for interview awareness (see gaps below).

---

### RESIDUAL HONEST GAPS — Own These in Interview

#### Gap 1: Years of experience vs. JD requirement
**JD requires:** 'Minimum 15 years of relevant experience, including at least 5 years in a senior leadership role.'
**Saber has:** ~7.3 years total finance experience; no formal people-management title.
**Honest framing:** This is a material gap. The application is viable only if OTPP interprets 'relevant' broadly (quant depth + analytics delivery + institutional pension context) and if the hiring manager is open to a high-ceiling candidate below the stated floor. Do not misrepresent years. If asked, answer: 'Seven-plus years of directly relevant practitioner experience across ALM analytics, model governance, and institutional platform delivery — I recognize the JD signals a more senior people-management profile and I'm happy to discuss how my technical depth and delivery track record maps onto that mandate.'

#### Gap 2: People management / team-building
**JD requires:** Build and lead high-performing analytics and AI teams; attract, develop, and retain senior data science talent.
**Saber has:** IC-plus-senior-review authority; mentorship of junior colleagues (repo-noted but not detailed); no evidence of hiring, performance management, or org-building.
**Honest framing:** 'I have operated as a senior IC with escalation authority and have mentored junior analysts, but I have not yet managed a direct-report team. I am actively seeking my first formal leadership role and believe the practitioner depth I bring to this mandate accelerates the team's credibility with investment and risk stakeholders from day one.'

#### Gap 3: ML / data science team leadership
**JD requires:** Lead cross-functional teams of data scientists and ML engineers; excellent knowledge of ML, NLP, advanced analytics disciplines.
**Saber has:** Agentic AI development workflows (Claude Code, Cursor); Python analytics pipelines; no ML model development, NLP, or data science team management in the repo.
**Honest framing:** 'My AI exposure is practitioner-side — deploying agentic workflows to accelerate analytics development and validation. I have not led a data science or ML engineering team. I would pair my domain depth in investment analytics and model governance with technically stronger ML leads to cover that gap.'

#### Gap 4: Budget and resource management
**JD requires:** Oversee budgets, resource planning, and squad capacity.
**Saber has:** No budget or resource-management evidence in the repo.
**Honest framing:** Do not claim it. If asked: 'I have not held formal budget ownership; I have influenced resource prioritization by scoping and sequencing analytical work within a cross-functional squad.'

#### Gap 5: Predictive modeling / ML designations
**JD notes:** 'Designations in AI, Machine Learning, and/or Analytics are considered an asset.'
**Saber has:** CFA + dual MSc (Financial Modelling + Chemical Engineering). No ML certification.
**Honest framing:** No action needed; CFA + dual MSc is a strong credential profile. Simply do not claim an ML designation.

#### Gap 6: Global trading / execution analytics
**JD scope includes:** Global trading capabilities, execution efficiency.
**Saber has:** No trading-desk or execution analytics experience in the repo.
**Honest framing:** Do not activate. This is a portion of the mandate Saber would build toward, not lead on day one. Frame the analytics/ALM/risk side as the primary value-add; let the trading execution angle be a growth area.

---

### WHAT REMAINS STRONG AND TRUE
- Delegated sign-off authority on $5–25bn institutional portfolios (~$50bn cumulative) — directly repo-supported.
- Enterprise cash flow projection engine design and delivery — directly repo-supported.
- Liquidity gap analytics, stress/reverse-stress scenario work — directly repo-supported.
- Derivatives validation (rates, FX, inflation) at portfolio-level aggregates — directly repo-supported.
- VaR/CVaR portfolio optimization, risk decomposition, near-optimal frontier analysis (Ortec/GLASS) — directly repo-supported.
- LDI, stochastic scenario generation, pension ALM studies — directly repo-supported.
- UPP merger ALM study (JSPP) — a genuine, named OTPP-adjacent credential.
- Agentic AI workflows with measurable cycle-time reduction — directly repo-supported.
- Python pipelines with auditability and model governance controls — directly repo-supported.
- CFA + dual MSc — verified credentials.
- Toronto-based, no sponsorship required — confirmed.