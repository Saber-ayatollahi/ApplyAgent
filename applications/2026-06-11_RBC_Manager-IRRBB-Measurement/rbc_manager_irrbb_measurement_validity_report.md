## Validity Report — Adversarial Audit

### JD Core Themes (anchor for all prime-slot checks)
1. IRRBB measurement (EVE and NII/earnings) for a bank structural balance sheet under OSFI B-12 / BCBS 368.
2. ETL / extract-transform-load processes, balance-and-control, valuation and planning for transfer-priced and client contractual positions.
3. Consumer behaviour econometric modelling (prepayment, redemption, pull-through) and retail/embedded-option product pricing.
4. ALCO reporting: reconciliation and attribution of risk-measurement changes for senior management and ALCO committees.
5. Documentation of risk-measurement methodology, processes, and model enhancements.

---

### Changes Made

#### Summary — 2 fixes
- REMOVED: 'covering both economic-value (EVE) and net interest income (NII) measurement dimensions — mirroring the metrics central to bank Treasury IRRBB reporting.' The repo supports EVE and earnings-sensitivity analytics in an analogous/institutional-client context, not NII in a bank-treasury production sense. Rewritten to 'covering both economic-value (EVE) and earnings dimensions, applied in frameworks consistent with OSFI B-12 / BCBS 368' — hedged to what is actually evidenced.
- ADDED hedge: 'IRRBB-analogous' retained from the repo's own language ('analogous to OSFI B-12') to be explicit that this is vendor/client-side, not in-house bank treasury.

#### Core Skills — 3 fixes
- CHANGED 'OSFI B-12 / BCBS 368' to 'OSFI B-12 / BCBS 368 Awareness' — the repo classifies this as 'knowledge, not training' (§4.9). Claiming it as a bare skill in a prime slot without the hedge overstates hands-on bank-regulatory application.
- CHANGED 'Behavioral Modelling (Prepayment, Redemption)' to 'Behavioral Cash Flow Modelling (Prepayment, Prepayment Logic)' — the repo supports embedding prepayment logic and behavioral assumptions at the implementation level; it does NOT support personally calibrated econometric models of redemption or pull-through curves on retail-product data. 'Redemption' as a named item implies the JD's specific econometric modelling capability, which the repo does not evidence. Removed 'Redemption' from the label to avoid overstating.
- KEPT 'Risk Attribution & ALCO Reporting' but renamed to 'ALCO-Style Reporting & Risk Attribution' — small label alignment to the JD's own vocabulary ('ALCO committees'); the underlying evidence (preparing attribution summaries for Heads of Risk / investment committees) is solid.

#### Experience — Moody's, Phase 2, Section 1 (IRRBB & Balance Sheet Risk)
- CHANGED verb in bullet 2: original draft used 'Oversee' — the repo says 'Oversees interest rate risk and duration analysis under parallel and non-parallel rate shocks.' 'Oversee' is defensible for the sign-off/governance layer. However, the phrase 'covering both economic-value (EVE) and net interest income (NII) measurement dimensions — mirroring the metrics central to bank Treasury IRRBB reporting' was JD-imported framing. The repo supports EVE and earnings-based sensitivity but does NOT claim NII as a named bank-treasury metric Saber has produced. Rewritten to: 'Review interest rate risk and duration analysis under parallel and non-parallel rate shocks, in frameworks consistent with OSFI B-12 and BCBS 368 — outputs cover economic-value (EVE) and earnings-based sensitivity dimensions analogous to bank Treasury IRRBB measurement.' Verb downgraded from 'Oversee' to 'Review' in the bullet body to reflect the independent-review nature of the mandate rather than implying direct ownership of the underlying models.
- KEPT bullet 1 (sign-off authority) and bullet 3 (derivatives validation) — both are word-for-word from the tagged bullet library and are fully evidenced.

#### Experience — Moody's, Phase 2, Section 2 (Cash Flow / ETL)
- KEPT all four bullets — all are sourced from the tagged bullet library. The ETL framing ('extract/transform/load pipelines with embedded balance-and-control checks') is an accurate translation of the repo's 're-engineered manual spreadsheet workflows into scalable Python analytics pipelines' into the JD's own ETL vocabulary; it does not add new claims.
- NOTE: 'covering the retail-product behavioral mechanics central to non-trading balance sheet measurement' in bullet 3 was in the original draft. This is slightly JD-imported. Rewritten to 'covering the non-trading balance sheet behavioral mechanics relevant to IRRBB measurement' — still accurate to the repo (behavioral assumptions, prepayment logic) but no longer implies Saber has worked specifically with retail-product data, which the repo does not evidence.

#### Experience — Moody's, Phase 2, Section 3 (Reporting / Documentation)
- Section heading in original: 'Reporting, Attribution & Senior Stakeholder Communication.' Changed to 'ALCO Reporting, Attribution & Model Documentation' — better echo of JD theme 4 and 5; evidence base unchanged.
- Bullet 1: added 'consistent with ALCO reporting standards' — this is a framing phrase, not a new claim. The underlying activity (summaries for Heads of Risk, attribution of risk-measurement changes) is fully evidenced in the repo.

#### Section Headings — Relevance check
- Original heading 'Cash Flow, Behavioral & ETL Process Build' — 'Process Build' is slightly weak for a Manager/Director framing. Changed to 'Cash Flow Projection, Behavioral Assumptions & ETL Pipelines' — cleaner JD echo.
- All three headings now directly map to JD accountability themes: (1) IRRBB measurement, (2) ETL/behavioral/cash flow, (3) ALCO reporting and documentation.

#### Cover Letter — 4 fixes
- REMOVED: 'net interest income (NII) dimensions — mirroring the metrics central to bank Treasury IRRBB reporting.' Same reason as summary fix — NII as a named bank-treasury metric is not evidenced in the repo at the production level. Replaced with 'EVE and earnings dimensions.'
- REMOVED the original draft's cover letter was just a gap-disclosure note, not an actual letter body. Replaced entirely with a proper 300-350 word, 3-paragraph letter per Template A rules.
- Opening sentence anchors on the concrete capability claim (sign-off authority on comparable analytical outputs) per template rules — NOT a regulatory-calendar narrative.
- Paragraph 2 covers the specific capability stack matching the JD's five core themes.
- Paragraph 3 names a specific RBC hook ('breadth of the IRRBB Measurement mandate — domestic banking subsidiaries, CAD and US non-trading balance sheets, and the full ETL-to-ALCO-reporting chain') — this is accurate to the JD and avoids generic phrasing.
- Word count: ~290 words in the letter body (within 300-350 target; marginally short — can expand the paragraph-3 hook by one sentence if needed).

---

### Residual Honest Gaps to Own in Interview (NOT in the resume)

1. **No direct bank-treasury seat.** The JD requires '2+ years of relevant Treasury experience.' Saber's experience is vendor-side (Moody's) and advisory (Ortec). The analogous ALM measurement work is the honest bridge. Frame as: 'My mandate at Moody's is the analytical equivalent of the bank-treasury measurement function — I hold sign-off on the same outputs a bank's IRRBB team produces, delivered to institutional clients including bank treasuries. The in-house bank context is new; the measurement methodology is not.'

2. **Behavioral econometric modelling gap.** The JD explicitly calls out 'consumer behaviour econometric modeling and forecasting (prepayment, redemption, and pull-through)' as a must-support capability. The repo supports embedding prepayment logic and behavioral assumptions at the implementation and review level — it does NOT evidence personally calibrated econometric models fit to retail-product data. In interview: 'I have implemented and reviewed behavioral cash flow assumptions and prepayment logic in production ALM systems; the specific econometric calibration methodology for retail products is an area I would ramp on using RBC's existing framework.'

3. **QRM / Blue Prism / Vertica / Tableau.** None are in the repo. All are 'nice to have.' Python/SQL is the honest substitute for QRM and ETL tooling; flag willingness to learn the specific stack.

4. **NII as a named bank-treasury metric.** The repo supports earnings-based sensitivity analytics in an institutional/vendor context. If asked to describe NII measurement in a bank-treasury production context (transfer pricing, mismatch positions, client contractual risk), be clear that the Moody's work is at the institutional-client analytics layer, not the bank's own transfer-pricing engine.

5. **Title/comp band mismatch.** This is a Manager role (RBC's Manager is typically Senior Manager / Director equivalent in the market, but confirm the band). The Master Repo's floor is $160K base for Senior Manager. Confirm RBC's band before the offer conversation — do not anchor too high on the Director comp expectations in this process.