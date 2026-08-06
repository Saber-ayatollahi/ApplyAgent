## Likely Technical Questions

**1. Walk me through how you would measure and report IRRBB for the banking book - EVE vs NII.**
> At Moody's I oversee duration and sensitivity analytics under parallel and non-parallel rate shocks aligned with IRRBB standards analogous to OSFI B-12 / Basel. EVE captures the present-value impact on equity from re-pricing the full balance sheet under shock; NII captures the short-horizon earnings impact from re-pricing gaps over a rolling window. The two are complementary - EVE is long-term economic, NII is short-term earnings - and risk-appetite frameworks typically set limits on both. Behavioral assumptions on non-maturity deposits and prepayments materially drive both metrics.

**2. Describe a time you challenged a model output that looked correct but was economically wrong.** (STAR Story 2)
> A client run produced sensitivities that passed internal checks but didn't square with their economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, and isolated a curve-calibration edge case at the short end. Escalated to product owners and the client's Head of Risk, walked through remediation. Release slipped 48 hours but the client avoided acting on wrong numbers, and the defect was captured in validation tests upstream.

**3. How would you design a risk-appetite framework for a non-trading banking book?**
> Start with the metrics the board can govern to - EVE sensitivity to a +/-200bp shock, NII-at-risk over 12 months, key-rate duration limits, and basis/optionality sub-limits. Calibrate tolerances to capital and earnings volatility the firm is willing to absorb. Cascade enterprise limits into business-line limits (treasury, wealth, regional units) with consistent aggregation. Anchor monitoring on routine breach/utilization reporting and trigger-based escalation. I have done analogous calibration on the buy-side via VaR/CVaR limits at Ortec.

**4. How do behavioral assumptions (NMDs, prepayments) affect EVE/NII, and how do you stress them?**
> They are the single biggest discretionary input - small changes in deposit beta or assumed core-deposit life shift EVE materially. I have embedded behavioral cash flow assumptions and prepayment logic into the Moody's cash flow engine. The discipline is to (a) document the model, (b) stress the assumption itself as a sensitivity (e.g., +/-20% on deposit life), and (c) reverse-stress: ask what assumption set would breach the limit, and is that plausible.

**5. Walk me through your cash flow projection engine and how it would help an ALM reporting team.**
> Multi-asset engine producing base, stress, and reverse-stress projections across time buckets from T+1 through multi-year. Configurable behavioral overlays, prepayment logic, macro stress layers. Python pipeline replacing spreadsheets, with logging and auditability. For an ALM team, the value is: same engine drives EVE, NII, liquidity gap, and stress reporting - one source of truth, consistent aggregation across business lines and legal entities, which is exactly the consolidation pain RBC's JD describes.

## Sharp Questions for Saber to Ask

1. How is the ALM oversight team organized between enterprise consolidation and the regional/US operating unit coverage - and where would this role sit on that axis on day one?
2. The JD mentions partnership with Risk Modernization and ALM Transformation - what does the target-state reporting infrastructure look like, and how mature is the migration off legacy Excel/Tableau workflows?
3. How does BSLR interact with Treasury on hedging decisions - is it pure second-line oversight, or is there a constructive-challenge model on hedge design and limit calibration?

## The One Competency Gap to Prepare For

**Big-6 banking-book balance-sheet experience.** Saber's IRRBB depth is genuine but practitioner-side (Moody's clients, Ortec pension/insurer mandates), not directly inside a Schedule I treasury function. Expect probing on Canadian banking-book specifics: non-maturity deposit modelling for retail/commercial deposits at scale, prepayment behavior on residential mortgages, FTP mechanics, and US sub-entity consolidation. Pre-load the OSFI B-12 (Q1 2026 consultation direction) and Basel IRRBB standards - frame answers as 'I have applied this analytically on the analytics-vendor side and on pension/insurer balance sheets; the translation to a Schedule I retail/commercial book is in the data inputs and behavioral assumptions, not the framework.'