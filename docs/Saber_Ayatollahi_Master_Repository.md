# Saber Ayatollahi — Master Career Repository (v2)

> **Purpose:** Single source of truth for resume and cover-letter generation. Every role-specific resume, cover letter, and LinkedIn snippet must draft from this document. The rewrite (2026-05-03) narrows positioning, adds a tagged bullet library for fast recombination, and captures a STAR story bank for interviews.

> **How to use this file:**
> 1. Sections 1–3 = identity, education, experience (factual spine).
> 2. Section 4 = evidenced skills inventory — **do not add skills not backed by Section 3**.
> 3. Section 5 = tagged bullet library — pick bullets by `[TAG]` for any resume variant.
> 4. Section 6 = STAR story bank for behavioral interviews.
> 5. Section 7 = role angles — **two primary**, not seven. All outbound focuses here.
> 6. Sections 8–11 = logistics, summary-statement bank, resume variants, job-search strategy.

> **Generated from:** `docs/master_repo/*.yaml`. Regenerate with `python docs/master_repo/_render.py`. Do not hand-edit this file.

---

## 1. IDENTITY & CONTACT

| | |
|---|---|
| **Name** | Saber Ayatollahi, CFA, MSc |
| **Location** | Toronto (North York), Ontario, Canada |
| **Phone** | +1 (416) 856-1276 |
| **Email** | saber.ayatollahi@gmail.com |
| **LinkedIn** | https://www.linkedin.com/in/sayatollahi/ |
| **Languages** | English (fluent), French (conversational) |
| **Work authorization** | Canadian citizen / permanent resident (no sponsorship required — CONFIRM WITH SABER before sending) |
| **Notice period** | 2 weeks (standard) — confirm per offer |
| **Target comp band (CAD)** | Base $185–260K + 30–50% bonus + LTIP at Director level; floor $160K base for Senior Manager. Negotiate off total comp, not base alone. |
| **Relocation** | Not needed (Toronto-based, Toronto-focused search) |
| **Availability** | Interviewing now; earliest start ~4 weeks after offer acceptance |

---

## 2. EDUCATION & CREDENTIALS

| Credential | Institution | Year |
|---|---|---|
| **Chartered Financial Analyst (CFA)** | CFA Institute | 2024 |
| **MSc, Financial Modelling** | Western University | 2018 |
| **MSc, Chemical Engineering** *(Full Scholarship)* | Western University | 2016 |

### Why these matter
- **CFA** is the gold-standard credential for investment, risk, asset management, and valuations roles.
- **Dual MSc (Finance + Engineering)** is the quantitative profile that Strats/risk-engineering desks explicitly look for.
- **Chemical Engineering** gave deep exposure to PDEs, numerical methods, and stochastic systems — the mathematical scaffolding underlying fixed income and derivatives modeling.
- CFA was completed in 2024 — *why now*: the CFA was a deliberate mid-career credential after 5+ years of practitioner experience; the combination of practitioner depth + charter is less common than either alone.

---

## 3. PROFESSIONAL EXPERIENCE

Years of experience: **~7.3 years full-time finance experience** (Feb 2019 → May 2026). Reference this consistently — avoid "8+" or "10+" phrasing that doesn't match.

### 3.1 Moody's Analytics — Asset Management & Buy-Side Solutions
**Role:** Assistant Director — Modelling Services (Investment & ALM Risk Lead)
**Location:** Toronto, ON
**Period:** May 2022 – Present (≈4 years)
**Team size / scope:** IC-plus-senior-review role within a Modelling Services team of ~12; formal sign-off mandate on output delivered to institutional clients.

#### Phase 2: Modelling Services (May 2023 – Present)
- Holds **sign-off authority on valuation, sensitivity, and ALM outputs** delivered to multi-asset institutional client portfolios; portfolio sizes typically range from **~$5bn to ~$25bn per engagement**, cumulatively covering ~$50bn+ of institutional assets across the book of work.
- Operates within Moody's internal model governance framework — independently reviews curve construction, spread calibration, cross-asset interactions, and stress behavior prior to production release.
- Validates derivatives pricing outputs (rates, FX, inflation) and cross-checks sensitivity consistency at portfolio-level ALM aggregates.
- Oversees interest rate risk and duration analysis under **parallel and non-parallel rate shocks**, aligned with industry IRRBB standards analogous to OSFI B-12 / Basel IRRBB.
- Reviews aggregation logic converting security-level exposures into portfolio-level risk metrics feeding downstream ALM and capital processes.
- Escalates outputs lacking mathematical or economic defensibility; serves as escalation point for client-critical analytical issues, interfacing with clients' Heads of Risk and investment stakeholders.
- **Led design and implementation** of an enterprise multi-asset **cash flow projection engine** supporting base, stress, and reverse-stress scenarios — providing forward-looking liquidity visibility across ALM horizons.
- Architected configurable **time-bucketed liquidity gap analytics** (T+1 through multi-year) enabling funding optimization, refinancing risk assessment, and asset-allocation decisions.
- Embedded behavioral cash flow assumptions, prepayment logic, and macro stress overlays aligned with regulatory liquidity expectations.
- Re-engineered manual spreadsheet workflows into scalable, auditable Python analytics pipelines.
- Built **agentic AI development workflows** using Claude Code and Cursor IDE — automated code generation, validation scaffolding, anomaly detection, and documentation — reducing development cycle time by an estimated 30–40% on comparable modules.
- Prepared analytical summaries for senior stakeholders covering interest-rate exposure, scenario impacts, and balance-sheet sensitivities.

#### Phase 1: Client Service Specialist (May 2022 – May 2023)
- Led **onboarding and implementation** for U.S. and Canadian pension funds, asset managers, and consulting firms migrating to the **PFaroe** analytics platform.
- Served as the technical liaison between clients and product owners, translating investment-team requirements into development requests; advised clients on asset, liability, and ALM configurations; validated model outputs post-deployment.
- Scoped client needs into Product Owner (PO) requests for development.
- Contributed to the successful migration of all assigned client accounts from the legacy Calypso platform to the PFaroe PM platform.

---

### 3.2 Ernst & Young (EY)
**Role:** Senior Consultant — IFRS & Financial Risk Transformation
**Location:** Toronto, ON
**Period:** Sep 2021 – Apr 2022 (~7 months)

- Delivered **IFRS 17 and IFRS 9** technology-transformation projects for Canadian and international insurance clients.
- Advised actuarial, IT, finance, and program-management functions on adoption of IFRS 17 and IFRS 9 standards.
- Contributed to governance documentation and regulatory readiness processes for financial institutions.
- Developed product offerings and go-to-market collateral for IFRS 17 implementation advisory services.
- Coordinated across actuarial, finance, IT, risk, and PM teams on milestone delivery and implementation materials.

---

### 3.3 Ortec Finance Canada
**Role:** Senior Consultant — Asset-Liability Management & Risk
**Location:** Toronto, ON
**Period:** Feb 2019 – Sep 2021 (~2.5 years)

- Delivered **ALM studies** for Canadian and international pension funds and institutional investors.
- Analyzed funding ratios, duration mismatch, and long-term balance-sheet risk exposures.
- Built and interpreted **stochastic economic scenario generators** to assess interest rate risk and funding volatility under base-case and stressed environments.
- Conducted **liability-driven investment (LDI)** analysis: trade-offs between return objectives, duration alignment, and liquidity considerations.
- Advised clients on Strategic Asset Allocation (SAA) to meet long-term objectives and helped clients navigate Tactical Asset Allocation (TAA) risk through stress testing and sensitivity analysis.
- Designed stochastic risk management frameworks for specific client mandates.
- Presented findings at client on-site meetings, including discussions with investment committees at pension-fund clients.

---

## 4. SKILLS INVENTORY (evidenced)

> **Rule:** no skill lives here without evidence in Section 3. If it's not in the experience section, it doesn't belong.

### 4.1 ALM, IRRBB & Balance Sheet Risk *(primary)*
- Asset–Liability Management (ALM) — structural and dynamic
- Interest Rate Risk in the Banking Book (IRRBB) — EVE and NII sensitivity under parallel and non-parallel shocks
- Duration gap & repricing mismatch analytics
- Multi-period balance sheet risk assessment
- Liquidity gap & cash flow projection modelling (T+1 to multi-year horizons)
- Stress testing & scenario analysis (base, stress, reverse-stress)
- Liability-Driven Investment (LDI) strategy & analytics
- Funding ratio & solvency analytics
- OSFI B-12 (IRRBB revision, Q1 2026 consultations) awareness and applied familiarity
- OSFI LAR 2026 (liquidity adequacy) alignment

### 4.2 Interest Rate, Fixed Income & Derivatives
- Yield curve construction & calibration
- Parallel & non-parallel rate-shock analysis
- Key-rate duration & convexity analytics
- Rates, FX & inflation derivatives valuation
- Spread calibration & cross-asset interaction analysis
- Stochastic modelling & Monte Carlo simulation
- Scenario-generator design and validation

### 4.3 Model Governance & Risk Controls *(primary)*
- Formal sign-off authority across multi-asset institutional portfolios
- Independent model review & challenge
- Assumption validation & economic-defensibility assessment
- Auditability & documentation standards
- Escalation & exception-handling processes
- OSFI E-23 (Model Risk Management, effective 2027-05-01) awareness
- SR 11-7 parallel framework awareness

### 4.4 Portfolio & Investment Risk Analytics
- Multi-asset portfolio-level analytics
- Portfolio-level stress testing and scenario analysis
- Duration positioning & cross-asset exposure analysis
- Security-level to portfolio-level aggregation
- Investment-risk oversight for multi-asset mandates

### 4.5 Financial Transformation & Regulatory Programs
- IFRS 17 & IFRS 9 transformation delivery (EY)
- Regulatory readiness support (Canadian insurers)
- Cross-functional Finance / Risk / IT alignment on regulatory programs

### 4.6 Enterprise Platform & Risk System Implementation *(primary for vendor-platform angle)*
- Enterprise risk analytics platform migration (Calypso → PFaroe)
- Scenario-engine integration and validation
- Production risk-reporting architecture
- Risk system configuration & validation
- Client onboarding for enterprise financial platforms
- Requirements scoping for Product Owners / development teams

### 4.7 Valuation & Financial Modelling
- Business valuation fundamentals (DCF, multiples, scenario analysis)
- Financial-instrument valuation (derivatives, fixed income)
- Complex payoff & sensitivity modelling
- Stochastic simulation and Monte Carlo modelling for long-horizon cash flow projections
- Economic-scenario-generator development (Ortec)

### 4.8 Programming & Technical Stack *(evidenced)*
**Languages:**
- Python (Advanced) — pandas, NumPy, SciPy
- SQL (Intermediate) — PostgreSQL day-to-day
- R (Intermediate — historical use)
- MATLAB (Intermediate — historical use in research/engineering context)

**Infrastructure & Tooling:**
- Git / version control
- CI/CD pipelines in professional context

**AI & Developer Tools:**
- Claude Code CLI (daily)
- Cursor IDE (daily)
- Agent-oriented development workflows
- LLM-assisted code generation and review

**Data & Visualization:**
- Excel (Advanced)
- Plotly / matplotlib

> **Removed from v1:** TypeScript/Node.js, Hono, Drizzle ORM, Java/C++, Kubernetes/EKS, TensorFlow/PyTorch, MongoDB, Snowflake, AWS Bedrock, Azure DevOps pipelines, multi-agent orchestration. These were not backed by experience and created interview-risk exposure. If an interviewer asks, the honest answer is *"I have used these at a hobby/learning level but haven't shipped production code with them."*

### 4.9 Regulatory Context (knowledge, not training)
- OSFI Guideline E-23 (Model Risk Management, effective 2027-05-01) — understands scope including AI/ML coverage and functional-separation requirements
- OSFI Guideline B-12 (IRRBB revision, consultations Q1 2026) — understands Basel Committee IRRBB alignment direction
- OSFI LAR 2026 (Liquidity Adequacy Requirements) — understands tightening of liquidity stress testing and cash-flow projection requirements
- IFRS 17 & IFRS 9 (delivered transformation engagements at EY)

### 4.10 Leadership & Communication
- Director-level stakeholder communication (Heads of Risk, CIO-office)
- Executive risk presentation & storytelling
- Cross-functional initiative coordination (risk / tech / product / client)
- Investment-committee presentation experience (Ortec)
- Mentorship of junior colleagues

---

## 5. TAGGED BULLET LIBRARY

> **Tags:**
> `[ALM]` = ALM / IRRBB / Balance-Sheet-Risk resume
> `[VAL]` = Model Validation / Model Risk resume
> `[VEN]` = Vendor-platform / Client Solutions resume (BlackRock Aladdin, Bloomberg, MSCI, S&P)
> `[QUANT]` = Quantitative / Fixed Income Analytics resume
> `[CON]` = Consulting / Advisory resume (Mercer, WTW, Deloitte FSI, EY FSRM boomerang)
> `[AI]` = AI-in-finance angle (add sparingly — only for AI-forward roles)

### Moody's Analytics bullets

- `[ALM][VAL]` Held sign-off authority on valuation, sensitivity, and ALM outputs delivered to institutional client portfolios ranging $5–25bn per engagement — independently reviewed curve construction, spread calibration, and cross-asset interactions prior to production release.
- `[ALM]` Oversaw interest-rate risk and duration analysis under parallel and non-parallel rate shocks, aligned with IRRBB standards analogous to OSFI B-12 and Basel Committee frameworks.
- `[ALM]` Led design and implementation of an enterprise multi-asset cash flow projection engine supporting base, stress, and reverse-stress scenarios — delivering forward-looking liquidity visibility across ALM horizons.
- `[ALM]` Architected configurable time-bucketed liquidity gap analytics (T+1 through multi-year) enabling funding optimization, refinancing risk assessment, and asset-allocation decisions under OSFI LAR-style liquidity requirements.
- `[ALM][VAL]` Embedded behavioral cash flow assumptions, prepayment logic, and macro stress overlays aligned with regulatory liquidity expectations and executive contingency planning.
- `[VAL]` Operated within formal model-governance framework — reviewed assumptions, validated economic defensibility, escalated outputs lacking mathematical support; built documentation standards consistent with SR 11-7 and OSFI E-23 expectations.
- `[VAL][ALM]` Escalated outputs lacking mathematical or economic defensibility and served as escalation point for client-critical analytical issues, interfacing with Heads of Risk and investment stakeholders.
- `[QUANT][ALM]` Validated derivatives pricing outputs across rates, FX, and inflation — ensured consistency of sensitivities and scenario impacts at portfolio-level ALM aggregates.
- `[VEN]` Led onboarding and implementation for U.S. and Canadian pension funds, asset managers, and consulting firms migrating to an enterprise analytics platform — served as technical liaison between client investment teams and product/development functions.
- `[VEN]` Successfully migrated all assigned client accounts from a legacy Calypso environment to a modern PFaroe PM platform, validating model outputs post-deployment.
- `[VEN][AI]` Built agentic AI development workflows (Claude Code, Cursor IDE) automating code generation, validation scaffolding, and anomaly detection — reducing development cycle time by an estimated 30–40% on comparable modules.
- `[VEN]` Re-engineered manual spreadsheet workflows into scalable Python analytics pipelines with embedded logging, validation, and auditability controls.
- `[ALM][VEN]` Prepared analytical summaries for senior stakeholders on interest-rate exposure, scenario impacts, and balance-sheet sensitivities — translated quantitative outputs into investment-committee-ready narratives.

### EY bullets

- `[CON][ALM]` Delivered IFRS 17 and IFRS 9 transformation projects for Canadian and international insurance clients — aligned regulatory requirements with system implementation and financial-reporting frameworks.
- `[CON]` Advised actuarial, IT, finance, and program-management functions on adoption of IFRS 17 and IFRS 9 standards; contributed to governance documentation and regulatory-readiness processes.
- `[CON]` Developed IFRS 17 advisory product offerings and go-to-market collateral.
- `[CON]` Coordinated across actuarial, finance, IT, risk, and PM teams on milestone delivery and implementation materials.

### Ortec Finance bullets

- `[ALM]` Delivered ALM studies for Canadian and international pension funds and institutional investors — analyzed funding ratios, duration mismatch, and long-term balance-sheet risk exposures.
- `[ALM][QUANT]` Built and interpreted stochastic economic scenario generators assessing interest-rate risk and funding volatility under base-case and stressed environments.
- `[ALM]` Conducted liability-driven investment (LDI) analysis — trade-offs between return objectives, duration alignment, and liquidity considerations for pension-fund clients.
- `[ALM][CON]` Advised clients on Strategic Asset Allocation (SAA) and Tactical Asset Allocation (TAA) trade-offs via stress testing and sensitivity analysis.
- `[ALM][CON]` Designed stochastic risk-management frameworks tailored to specific client mandates.
- `[CON]` Presented ALM study findings to investment committees at Canadian pension-fund clients on-site.

---

## 6. STAR STORY BANK *(for behavioral interviews)*

### Story 1 — "Led enterprise cash flow projection engine from scratch"
**Situation:** Moody's Analytics buy-side team needed forward-looking liquidity visibility across multi-asset ALM horizons; prior approach was manual-spreadsheet-based and not auditable. Situation sharpened by institutional clients asking for reverse-stress and behavioral-cashflow coverage.
**Task:** Design and build a scalable multi-scenario cash flow projection engine that integrated with the broader analytics platform.
**Action:** Architected configurable time-bucketed liquidity gap analytics (T+1 → multi-year), embedded behavioral cashflow assumptions and prepayment logic, layered macro stress overlays, and re-engineered the upstream spreadsheet workflows into Python pipelines with auditable logging.
**Result:** Shipped production engine delivering forward-looking liquidity visibility, unlocking analytical capability clients were asking for and reducing manual workflow time materially.
**Tags:** `[ALM]` `[VEN]` `[VAL]`

### Story 2 — "Escalated a model output that was mathematically defensible but economically wrong"
**Situation:** A client-delivery run produced portfolio-level sensitivities that passed all internal checks but did not square with the client's economic intuition under a specific rate-shock scenario.
**Task:** Either sign off under deadline pressure or hold the release and escalate — with client relationship and platform credibility on the line.
**Action:** Held the release, re-ran the sensitivities decomposed by asset class, identified a curve-calibration edge case (short-end inversion handling), escalated to product owners and the client's Head of Risk, and walked through the remediation plan.
**Result:** Release delayed by 48 hours; client avoided acting on wrong numbers; defect was remediated upstream and captured in validation tests. Built trust with Head of Risk — became their direct escalation contact.
**Tags:** `[VAL]` `[ALM]`

### Story 3 — "Bridged client investment team and development organization"
**Situation:** During Calypso → PFaroe migration, a pension-fund client's ALM configuration requirements were being lost in translation between their investment desk and Moody's dev team, delaying onboarding.
**Task:** Bring both sides to a working agreement quickly.
**Action:** Scoped client requirements into structured Product Owner requests, walked PO through the investment-team's decision logic, translated dev pushback back into investment language.
**Result:** Client onboarded on schedule; configuration pattern was reused for subsequent clients in the migration cohort.
**Tags:** `[VEN]` `[CON]`

### Story 4 — "LDI study that shifted a pension fund's SAA"
**Situation:** Ortec Finance ALM study for a Canadian pension-fund client — client was questioning whether their fixed-income duration positioning was appropriate given a liability-duration extension.
**Task:** Quantify the trade-off and present to the investment committee.
**Action:** Built stochastic economic scenario generator calibrated to the client's assumptions, ran funding-ratio distributions under base and stressed regimes, decomposed duration gap contribution to funding-ratio volatility, presented results with explicit SAA recommendations.
**Result:** Committee adopted a duration extension recommendation; client returned to Ortec for subsequent studies.
**Tags:** `[ALM]` `[CON]` `[QUANT]`

### Story 5 — "IFRS 17 program — reconciling finance, actuarial, and IT"
**Situation:** EY client — Canadian insurer mid-way through IFRS 17 implementation with finance, actuarial, and IT functions out of sync on data sourcing and CSM mechanics.
**Task:** Drive alignment at the technical level so the program could hit its reporting readiness milestone.
**Action:** Built shared requirements documentation, walked each function through other functions' constraints, identified the three decisions that needed executive sign-off, escalated clearly.
**Result:** Program milestone hit; documentation was reused across subsequent IFRS 17 engagements.
**Tags:** `[CON]` `[ALM]`

### Story 6 — "Spreadsheet to Python pipeline — governance upgrade"
**Situation:** A Moody's valuation workflow was spreadsheet-driven with limited logging and no versioning — not acceptable under model-governance audit.
**Task:** Migrate without disrupting live client delivery.
**Action:** Parallel-built Python pipeline; ran in shadow mode for two cycles; reconciled output; cut over with rollback plan.
**Result:** Governance audit closed satisfactorily; pipeline became template for adjacent workflows.
**Tags:** `[VAL]` `[ALM]` `[VEN]`

### Story 7 — "Using Claude Code to accelerate code review"
**Situation:** Validation workload was expanding faster than the team could grow headcount.
**Task:** Find a force-multiplier.
**Action:** Built agentic review workflows (Claude Code, Cursor IDE) — automated first-pass code review, validation scaffolding, documentation drafts; human still signs off on governance-critical review.
**Result:** Cycle time on comparable validation modules dropped ~30–40%; approach is being explored for broader adoption. Also a portfolio piece for any AI-forward interview.
**Tags:** `[AI]` `[VAL]` `[VEN]`

### Story 8 — "Chem Eng → Finance — why the pivot stuck"
**Situation:** Interviewer probes the chem-eng-to-finance pivot.
**Task:** Answer credibly without apologizing for the transition.
**Action:** Honest framing: chem eng gave mathematical fluency with PDEs, numerical methods, and uncertainty quantification. Financial modelling MSc translated that into the finance vocabulary. First five years (Ortec, EY) were the bridge. CFA in 2024 consolidated the charter-level signal.
**Result:** Positioned as deliberate, not accidental. Ties to interviewer's next question (usually "what about finance sticks?").
**Tags:** `[ALL]`

### Story 9 — "Sign-off on a $15bn portfolio — how I think about that trust"
**Situation:** Interviewer challenges "you're Assistant Director, how do you have sign-off?"
**Task:** Clarify role scope without overclaiming.
**Action:** Honest framing: Moody's runs a formal governance framework where sign-off authority is delegated by role, not title. The Assistant Director role is IC-with-independent-review authority; sign-off attests to defensibility of specific analytical outputs, not to the whole portfolio's investment strategy.
**Result:** Distinction is clear; interviewer moves to the technical probing (yield curve, behavioral assumptions, etc).
**Tags:** `[VAL]` `[ALM]`

### Story 10 — "Managed a difficult client escalation"
**Situation:** (Reserve this slot — log a real incident here within 2 weeks; every senior finance interview uses one of these.) Placeholder: Difficult client situation at Moody's / EY / Ortec where a stakeholder pushed hard on an analytical answer they didn't like.
**Task:** Hold the line on analytics while preserving the relationship.
**Action:** (to fill)
**Result:** (to fill)
**Tags:** `[ALL]`

---

## 7. TARGET ROLE POSITIONING — **TWO ANGLES ONLY**

> **Decision 2026-05-03:** Retired 5 of the original 7 angles (Portfolio Manager, Product Manager, Project/Program Manager, Valuations-as-primary, Asset Management Quant-as-primary). Not removed from capability — removed from *active outbound*. If a specific role appears that fits a retired angle exceptionally well, treat it as a one-off and draft ad hoc from the bullet library. Do not run parallel searches on retired angles.

### 7.1 — PRIMARY: ALM / IRRBB / Model Governance
**Best-fit titles:** Director — ALM & Balance Sheet Risk · Director — IRRBB Modelling · Senior Manager/Director — Model Risk & Validation · Head of ALM Analytics · Director — Treasury Risk · VP — Balance Sheet Risk

**Evidence stack:** Sign-off authority on multi-asset institutional portfolios (Moody's) · Cash flow projection engine design and delivery (Moody's) · IRRBB-analogous shock analytics and curve calibration (Moody's) · LDI and stochastic scenario generators (Ortec) · Model governance framework operation (Moody's).

**Summary angle (45–55 words):**
> Asset-Liability Management and balance sheet risk professional with ~7 years spanning institutional ALM analytics, IRRBB modelling, liquidity projection, and model governance. Currently operates sign-off authority on multi-asset institutional portfolios at Moody's Analytics. CFA + dual MSc (Financial Modelling + Engineering). LDI background from Ortec Finance, IFRS 17 / IFRS 9 delivery from EY.

**Target employers:** Scotiabank, RBC, BMO, CIBC, TD, National Bank, Equitable Bank/EQB, HSBC Canada, Citibank Canada, JPMorgan Canada; CPP, OTPP, OMERS, HOOPP, PSP, OPTrust, CAAT, IMCO; Manulife, Sun Life, Canada Life, Intact, iA, RGA.

---

### 7.2 — SECONDARY: Vendor-Platform / Client Solutions
**Best-fit titles:** Director — Aladdin Client Engagement · Senior Analytics Specialist · Director — Risk Solutions · Product Manager (Risk/ALM platforms) · Senior Quantitative Analyst — IR Modelling · Director — Client Advisory

**Evidence stack:** Institutional platform delivery at Moody's (direct parallel to Aladdin, S&P Risk Solutions, MSCI Analytics, Bloomberg Financial Solutions) · Calypso→PFaroe migration leadership · Client-translation across investment teams and dev · Agentic-AI workflow design (Claude Code, Cursor).

**Summary angle (45–55 words):**
> Senior finance-technology professional bridging institutional investment teams and enterprise risk platforms. ~4 years at Moody's Analytics delivering, configuring, and validating the multi-asset analytics platform competing directly with Aladdin, MSCI, and S&P Risk Solutions. CFA + dual MSc + agentic AI workflow experience — rare combination at the finance/platform boundary.

**Target employers:** BlackRock (Aladdin), Bloomberg (Financial Solutions), MSCI, S&P Global, FactSet, Morningstar DBRS, SS&C Algorithmics, Numerix, Prometeia.

---

### 7.3 — Ad-hoc third lane: Consulting / Advisory (opportunistic)
Only activate if an EY boomerang, Mercer/WTW LDI-specific role, Deloitte FSI Director-level risk advisory role, or Oliver Wyman FS role surfaces. Do not run active search. If activated, lead with Ortec advisory roots + EY transformation evidence.

---

## 8. SUMMARY-STATEMENT BANK

### Short (LinkedIn headline, 150 chars)
- `v-ALM-short` *Director-level ALM & IRRBB specialist · CFA · Moody's Analytics · ex-Ortec LDI · sign-off authority on multi-asset institutional portfolios*
- `v-VEN-short` *Senior risk-analytics practitioner bridging institutional investment teams and enterprise platforms · CFA · Moody's Analytics · agentic AI workflow builder*

### Medium (resume header, 40–70 words)
Covered in §7.1 and §7.2.

### Long (cover-letter opening paragraph, 110–140 words)

- `v-ALM-long`
> I am an Asset-Liability Management and model-governance specialist currently at Moody's Analytics, where I hold sign-off authority on valuation, sensitivity, and ALM outputs for multi-asset institutional portfolios. Over the past four years I have led the design of a multi-scenario cash flow projection engine, operated IRRBB analytics under parallel and non-parallel rate shocks, and validated derivatives outputs at portfolio-level ALM aggregates. Before Moody's, I delivered insurance-accounting transformation at EY, and stochastic ALM studies for Canadian pension funds at Ortec Finance. I hold the CFA charter and dual MSc degrees (Financial Modelling, Chemical Engineering). I am writing because [TARGET COMPANY]'s [TARGET TEAM] is building exactly the ALM and model-governance capability where I have spent my career — and it is where my practitioner depth most directly translates.

- `v-VEN-long`
> I have spent four years at Moody's Analytics delivering, configuring, and validating the multi-asset analytics platform that competes most directly with your own. At the institutional-client layer I have onboarded U.S. and Canadian pension funds, asset managers, and consulting firms; at the modelling layer I hold sign-off authority on valuation and ALM outputs for portfolios ranging into the mid-billions; at the engineering layer I have re-built spreadsheet workflows into production Python pipelines and have deployed agentic-AI workflows (Claude Code, Cursor) to accelerate code generation and validation. Prior roles at EY (insurance-accounting transformation) and Ortec Finance (pension ALM and LDI) extend the practitioner bench on the client side of the platform. I know your buyers because many of them are my current clients.

---

## 9. LOGISTICS & HOUSEKEEPING

### Work authorization
Confirm with Saber before first application: Canadian citizen / PR / work-permit? (This section should be filled precisely; in recruiter screens the first hard question is sponsorship.)

### Notice period and earliest start
Standard 2 weeks. Earliest practical start ≈ 4 weeks post-offer.

### Salary anchoring by tier
See `references_and_salary.md` for detailed band research.
- Director / VP Big 6 Banks: $195–260K base + 35–50% bonus + LTIP ≈ $300–420K TC.
- Director Maple 8 pension: $200–310K base + 30–50% bonus + LTIP ≈ $320–500K TC.
- Director US/global AM (BlackRock, PIMCO): $195–310K base + bonus + RSU ≈ $330–550K TC.
- Director vendor (Bloomberg, MSCI, S&P): $175–250K base + bonus + RSU ≈ $260–400K TC.
- Senior Manager insurer / mid-bank (EQB, Canada Life, Intact): $165–230K base + bonus ≈ $220–310K TC.
- Senior Manager / Director Big 4 Risk Advisory: $170–230K base + bonus ≈ $220–300K TC.

### References (to confirm with Saber)
- Moody's: direct manager (sign-off delegator) — **primary technical reference**
- Moody's: Product Owner for a recent platform engagement — **platform delivery reference**
- EY: senior manager from IFRS 17 engagement — **consulting/transformation reference**
- Ortec Finance: senior consultant or director who co-led a pension ALM study — **ALM advisory reference**
- CFA sponsor or MSc advisor — **character/academic reference**
Contact each BEFORE final-round interviews; confirm they can speak to the specific capabilities the target role requires.

### Publications / speaking / thought leadership
*(to fill)* — if none currently, the LinkedIn content engine (see `linkedin_content_engine.md`) is the plan to build a public footprint over the next 12 weeks.

---

## 10. RESUME VARIANTS ON FILE (update 2026-05-03)

| Variant | Role focus | File | Status |
|---|---|---|---|
| ALM / IRRBB (primary) | Big 6 banks, pensions, insurers | `Saber_Ayatollahi_Spring_2026_ALM.docx` | Update this week |
| Model Validation | RBC, TD, CIBC, BMO, Scotia validation teams, BNY, State Street | `Saber_Ayatollahi_Spring_2026_Validation.docx` | Build this week |
| Vendor-Platform | BlackRock Aladdin, Bloomberg, MSCI, S&P, FactSet, SS&C Algorithmics | `Saber_Ayatollahi_Spring_2026_VendorPlatform.docx` | Build this week |
| Quant / Fixed Income Analytics | PIMCO, Wellington, RBC GAM, TDAM, CPP/OTPP/OMERS quant teams | `Saber_Ayatollahi_Spring_2026_Quant.docx` | Build this month |
| Consulting / Advisory *(opportunistic)* | EY FSRM, Mercer, WTW, Deloitte FSI | `Saber_Ayatollahi_Spring_2026_Consulting.docx` | Build on trigger |

Retired variants (no longer in rotation): Portfolio Manager (`_PM.docx`), Product Manager (`_Product.docx`), Project/Program Manager.

---

## 11. JOB-SEARCH STRATEGY NOTES

- Primary narrative: **ALM / IRRBB / Model Governance — sign-off authority on multi-asset institutional portfolios, cash-flow-engine build, LDI practitioner depth.** Every Big 6 and insurer cover letter opens on a concrete capability tied to the target team (not on regulatory-calendar framing).
- Secondary narrative: **Vendor-platform practitioner who already knows your buyers.** Every BlackRock / Bloomberg / MSCI / S&P cover letter opens on this hook.
- Toronto-only geography — all target companies have confirmed Toronto presence.
- Warm intros over cold applications for Director+ roles (~70% of Director-level hiring is referral-driven in Toronto finance). For every tailored application, attempt at least one warm-intro pathway before submitting.
- Cadence: 8 apps/wk · 10 outreach messages/wk · 3 coffees/wk · 1 LinkedIn post/wk (see `operating_cadence.md`).
- Use `jd_tailor.py` to draft resume + cover letter variants before applying; never ship a generic resume.

---

*Last updated: 2026-05-03 | v2 rewrite: narrowed positioning, added tagged bullet library, STAR story bank, resolved year-count and sign-off framing inconsistencies.*
