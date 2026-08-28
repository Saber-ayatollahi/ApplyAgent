# RBC — Associate Director, Global Risk Analytics (Market Risk Analytics)
## Panel interview · **Fri Aug 28, 9:30–11:00am** · 90 min · IN PERSON
**200 Bay St — Royal Bank Plaza, SOUTH tower, 11th floor**
**On arrival: call Eric at 226-260-0138**

Applied 2026-08-15 (also 2026-05-29) · Posting closed Aug 25 · Platform: Group Risk Management

---

## 1. The panel — four people

| Who | What we know | Likely angle |
|---|---|---|
| **Huameng "Eric" Jia, PhD** | **PhD Actuarial Science, Waterloo (2020)** — thesis *Multivariate Risk Measures for Portfolio Risk Management*. Associate Director, GRA. Your main contact. | **Theory.** Risk-measure properties, coherence/subadditivity, CVaR, risk contribution & capital allocation. |
| **Lei Han, CFA** | Director, RBC CM. PhD candidate, Economics (SFU). Skills: derivatives, options, financial modeling. | Probable **hiring manager**. Derivatives pricing, judgment, seniority fit. |
| **Denise (Dehui) Yu** | RBC Global Risk Analytics | Team fit, methodology practice |
| **Ann Wan** | No public profile found | Unknown — possibly HR or team |

> Eric is a **peer AD**, not your boss. Peer panels probe *how you reason*, not what you memorised.
> That favours you — review-and-challenge is your strongest instinct.

**Eric's thesis, in one line each:**
- Ch.2 — multivariate **CVaR**; proves positive homogeneity, translation invariance, **subadditivity**
- Ch.3 — **capital allocation**: optimal total capital *and* allocation to each risk unit simultaneously
- Ch.4 — multivariate shortfall risk measure from cumulative prospect theory

**→ Your Ortec work is the applied version of his theory.** Lead with it.

---

## 2. Opening pitch (~60–75 sec)

~7 years across market and balance-sheet risk. At **Moody's Analytics**, delegated **sign-off
authority** on valuation, sensitivity and ALM outputs for institutional portfolios ($5–25bn per
engagement); independently review **yield-curve construction, spread calibration** and
cross-asset consistency; sit on the **model governance committee**. Before that **Ortec Finance** —
**VaR/CVaR portfolio optimization on GLASS with risk decomposition and contribution-to-risk
budgeting**, plus **stochastic/Monte Carlo scenario generators**. **EY** — IFRS 17/9.
**Python (pandas/NumPy/SciPy) + SQL**; CFA + dual MSc.

**Pivot:** "My market-risk depth is measurement, decomposition and independent validation —
on institutional and balance-sheet portfolios rather than a trading book."

---

## 3. THE question — VaR vs ES coherence

*Near-certain, given Eric's thesis. Know this cold.*

- **VaR** = the α-quantile of the P&L distribution. Says **nothing about losses beyond it**.
- **VaR is NOT subadditive** → not a coherent risk measure. VaR(A+B) can exceed VaR(A)+VaR(B),
  i.e. it can **penalise diversification** — economically indefensible.
- **ES / CVaR** = expected loss *conditional on* breaching VaR. **Subadditive → coherent.**
- Coherence axioms: monotonicity, translation invariance, positive homogeneity, **subadditivity**.
- **This is exactly why FRTB replaced VaR 99% with ES 97.5%.**
- ES 97.5% ≈ VaR 99% under normality — but ES is far more conservative with fat tails.
- Trade-off to name: **ES is harder to backtest** (not elicitable in the same way), which is why
  **backtesting is still done on VaR** even under FRTB.

**Risk contribution / Euler allocation** — Eric's Ch.3 territory:
- Contributions should **sum to total risk** (full allocation) — Euler/gradient allocation gives this
- For ES: contribution of position *i* = its expected loss **conditional on the tail event**
- Diversification benefit = sum of standalone risks − portfolio risk; allocation decides who gets credit

---

## 4. VaR mechanics

**Three approaches + trade-offs**
- **Historical simulation** — actual historical factor moves (250–500d), empirical quantile.
  No distributional assumption; bounded by sample; **ghost effect** when a big move exits the window.
- **Monte Carlo** — calibrate processes, simulate, reprice. Handles optionality/non-linearity;
  costs model risk + compute.
- **Parametric / delta-normal** — sensitivities + covariance. Fast; breaks on convexity.

**Lookback window** — short = responsive but noisy/procyclical; long = stable but slow. Basel floor 1yr.

**Risk-factor selection** — curve tenors/key rates, credit spreads, FX, equity (index + idio),
vol surfaces. Granularity (basis risk) vs parsimony (estimation stability). Proxy illiquid factors.

**Full reval vs sensitivity-based** — full reval accurate for convexity/exotics but expensive;
delta-gamma is a Taylor approximation that degrades on large moves. Most banks run a hybrid.

**Backtesting** — VaR vs **hypothetical/clean P&L** (position held constant) and **actual P&L**.
At 99% over 250 days expect ~2.5 exceptions.
**Basel traffic light:** green 0–4 (mult 3.0) · yellow 5–9 (3.4–3.85) · **red 10+ (4.0, approval at risk)**.

---

## 5. SVaR

Same model, **different calibration window**: a continuous **12-month period of significant stress
relevant to the portfolio**.

- **Selection:** run the *current* portfolio through candidate windows; pick the one that
  **maximises VaR**; document; **re-review annually / after material portfolio change**.
- Candidates: 2008–09 GFC, 2011 Eurozone, Mar 2020, **2022 rates/gilt shock** (often worst for a
  rates-heavy book).
- **Capital ≈ max(VaR₍t₋₁₎, m·VaR₆₀avg) + max(SVaR₍t₋₁₎, m·SVaR₆₀avg)**, m ≥ 3 + backtest add-on.
  Additive → Basel 2.5 roughly doubled–tripled market risk capital.
- **Purpose: anti-procyclicality** — capital can't evaporate in calm markets.

**Hard parts (say these — they show depth):**
- **Data availability** — post-LIBOR transition there is **no SOFR/CORRA history in a 2008 window**;
  must proxy old benchmark + spread, and defend the proxy as a model limitation.
- **Full search is expensive** → approximate with reduced factor set / proxy portfolio, then validate.
- **Window instability** → capital volatility + governance question on re-selection.
- **SVaR is static** → in a real crisis current VaR can exceed SVaR; stressed term stops binding.

**Your bridge:** reverse-stress testing at Moody's is the same search logic inverted — solve for
what breaks the constraint, then judge plausibility.

---

## 6. CCR — concepts only, no delivery claim

Exposure is **stochastic and bilateral**. Simulate paths → reprice → aggregate by **netting set**
→ apply collateral (threshold, MTA, **MPOR**).

- **EE** — mean exposure at time t · **EPE** — time-weighted average EE (feeds Basel EAD)
- **PFE** — high quantile (95/97.5%) of exposure at t; used for **limits**
- **Wrong-way risk** — exposure rises as counterparty credit deteriorates
- **CVA** — market value of counterparty credit risk (xVA family)
- **SA-CCR** replaced CEM for standardised EAD

---

## 7. FRTB headline

Replaces Basel 2.5 wholesale.
1. **ES 97.5% replaces VaR 99%** (coherence + tail capture)
2. **Liquidity horizons** 10/20/40/60/120d by risk-factor class
3. Hard **trading/banking book boundary**
4. **IMA approval per desk** — must pass **backtesting** + **PLA** (risk-theoretical vs hypothetical
   P&L; Spearman correlation + KS statistic; green/amber/red). Fail → desk pushed to SA.
5. **NMRF** — factors failing real-price observability (~24 obs/yr, no >1mo gap) get separate
   stressed capital. Often a large, painful line.
6. **Rebuilt SA** — sensitivities-based (delta/vega/curvature) + **DRC** + **RRAO**; floor & fallback.

**Canada:** OSFI **CAR Guideline Chapter 9 (Market Risk)**. CAR 2026 effective **Nov 1 2025** for
Oct-31 fiscal year-end institutions (**= RBC**); CAR 2027 consulted on earlier this year.

**Why the JD still says VaR/SVaR:** under FRTB, ES drives **capital** but VaR remains for
**desk backtesting, limits and management reporting**. GRA genuinely runs both worlds.

---

## 8. Gap scripts — do NOT overclaim

**CCR / SVaR production / VaR backtesting:**
> "My depth is measurement, decomposition and independent validation on institutional and
> balance-sheet portfolios. I haven't built CCR exposure engines or run SVaR calibration in
> production — I'd rather be straight about that. The simulation design, risk-factor selection,
> calibration review and validation mechanics are the same, and that's what I'd bring on day one."

**C++/C#:** Python (pandas/NumPy/SciPy) + SQL daily, R and MATLAB historically. No production C++.
Say it plainly; note the JD lists "Python/C++/C#" as alternatives, not all three.

**Trading book:** buy-side and balance-sheet, not a desk. Frame as the domain layer to learn.

**"Delegated sign-off as an Assistant Director?"** — Moody's delegates sign-off **by role, not
title**; IC-with-independent-review authority; attests to defensibility of specific analytical
outputs, not portfolio strategy.

---

## 9. Ask them

1. How is the split drawn between **methodology specification and prototype implementation** —
   does the AD own the prototype through to the Risk IT handoff, or hand off at spec?
2. Where's the biggest methodology pressure right now — the **VaR/SVaR framework**, **market data
   and scenario services**, or **CCR coverage**?
3. How far along is the **IMA vs SA split across desks** — is the pain more in **PLA pass rates**
   or **NMRF coverage**?
4. *(For Eric)* Are risk **contributions computed on a Euler/coherent basis**, and how is
   **diversification benefit** allocated back to the desks?
5. What does the **approval path to the senior management committee** look like — how many
   methodology proposals a year, and what typically sends one back?

---

## 10. Comp — don't raise it

Not a panel topic; it goes through the recruiter after they decide. If pushed:
> "Mid-to-high $100s base plus incentive, in line with market for AD-level quant risk."

Estimate: **base $145–175K + 15–20% bonus** (~$170–205K total). **Never state the Moody's number.**

---

## 11. Tonight / tomorrow morning

- [ ] Re-read this + the interview brief in the application folder
- [ ] Say the VaR-vs-ES coherence answer **out loud** twice
- [ ] Re-read your own Ortec bullets — that's your credibility anchor
- [ ] Print 4 copies of the resume (four-person panel) + photo ID for security
- [ ] 200 Bay St, **SOUTH tower**, 11th floor — arrive **9:15**, call **226-260-0138**
- [ ] No competing offers — don't imply otherwise
