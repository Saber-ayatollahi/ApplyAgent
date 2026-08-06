# HOOPP — Sr. Manager, Risk Analytics & Modelling (JR102444)

**Phone screen prep + comparison vs. BlackRock Aladdin Solutions Engineer.**
Reports to: Senior Director, Risk Analytics & Modelling. Location: Toronto (hybrid).

---

## 1. What the role actually is

Buy-side **total-fund quantitative risk**. Per the JD, you would:

- Develop & maintain risk models across **all asset classes** — derivatives, credit, fixed income, equities, **and alternatives** (PE, real assets, infra).
- Build **new models and risk methodologies**; run and **validate** existing ones.
- Operate and govern **HOOPP's risk management system** (their platform + model inventory).
- Work on **model-governance** projects — documentation, controls, methodology sign-off.

This is *not* a trading-desk capital seat (no FRTB/CCR-xVA machinery). It's model development + validation + governance for an asset owner. **That is squarely your wheelhouse.**

---

## 2. Why you fit (your evidence → their asks)

| HOOPP asks | Your proof |
|---|---|
| Cross-asset risk models (derivatives, credit, FI, equity, alts) | Moody's: **sign-off authority** on valuation/sensitivity/ALM outputs across multi-asset institutional portfolios ($50bn+ book); validate derivatives pricing (rates/FX/inflation) + cross-asset interactions |
| Develop new models & methodologies | Led design/build of enterprise **multi-asset cash-flow projection engine** (base/stress/reverse-stress); time-bucketed liquidity-gap analytics |
| Run & validate existing models | Independent review of curve construction, spread calibration, stress behavior pre-production; escalate outputs lacking economic defensibility |
| Model governance | Operate inside Moody's model-governance framework; know **OSFI E-23** (dev/owner/validator separation, AI/ML scope) cold |
| Alternatives / total-fund view | Ortec: **LDI, SAA/TAA, VaR/CVaR portfolio optimization, risk decomposition & attribution** on GLASS; UPP merger model (duration/inflation/currency/leverage overlays) |
| Modern tooling | Python pipelines replacing spreadsheet workflows; **agentic AI dev** (Claude Code/Cursor) — a differentiator most pension quants don't have |

**One-line positioning:** *"I've spent my career on the model side of exactly this — cross-asset valuation, sensitivity and ALM sign-off at Moody's, and before that LDI and total-fund risk optimization at Ortec for pension clients. HOOPP is where those two threads meet."*

---

## 3. Honest gaps — and how to frame them

- **Alternatives modelling depth** (illiquid PE/infra risk) — you've touched real assets via LDI/total-fund work but not built bespoke alt-asset risk models. Frame as *fast-ramp*: "I've modelled the liquid book end-to-end and the total-fund aggregation; alts is the layer I'm most excited to go deeper on."
- **HOOPP's specific platform** — you don't know their in-house system, but you've onboarded/validated on PFaroe, Calypso, GLASS, Moody's — "platform-agnostic, I learn risk systems fast because I've implemented several."
- Do **not** volunteer trading-desk-capital (FRTB/CCR) as a gap — it's not in this JD. If asked, be honest it's the one adjacent area you've not owned.

---

## 4. Phone screen game plan

A first-round phone screen (recruiter or the Senior Director) is **~30 min**, mostly: motivation, career narrative, high-level technical sanity-check, comp, logistics. Your job: be warm, concise, and unmistakably a fit. Nail these:

1. **Tight career arc (60–90 sec):** Chem Eng → Financial Modelling MSc → Ortec (pension LDI/total-fund risk) → EY (IFRS 17/9) → Moody's (multi-asset model sign-off) + CFA. Land on: *"I want to move from advising/validating asset owners to owning the risk models inside one — HOOPP is the top of that list."*
2. **Why HOOPP specifically** — Canada's strongest DB plan, LDI/liability-aware culture, and a risk-modelling team that spans the whole fund. Genuine: you've spent years serving pensions from the outside; you want in.
3. **One crisp technical proof** — have Story 1 (cash-flow engine) and Story 2 (model-output escalation) ready.
4. **Comp** — see §6. Don't lead with a number.
5. **Logistics** — Toronto, no sponsorship needed, ~4 weeks notice.

---

## 5. Likely questions + your answers

**"Walk me through your background."** → Career arc above. End on the pension pull.

**"Why leave Moody's?"** → Growth, not escape: *"I've had strong impact on the model/validation side serving institutional clients. I want to own risk models end-to-end inside an asset owner, where the models drive real allocation and hedging decisions — not just client deliverables."* (No badmouthing.)

**"Tell me about a risk model you built or validated."** → Story 1 or 2. Emphasize methodology judgment + economic defensibility, not just code.

**"How do you approach validating a model you didn't build?"** → Independent challenge vs. audit; check methodology assumptions, calibration, edge/stress behavior, economic sense; reproduce independently; document limitations. Cite E-23 dev/owner/validator separation.

**"How would you think about risk on alternatives / illiquid assets?"** → Honest + structured: proxy/factor mapping, stale-pricing and smoothing adjustments (de-smoothing returns), liquidity-adjusted risk, look-through where possible, scenario overlays. Show you know the *problems* even if you haven't built HOOPP's solution.

**"What's your Python / tooling like?"** → pandas/NumPy pipelines, validation scaffolding, plus agentic AI dev workflows (Claude Code/Cursor) that cut cycle time 30–40%. Modern, auditable.

**"LDI / hedge ratio at a pension?"** → §1.5 of `interview_prep.md` — liability duration/convexity, hedge-ratio target, instrument choice under collateral regime, rebalancing tolerance, hedge-effectiveness reporting. Note the Canadian RRB supply constraint.

---

## 6. Comp handling (phone screen)

- Your band: **Senior Manager floor ~$160K base**; realistic total cash **~$200–280K CAD** + HOOPP's exceptional DB pension. (Aggregator "$92–120K" is a low generic estimate — ignore it.)
- If asked for expectations: *"I'm calibrating to the Toronto pension Senior Manager / Director market — happy to get specific once we're aligned on scope. Can you share the band for the role?"*
- Weight the **DB pension** heavily in your mental math — it's a large, real add most private-sector roles don't match.

---

## 7. Questions to ask them

1. "How is the Risk Analytics & Modelling team split — model development vs. validation vs. platform/governance?"
2. "What's the current hedge-ratio philosophy, and how is it adjusted when duration-matched supply is constrained?"
3. "How is the team handling risk modelling for the alternatives book relative to the liquid book?"
4. "What's the biggest methodology debate the team has had recently, and how did it resolve?"
5. "What does success look like at 6 and 12 months?"
6. "What are the next steps and timeline?"

---

## 8. HOOPP (JR102444) vs. BlackRock Aladdin Solutions Engineer

| Dimension | **HOOPP — Sr. Mgr, Risk Analytics & Modelling** | **BlackRock — VP, Solutions Engineering (Aladdin)** |
|---|---|---|
| **Lane** | Spearhead B — pension / buy-side total-fund risk | Spearhead A — vendor-platform / solutions engineering |
| **Core work** | Build/validate/govern cross-asset risk models *inside* an asset owner | Configure/implement/advise on Aladdin *for* institutional clients; pre-sales + delivery |
| **Day-to-day** | Quant modelling, validation, methodology, governance — heads-down + committee | Client-facing: workshops, solutioning, implementation, demos, stakeholder mgmt |
| **Fit to your core** | **Very high** — direct model/validation/LDI match | **High** — you *are* the buyer; "I've built the competing platform and I know your clients" |
| **Differentiation / competition** | Strong, but competes vs. other pension quants | **Most differentiated** — least competition; your Moody's + client-facing blend is rare |
| **Comp shape** | Base + bonus + gold DB pension; ~$200–280K cash + pension | Higher cash/variable, revenue-adjacent; vendor VP band ~$260–400K TC, less/no DB |
| **Career trajectory** | Deep pension-risk expert → Director/Head of Risk Analytics | Platform/commercial → Director/MD, client org; broader, more commercial |
| **Energy match** | Rewards depth, rigor, quiet mastery | Rewards range, communication, relationship-building (you said you *like* this work) |
| **Status of lead** | **Live — phone screen requested now** | Warm champion (Mohsen Namazi), awaiting reply since mid-June |

### Verdict

**Run both — they're complementary, not competing.** HOOPP is the concrete, in-hand opportunity in your deepest-evidence lane; it's the one to *win the process on right now*. BlackRock is the higher-differentiation, higher-ceiling bet where your profile is rarest — but it's stalled on their timeline, not yours.

Tactically: **prosecute HOOPP hard** (it's live and it's a genuine fit), and **use momentum from it to re-engage Mohsen** — a live process elsewhere is a legitimate, non-needy reason to send that keep-in-touch note. An offer or advanced stage at HOOPP also strengthens any BlackRock comp conversation.

If forced to rank on *fit + winnability today*: **HOOPP**. On *differentiation + ceiling*: **BlackRock**. The barbell says: don't choose — advance both.
