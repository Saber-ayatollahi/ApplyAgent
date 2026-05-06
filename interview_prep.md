# Interview Preparation — Technical + Behavioral + Per-Company

> Saber Ayatollahi — Director/VP level Toronto finance interviews. Primary = ALM/IRRBB/Model Governance. Secondary = Vendor-Platform / Client Solutions.

> **How to use:** 1 hour before any interview, skim §1 for the relevant technical block, §3 for the company, §2 for 2-3 STAR stories that match the JD. Have pen + paper ready for shock/Monte Carlo whiteboard questions.

---

## 1. Technical Q&A — ALM / IRRBB / Model Governance

### 1.1 IRRBB fundamentals

**Q: Explain the difference between EVE and NII sensitivity.**
A: EVE (Economic Value of Equity) is the long-run, present-value perspective — it shocks the yield curve, re-prices all assets and liabilities, and reports the change in equity's economic value. NII (Net Interest Income) is the short-run, accrual-accounting perspective — it projects net interest income under rate shocks over a 12–24 month horizon using contractual and behavioral repricing assumptions. EVE captures long-duration mismatches; NII captures near-term earnings volatility. Basel IRRBB requires both. They can give opposite signals: a bank short-funded in long-duration loans has NEGATIVE EVE sensitivity to rate rises (loan values fall faster than deposit values) but POSITIVE NII sensitivity (loans reprice up while deposits lag).

**Q: What are the six standardized rate shocks under Basel IRRBB?**
A: Parallel up, parallel down, steepener, flattener, short rate up, short rate down. Magnitudes are currency-specific — e.g., ~200bps parallel for CAD/USD, smaller for JPY/EUR historically. OSFI B-12 is being revised (consultations Q1 2026) to align Canadian Schedule I banks more tightly with Basel Committee IRRBB standards.

**Q: How do you model non-maturity deposit (NMD) behavior?**
A: NMDs — chequing, savings, money-market accounts — have no contractual maturity, but depositors don't actually move money at the rate curve's short end. Common approach: decompose into stable core and volatile surge components (Basel caps on stable fraction per deposit type: retail transactional / retail non-transactional / wholesale). Run separate behavioral duration assumptions — stable core might carry a 3-5 year effective duration; surge deposits near zero. Validate against historical run-off rates under prior rate cycles. NMD modeling is always where IRRBB results get sensitive; it's where model-risk committees spend the most time.

**Q: What's the difference between contractual and behavioral duration for retail mortgages?**
A: Contractual = the coupon schedule as written. Behavioral = observed prepayment behavior overlaid (refinance sensitivity, partial prepayment options, renewal elasticity in Canadian 5-year-fixed context). Canadian mortgages renew at 5 years — so a contractual 25-year amortization has a behavioral duration closer to 2.5 years on average (assume ~50% mid-term prepayment/partial-paydown probability). Wrong assumption here is a common source of EVE/NII mismeasurement.

**Q: How do you calibrate a yield curve?**
A: Choose instruments (OIS short end, deposits + forwards for belly, swap rates longer, bonds for spread adjustments). Bootstrap zeros from instrument prices → discount factors → forward rates. Smooth with cubic spline or monotone convex to avoid arbitrage. Validate daily by repricing the input instruments to within basis-point tolerance. Calibration choices (OIS vs LIBOR/CORRA, multi-curve framework post-2008, collateralized vs uncollateralized) matter a lot for derivatives pricing and sensitivity consistency.

**Q: What's a non-parallel shock scenario that's especially dangerous for Canadian banks?**
A: A short-end hike combined with a long-end rally (bull flattener) — Canadian banks have large fixed-rate 5-year mortgage books funded by shorter-duration deposits. A bull flattener compresses NIM on the mortgage spread and raises funding costs without lifting reinvestment yields. This is the scenario CAD banks stressed hard in 2022–23.

### 1.2 Liquidity / LAR / cash flow projection

**Q: LCR vs NSFR — when does a bank flag both?**
A: LCR (Liquidity Coverage Ratio) = HQLA / Net Cash Outflows 30-day, ≥100%. NSFR (Net Stable Funding Ratio) = Available Stable Funding / Required Stable Funding 12-month, ≥100%. LCR captures 30-day crisis liquidity; NSFR captures structural funding mismatch. A bank funded heavily in wholesale short-dated paper but lending long-duration is fine on LCR (cash in 30 days) but fails NSFR. OSFI's LAR 2026 updates tighten both.

**Q: How do you design a reverse-stress test for liquidity?**
A: Forward scenarios answer "what happens if X occurs?" Reverse-stress flips: "what combination of events would cause liquidity failure?" Approach: define failure (e.g., LCR < 80% or NSFR < 90%), run solver across the funding/asset/deposit-flight dimensions, identify the envelope of scenarios that hit failure. Useful for contingency-funding-plan design and for disclosing tail vulnerabilities to the board.

**Q: What's a time-bucketed liquidity gap? Why use it?**
A: Split cash flows into buckets (T, T+1-7d, T+8-30d, T+1-3m, T+3-12m, T+1-3y, T+3-5y, T+5y+). For each bucket, compute expected inflows minus outflows under behavioral assumptions. Cumulative gap reveals where funding pressure concentrates. Better than a single-number metric because it surfaces the *shape* of the mismatch. At Moody's I built T+1 through multi-year buckets with toggleable stress overlays.

### 1.3 Model risk / governance (OSFI E-23)

**Q: What does OSFI E-23 require that the prior SR 11-7-analogous Canadian guidance didn't?**
A: The Sept 2025 final version of E-23 (effective 2027-05-01): (1) explicitly extends scope to AI/ML models, not just traditional quantitative models; (2) mandates functional separation of model developer / model owner / independent model reviewer, with clear accountability for each; (3) introduces more prescriptive documentation and ongoing-monitoring expectations; (4) raises the bar on vendor model governance — institutions must understand and attest to vendor model methodology, not just "trust the vendor". The practical effect is that every FRFI is expanding validation team headcount and building out AI/ML-model-risk playbooks ahead of 2027.

**Q: Walk me through a model validation you've done.**
A: Use STAR Story 2 (model output flagged economically-wrong escalation).

**Q: What distinguishes challenge from audit in model risk?**
A: Independent challenge = parallel thinking, during-development engagement, methodology debate with model developer. Audit = post-fact review of whether the framework was followed. E-23 emphasizes challenge — auditors can't catch methodology errors that the developer didn't catch themselves.

**Q: Where does model risk fit in the 3 Lines of Defense?**
A: Model development = Line 1 (front-office / business). Independent model validation / risk management = Line 2. Internal audit = Line 3. E-23 re-emphasizes that model owners (Line 1 business stakeholders) and developers should be functionally separate; validators cannot be compromised by reporting into the same function as development.

### 1.4 Derivatives / fixed income

**Q: PV01 / DV01 vs key-rate duration — when does one mislead?**
A: Parallel DV01 assumes uniform shift — masks curve shape exposure. Key-rate duration decomposes sensitivity to bucketed shifts (2y, 5y, 10y, 30y). A portfolio can be parallel-neutral but exposed to a steepener — DV01 would show zero, KRD would show short 2y + long 10y positions. Always report KRD alongside parallel DV01 for any non-trivial portfolio.

**Q: How does CVA impact derivatives pricing?**
A: Credit Valuation Adjustment = expected loss from counterparty default on a derivative position. Netting and collateralization mitigate. Funding Valuation Adjustment (FVA) is now also standard. For a trading book, these adjustments are P&L-relevant; for an ALM book with centrally cleared derivatives, CVA is typically zero on the cleared side. Know which one applies to the role.

**Q: What's the difference between a total return swap and a credit default swap?**
A: TRS = synthetic replication of total return (price return + coupons) of a reference asset in exchange for a funding leg (LIBOR/SOFR + spread). Used for leverage, synthetic exposure, balance-sheet optimization. CDS = insurance against credit event; pays par minus recovery on default. Different risk profiles: TRS = broad market + credit; CDS = pure credit event.

### 1.5 LDI specific (for HOOPP, OTPP, OMERS, Mercer, WTW interviews)

**Q: Walk me through building an LDI portfolio.**
A: (1) Estimate liability duration, convexity, and cash flow profile with actuarial help. (2) Construct a hedge-ratio target (typically 60-100% of duration, sometimes with sleeves on interest rate vs credit vs inflation risk). (3) Choose instruments: physical bonds, swaps (pay-fixed), total return swaps, or bond futures depending on collateral regime. (4) Set rebalancing tolerance — tighter in periods of curve volatility. (5) Report hedge-effectiveness ratios to the investment committee.

**Q: How does a Canadian pension manage inflation-linked liabilities?**
A: Real-Return Bonds (GoC RRBs — now being wound down in new issuance, supply-constrained), provincial inflation-linked issuance, inflation swaps (limited Canadian market), private inflation-indexed real-asset exposures (infra, real estate). Canadian DB plans with CPI-linked benefits face a structural inflation-hedge supply problem; many use a partial synthetic approach.

---

## 2. STAR stories — mapped to competencies

See `Saber_Ayatollahi_Master_Repository.md` §6 for the full bank of 10 stories. Mapping shortcut:

| Competency probed | Which story to use |
|---|---|
| "Tell me about a time you influenced a senior stakeholder" | Story 2 (model output escalation) |
| "Tell me about a technical project you led" | Story 1 (cash flow projection engine) |
| "Tell me about a time you bridged two teams" | Story 3 (client / dev bridge), Story 5 (IFRS 17) |
| "Tell me about a time you used data to change a decision" | Story 4 (LDI study SAA shift) |
| "Tell me about a time you delivered under pressure" | Story 6 (spreadsheet → Python migration) |
| "Tell me about innovation you drove" | Story 7 (Claude Code workflows), Story 1 |
| "Walk me through your career" | Story 8 (Chem Eng → Finance arc) |
| "How do you handle authority / sign-off?" | Story 9 (sign-off framing) |
| "Tell me about a difficult client / stakeholder" | Story 10 (fill before interview) |

---

## 3. Per-company prep

### 3.1 Scotiabank
- **Team structure:** ALM Modelling Team in Treasury (6–8 quants); reports up to Treasury CIO-equivalent; partners with Global Risk Management on Model Validation.
- **Known tech:** likely QRM or in-house IRRBB platform; Python + SAS mixed.
- **Active area:** large IRRBB remediation program ongoing; ALM analytics platform modernization.
- **Interview likely stages:** recruiter screen (30') → HM screen (45') → 2-3 technical interviews (IRRBB deep dive, model governance, coding) → panel with Director+ → offer.
- **Questions to ask:**
  - "How is the ALM Modelling Team split between NMD behavioral modeling, TP curve construction, and scenario engine development?"
  - "What's the biggest methodology debate the team has had in the last quarter, and how did it resolve?"
  - "How does the Director ALM Modelling role interface with Group Model Validation day to day?"

### 3.2 RBC
- **Team structure:** Group Treasury ALM (multiple sub-teams) + Group Risk Management Model Risk (largest in Canada). Cross-entity scope (Canada, US, UK, EU, Caribbean).
- **Known tech:** multi-platform; heavy QRM and custom in-house.
- **Active area:** RBC-HSBC Canada integration completing 2026; large cross-border model inventory requires ongoing governance build-out.
- **Questions to ask:**
  - "How is the model inventory being consolidated post-HSBC integration, and where are the biggest overlapping-methodology debates?"
  - "What does success look like for this role 12 months in?"

### 3.3 BMO (Model Validation Director — bmo-001)
- **Team structure:** Model Risk Management group, Director level reports to VP MRM.
- **Known tech:** mixed; Python increasing, legacy SAS persistent.
- **Active area:** growing validation headcount; expanding ML / vendor-model governance coverage.
- **Questions to ask:**
  - "What's the current split of validation work — traditional models, ML models, vendor models?"
  - "How does the Director role balance new-model validation vs. ongoing-monitoring review?"
  - "What's the team's 12-month priority stack?"

### 3.4 BlackRock (Aladdin Client Engagement Director — br-001)
- **Team structure:** Aladdin Toronto office; Client Engagement team serves Canadian institutional clients (banks, pensions, AMs, insurers).
- **Known tech:** Aladdin platform, obviously; Python/Java/C++ ecosystem under the hood; Snowflake/Kafka data pipeline stack.
- **Interview likely stages:** recruiter screen → HM screen → 2-3 client-facing case studies → panel with Managing Directors.
- **Questions to ask:**
  - "What do Aladdin's Canadian pension clients most commonly ask for that's not currently in the roadmap?"
  - "How does the Client Engagement Director role differ from Solutions Engineering — where's the dividing line?"
  - "What does a successful first 90 days look like in client engagement?"

### 3.5 Bloomberg (Senior Quant IR Modeling — bloom-001)
- **Team structure:** Financial Solutions, IR Modeling team; partners with Portfolio & Risk Analytics product leads.
- **Known tech:** Bloomberg's own stack (terminal + BQL + Python bindings).
- **Interview likely stages:** recruiter + HM → coding test (likely Python/C++) → 2-3 technical (quant modeling + product sense) → manager round.
- **Questions to ask:**
  - "How is the IR modeling team integrated with the rest of Financial Solutions — client-driven or product-roadmap-driven?"
  - "What's the coverage split between short-rate models, HJM-family, and Monte Carlo for CVA/xVA?"

### 3.6 S&P Global (Risk Solutions)
- **Team structure:** Risk Solutions division (formerly IHS Markit analytics + S&P legacy). Toronto office at Bay Adelaide Centre.
- **Angle:** direct Moody's Analytics competitor — emphasize that Saber already speaks to their target buyers.
- **Questions to ask:**
  - "How does Risk Solutions' product roadmap differentiate from Moody's Analytics' buy-side platform?"
  - "What's the biggest Canadian-market opportunity Risk Solutions is currently chasing?"

### 3.7 MSCI
- **Team structure:** Risk & Portfolio Analytics (Barra/RiskMetrics heritage) + growing banking-risk-analytics product.
- **Angle:** MSCI's banking risk product (including IRRBB) is the growth lane — Saber's IRRBB expertise is directly applicable.
- **Questions to ask:**
  - "How is MSCI positioning the banking risk analytics product vs. established vendors like Moody's and SAS?"
  - "What does the Director role's split look like between existing Barra clients and banking-risk new clients?"

### 3.8 Maple 8 pensions (CPP, OTPP, OMERS, HOOPP, IMCO)
- **Team structures vary widely** — each fund runs its own in-house investment platform. Key Saber-relevant teams: Total Portfolio Risk, Fixed Income (active + derivative overlay), LDI, Investment Engineering & Analytics (CPP-specific term).
- **Angle:** Ortec LDI origin + Moody's institutional platform depth is a strong combined profile. For HOOPP specifically — LDI is the pension's defining mandate.
- **Questions to ask:**
  - (CPP) "How does CMF's Investment Engineering & Analytics group partner with the Systematic Strategies group?"
  - (OTPP) "How is Total Portfolio Risk evolving post-2025 funding surplus?"
  - (HOOPP) "What's the current hedge ratio philosophy and how is it adjusted when duration-matched supply is constrained?"
  - (IMCO) "How does IMCO balance the LDI mandates of OPB/WSIB against newer client onboarding?"

### 3.9 Manulife / Sun Life / Canada Life (insurers)
- **Angle:** EY insurance-accounting + Moody's ALM + Ortec LDI combined profile is highly differentiated.
- **Questions to ask:**
  - "Where is the insurer's ALM function today — resourcing up, consolidating, or pivoting into a new area?"
  - "How is long-duration liability matching changing as rates normalize off the 2022-2024 regime?"

### 3.10 EY FSRM (boomerang — ey-fsrm-001)
- **Team structure:** FSRM Toronto; natural Senior Manager / Director boomerang path.
- **Questions to ask:**
  - (Relevant EY contact) "What's the current hiring window, and what's the practice's biggest delivery gap right now?"
  - "If I were to rejoin, what's the fastest on-ramp to Director / Senior Manager?"

---

## 4. Coding / technical test preparation (for vendor, quant, Strats roles)

- **Python core:** pandas, NumPy, dict/list comprehensions, decorators, context managers, generators.
- **Finance quant:** Black-Scholes formula (know the derivation), Monte Carlo with antithetic variates, finite-difference solvers for PDEs, curve bootstrapping from instrument quotes.
- **Practice set:** 10–20 LeetCode easy/medium (focus on arrays + dicts), plus 5 finance-specific (yield curve construction, duration-matched portfolio, VaR via historical simulation).
- **Expected time-limit:** 45–90 min coding tests; expect a live-pairing round at Bloomberg, BlackRock, Goldman.

---

## 5. Compensation / negotiation during the interview

- **Do not** give a first number when asked early-round. Anchor with range only.
- **Do** know your band: see `references_and_salary.md` per target.
- **Standard deflection:** *"I'd prefer to discuss compensation once we're aligned on scope. My expectations are in line with Toronto Director/VP market at a [BANK | PENSION | VENDOR]; I'm happy to share specifics once we're both confident on fit."*
- **If pressed for a number:** give a RANGE, not a point. Pick the range from `references_and_salary.md`.
- **Never** lie about current comp. "I'd rather not share my current comp, but my expectations are based on the Toronto [TIER] market" is acceptable.

---

## 6. Company research cheat list (read before interview)

- Most recent quarterly earnings call transcript (for banks + publicly-traded AMs).
- CEO / CFO / CRO most recent public remarks.
- Industry briefing reports: OSFI annual reports, McKinsey / BCG Canada banking reports, Callan / RVK pension industry reports.
- Glassdoor review summary (note common interview themes).
- LinkedIn — identify the hiring manager, their background, their last 3 posts.

---

## 7. Red flags to watch for during interviews

- Interview process > 6 weeks end-to-end = probable "parked" role.
- No hiring manager interview scheduled = role is re-org bait.
- Comp range stonewall = recruiter knows comp is below market.
- Panel that's 80% junior staff = scarce senior bandwidth, risk of promotion choke points.
- Sudden scope changes JD→conversation = role isn't defined.

---

## 8. Questions to ALWAYS ask (end of every interview)

1. "What does success look like in this role at 6 months and 12 months?"
2. "What's the biggest open question this role will need to answer in Year 1?"
3. "What's the makeup of the team — how many senior, how many junior, and where are you growing?"
4. "What's the biggest methodology debate the team has had in the last quarter, and how did it resolve?" *(signals practitioner depth without leaning on regulatory-calendar framing)*
5. "What are the next steps in the process and what's your timeline?"

---

## 9. Immediately after interview (within 4 hours)

- Send a 3-line thank you email per interviewer. Reference one specific thing discussed. No more, no less.
- Log: interview date, interviewers, questions asked, answers given (briefly), 1-5 rating of how it went, next steps promised.
- Update `job_tracker_data.json` → status, notes, date_last_followup.

---

*Last updated: 2026-05-03*
