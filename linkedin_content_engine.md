# LinkedIn Content Engine — 12-Week Plan

> Saber Ayatollahi — positioning as the Toronto-based ALM / IRRBB / Model Governance practitioner with agentic-AI edge. Posts Mondays 07:30 EST. One post per week, 400-600 words, analytic voice, **zero humble-brags**.

> **Why:** LinkedIn inbound is the highest-leverage free marketing channel for Director-level Toronto finance. 12 thoughtful posts on OSFI E-23 / B-12 / LAR / IRRBB / ALM / agentic-AI-in-finance over 12 weeks = ~30% increase in recruiter InMails within 4 weeks based on peer-reported pipeline data. It also gives you something concrete to point interviewers to.

---

## 0. Profile setup (do this before Week 1)

### Headline (150 chars max)
Pick one; iterate monthly based on what's drawing clicks:
- **v-ALM:** `Director-level ALM & IRRBB specialist · CFA · Moody's Analytics · ex-Ortec LDI · preparing Canadian FIs for OSFI E-23 + B-12`
- **v-VEN:** `ALM & risk-platform practitioner · CFA · Moody's Analytics · building with agentic AI · bridging institutional clients and enterprise analytics`

### About (2,600 chars max — keep to ~300 words)

> I help institutional investors and Canadian financial institutions measure, validate, and govern the risks that show up on their balance sheets and in their portfolios.
>
> In my current role at Moody's Analytics I hold sign-off authority on valuation, sensitivity, and ALM outputs for multi-asset institutional portfolios — led the design of a multi-scenario cash flow projection engine, run IRRBB analytics under parallel and non-parallel rate shocks, and validate derivatives outputs at portfolio-level aggregates. Before Moody's I delivered IFRS 17 and IFRS 9 transformation at EY, and stochastic ALM / LDI studies for Canadian pension funds at Ortec Finance.
>
> I sit at the intersection of three things that rarely overlap at senior level in Canadian finance:
> — **ALM and balance-sheet-risk practitioner depth** (Moody's sign-off authority, Ortec LDI experience).
> — **Regulatory-driven transformation delivery** (EY IFRS 17/9, and now OSFI E-23 / B-12 / LAR readiness conversations with Big 6 and pension clients).
> — **Agentic-AI development workflows** (Claude Code, Cursor IDE) deployed in production code-review and validation scaffolding, reducing cycle time by an estimated 30–40%.
>
> CFA charterholder. Dual MSc (Financial Modelling + Chemical Engineering, Western University). Fluent in English, conversational French.
>
> I write here about OSFI E-23 and B-12 implementation, ALM and IRRBB methodology, LDI design under supply-constrained markets, and how agentic AI is changing model development and validation workflows. If you are building in any of these spaces, I'd welcome a conversation.

### Featured section
Pin (1) the Moody's cash flow projection engine explainer (Week 2 post), (2) the "what formal sign-off actually means" post (Week 5), and (3) the "agentic AI in production risk workflows" post (Week 6). These are the three best visible cards.

### Experience entries
Mirror the Master Repository exactly — no embellishment beyond the evidenced claims.

---

## 1. Weekly cadence

**Monday 07:30 EST:** post goes live. Schedule Sunday evening.

**After post goes live:**
- 07:45: comment on 3 other people's posts in your space (OSFI watchers, bank risk leads, pension-fund CIOs on LinkedIn).
- 12:00: check post engagement; respond to every comment under your own post within 2 hours.
- 19:00: 2-3 additional replies on comments; send LinkedIn connect requests to anyone who engaged but isn't yet a connection.

**After post is 48 hours old:** measure. Save the post URL + engagement count + best comment in `linkedin_engagement_log.md` (to create). Identify which connections are from TARGET COMPANIES (Scotia, RBC, BMO, CIBC, TD, BlackRock, Bloomberg, MSCI, S&P, pensions). Those become follow-up leads for warm-intro reachout.

---

## 2. 12-week post calendar

Each post has: (1) hook, (2) key arguments, (3) call-to-engagement. Draft takes ~90 min using Claude Code — ask for an outline, then edit for voice.

### Week 1 — "OSFI E-23 and the shape of Canadian model-risk hiring in 2026"

**Hook:** OSFI's final E-23 guidance took effect for planning purposes in September 2025, with compliance landing May 2027. Every Canadian FRFI is hiring ahead of it. Here's what I'm seeing.

**Arguments:**
- E-23 v2 scope explicitly covers AI/ML models — a first for Canadian guidance.
- Functional separation of model developer / owner / independent reviewer is now non-negotiable.
- Result: Model Risk Management headcount is growing at every Big 6 bank, at the Maple 8, and at Canadian insurers running IFRS 17 models.
- Question for the comments: which firms do you see scaling fastest, and which are still in denial?

### Week 2 — "Multi-asset cash flow projection engines — the LDI design under-appreciated tool"

**Hook:** LDI is usually discussed as duration-matching plus a hedge-ratio conversation. That's the mechanics. The harder question is liquidity-inside-the-match.

**Arguments:**
- Time-bucketed cashflow gap analytics (T+1 through multi-year) surface where funding pressure concentrates that a single-number metric hides.
- Behavioral cashflow assumptions (NMD run-off, prepayment elasticity, mortgage renewal behavior in Canada) dominate tail outcomes at 3-5 year horizons.
- Reverse-stress testing is underused in pension ALM vs banking — yet the pension fund case is identical: "what combination of events would force the plan off-LDI?"
- This is the engine I built at Moody's.

### Week 3 — "LDI meets IRRBB — where pension-fund ALM and bank balance-sheet risk converge"

**Hook:** The Canadian pension-fund LDI conversation and the bank IRRBB conversation are using different words for related problems. Both communities benefit from speaking across.

**Arguments:**
- Pension fund LDI = duration-match liabilities; use swaps/RRBs/real assets.
- Bank IRRBB = stabilize NII and EVE under rate shocks; use swaps/bonds/FTP.
- Both are portfolio-level risk-optimization problems under similar instruments and similar stresses — but with different accounting regimes (IFRS 17 for insurers, IFRS 9/ECL for banks, pension funded-ratio for DB plans).
- A CFA-plus-practitioner can move between these communities with more credibility than the specialist-in-one can.

### Week 4 — "IFRS 17 is done — now what? Post-implementation ALM opportunities at Canadian life insurers"

**Hook:** Canadian life insurers spent 2020-2023 on IFRS 17 implementation. Many now have the data infrastructure but not yet the insight infrastructure.

**Arguments:**
- CSM roll-forward is a data problem that's largely solved; the next phase is using CSM mechanics to drive investment strategy for long-duration liability matching.
- Measurement doesn't equal management: integrated asset-liability optimization under IFRS 17 is the next 3-year program at most insurers.
- This is where the ALM talent pool at insurers needs to grow. IFRS 17 knowledge + ALM practitioner depth + derivatives is the rare skill set.

### Week 5 — "What 'formal sign-off' actually means in bank model governance"

**Hook:** I get asked what sign-off authority on a multi-billion-dollar portfolio actually is. Here's the honest answer.

**Arguments:**
- Sign-off is a governance delegation, not a title. It attests to the defensibility of specific analytical outputs — curves, sensitivities, aggregation logic — not the investment strategy.
- It's an exercise in disciplined pushback: when an output is mathematically correct but economically unsupported, the sign-off holder is the person who holds the release.
- The E-23 functional-separation requirement is about this: the sign-off can't be compromised by reporting into the same function as model development.

### Week 6 — "Agentic AI in production risk workflows — what works, what doesn't"

**Hook:** I've been using Claude Code and Cursor IDE every day for about a year in institutional risk-analytics work. Here's what moved the needle and what didn't.

**Arguments:**
- Works: code review first-pass, documentation drafts, test scaffold generation, refactoring spreadsheet logic into clean Python, agent-based orchestration of multi-step validation runs.
- Doesn't work: methodology design (still requires a human with the mental model), curve calibration debates, client-facing narrative decisions.
- The delta: agents take 60% of the grunt work off the critical path. Senior judgment becomes *more* valuable, not less.
- For model governance teams worried about the E-23 AI/ML scope: treat your OWN agent workflows as a model — validate inputs, validate outputs, keep audit logs.

### Week 7 — "The 3 scenarios every IRRBB program needs to explicitly run"

**Hook:** Between parallel rate shocks and the 6 Basel IRRBB standardized scenarios, there are 3 non-standard cases that matter most for Canadian banks in 2026.

**Arguments:**
- Bull flattener (short hike + long rally) — the Canadian-mortgage squeeze scenario.
- Sticky-deposit run-off under rate hikes — what happens if the behavioral NMD core is 20% smaller than assumed?
- Convexity blowout — non-linear jump risk under a large shock, which EVE analytics can understate.
- None of these is novel; the issue is whether they're run *visibly* at ALCO, not just buried in an annex.

### Week 8 — "Calypso to modern platforms — what the migration actually looks like from the client side"

**Hook:** I spent a year migrating institutional clients off Calypso. Here's what the migration experience actually feels like from their end.

**Arguments:**
- Migration pain is rarely the tool; it's the configuration. Every client's legacy platform holds 10-15 years of undocumented business logic.
- A good migration captures that logic before it's re-implemented. A bad migration re-implements assumptions.
- For platform vendors (Aladdin, PFaroe, MSCI Barra, SS&C Algorithmics): the client-engagement seat matters more than the engineering seat, because migration quality depends on eliciting the right business logic from the client.

### Week 9 — "OSFI B-12 update — what it means for 2027 planning"

**Hook:** OSFI's B-12 IRRBB revision finished consultations in Q1. Here's what the direction tells us about 2027 bank planning cycles.

**Arguments:**
- Closer alignment with BCBS IRRBB standards (specifically around NMD modeling constraints, outlier test calibrations, and disclosure requirements).
- Implications for Canadian Big 6: re-validate NMD behavioral assumptions; expect outlier test to catch banks who were loose on deposit-duration assumptions.
- For the buy-side, B-12 alignment creates an arbitrage opportunity for liability-matching asset strategies against banks re-balancing.

### Week 10 — "Canadian mortgage renewal behavior — the underappreciated IRRBB driver"

**Hook:** Canadian 5-year-fixed mortgages are the most IRRBB-sensitive asset on every Big 6 balance sheet, and behavioral renewal is where model results diverge most.

**Arguments:**
- Contractual duration = 25-year amortization. Behavioral duration = ~2.5 years average.
- Renewal elasticity to rates is non-linear; the 2023-2024 renewal cohort is a rich dataset we haven't fully digested.
- Every Big 6 treasury is re-estimating. The methodology debate matters more than the headline EVE number.

### Week 11 — "LAR 2026 — the liquidity adequacy changes banks should be pre-building for"

**Hook:** OSFI's Liquidity Adequacy Requirements 2026 update is tightening both LCR and NSFR assumptions. Here's the shape of the build-out required.

**Arguments:**
- Tighter 30-day-outflow assumptions for certain wholesale funding classes.
- More granular disclosure of intra-day liquidity.
- Cash flow projection and behavioral liquidity analytics — the same tooling that supports IRRBB — is also the LAR build-out tooling.
- Good news for staff: LAR and IRRBB are now 70%+ overlapping infrastructure; build once, use twice.

### Week 12 — "Year in review — Toronto ALM / model-risk / vendor-platform hiring 2026"

**Hook:** Three weeks of active job search in the Toronto senior-finance market. Here's what I saw.

**Arguments:**
- Big 6 ALM/model validation hiring has never been stronger, driven by E-23 and B-12 timelines.
- Vendor-platform demand from Bloomberg, MSCI, S&P, BlackRock Aladdin, SS&C Algorithmics is rising as banks and pensions modernize.
- Pension-fund in-house teams continue their 10-year trend of bringing analytics in-house.
- Consulting (Big 4, Mercer, WTW, Oliver Wyman) is staffing up to meet the same regulatory demand.
- Meta-observation: the candidate profile in greatest shortage is **practitioner + regulatory-program + data-tooling**. Exactly the intersection this column has been writing about for 12 weeks.
- [Closing line that indicates, gently, you have landed somewhere — or if not, thanks the audience and signals continued engagement.]

---

## 3. Posting mechanics

- 400-600 words. Longer posts under-perform in LinkedIn's algorithm.
- 3-5 short paragraphs. Lots of white space. Lead with the hook.
- Include 2-3 hashtags at the bottom (not in-line): `#ALM #IRRBB #OSFI` / `#ModelRisk #CFA #RiskManagement` / `#FintechCanada #AssetLiabilityManagement`
- Tag nobody unless they're a co-author or reference. Tagging CEO-level people in a promotional way tanks engagement.
- Include 1 personal-voice sentence per post — a "here's how I've seen this" line. Pure analysis without voice reads like a McKinsey excerpt.

---

## 4. Engagement strategy

- Before your post goes live: comment on 3 posts by (a) Big 6 risk leads, (b) Maple 8 CIOs, (c) CFA Toronto society board. You show up in their feeds before they show up in yours.
- After your post: respond to every comment within 2 hours on launch day.
- Weekly: send 3 connection requests with personalized notes (150-300 chars) to people who engaged with your posts.
- Target LinkedIn SSI (Social Selling Index) of 60+. Track monthly.

---

## 5. Anti-patterns

- ❌ Humble-brag posts ("grateful to have been promoted to..." — everyone hates these).
- ❌ "Open to work" framed as victim narrative. Never.
- ❌ Motivational content without concrete substance.
- ❌ Re-sharing someone else's meme/graphic. Post original analysis or don't post.
- ❌ 4+ hashtags. Reads as spam.
- ❌ Lengthy disclaimers/disclosures. 1 sentence max if needed ("Views are my own.").
- ❌ Posting twice in the same week. Cadence discipline matters.

---

## 6. Engagement log template (create `linkedin_engagement_log.md` in Week 1)

```markdown
| Week | Date | Post topic | URL | Views | Likes | Comments | Reshares | New followers | New connections from target companies |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-05-04 | OSFI E-23 hiring | <url> | | | | | | |
```

Review monthly. If any post exceeds 5,000 views, that's a topic you build another post on next month.

---

*Last updated: 2026-05-03*
