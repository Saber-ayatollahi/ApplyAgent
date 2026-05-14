# LinkedIn Content Engine — 12-Week Plan

> Saber Ayatollahi — positioning as the Toronto-based ALM / IRRBB / Model Governance practitioner with agentic-AI edge. Posts Mondays 07:30 EST. One post per week, 400-600 words, analytic voice, **zero humble-brags**, **zero regulatory-calendar grandstanding**.

> **Why:** LinkedIn inbound is the highest-leverage free marketing channel for Director-level Toronto finance. 12 thoughtful posts over 12 weeks on what formal model sign-off actually entails, how cash-flow-engine design plays out in practice, LDI mechanics, methodology debates worth having, and agentic-AI in production risk workflows — that's the credibility stack. It gives you something concrete to point interviewers to, and it earns the right to comment in senior threads.

---

## 0. Profile setup (do this before Week 1)

### Headline (150 chars max)
Pick one; iterate monthly based on what's drawing clicks:
- **v-ALM:** `Director-level ALM & IRRBB specialist · CFA · Moody's Analytics · ex-Ortec LDI · sign-off authority on multi-asset institutional portfolios`
- **v-VEN:** `ALM & risk-platform practitioner · CFA · Moody's Analytics · building with agentic AI · bridging institutional clients and enterprise analytics`

### About (2,600 chars max — keep to ~300 words)

> I help institutional investors and Canadian financial institutions measure, validate, and govern the risks that show up on their balance sheets and in their portfolios.
>
> In my current role at Moody's Analytics I hold sign-off authority on valuation, sensitivity, and ALM outputs for multi-asset institutional portfolios — led the design of a multi-scenario cash flow projection engine, run IRRBB analytics under parallel and non-parallel rate shocks, and validate derivatives outputs at portfolio-level aggregates. Before Moody's I delivered insurance-accounting transformation at EY, and stochastic ALM / LDI studies for Canadian pension funds at Ortec Finance.
>
> I sit at the intersection of three things that rarely overlap at senior level in Canadian finance:
> — **ALM and balance-sheet-risk practitioner depth** (Moody's sign-off authority, Ortec LDI experience).
> — **Client-side delivery across banks, pensions, insurers, and asset managers** (EY, Ortec, Moody's client book).
> — **Agentic-AI development workflows** (Claude Code, Cursor IDE) deployed in production code-review and validation scaffolding, reducing cycle time by an estimated 30–40%.
>
> CFA charterholder. Dual MSc (Financial Modelling + Chemical Engineering, Western University). Fluent in English, conversational French.
>
> I write here about ALM and IRRBB methodology, what formal sign-off authority actually entails day to day, LDI design under supply-constrained markets, and how agentic AI is changing model development and validation workflows. If you are building in any of these spaces, I'd welcome a conversation.

### Featured section
Pin (1) the Moody's cash flow projection engine explainer (Week 2 post), (2) the "what formal sign-off actually means" post (Week 5), and (3) the "agentic AI in production risk workflows" post (Week 6). These are the three best visible cards.

### Experience entries
Mirror the Master Repository exactly — no embellishment beyond the evidenced claims.

---

## 1. Weekly cadence

**Monday 07:30 EST:** post goes live. Schedule Sunday evening.

**After post goes live:**
- 07:45: comment on 3 other people's posts in your space (bank risk leads, pension-fund CIOs, platform-vendor Toronto leads on LinkedIn).
- 12:00: check post engagement; respond to every comment under your own post within 2 hours.
- 19:00: 2-3 additional replies on comments; send LinkedIn connect requests to anyone who engaged but isn't yet a connection.

**After post is 48 hours old:** measure. Save the post URL + engagement count + best comment in `linkedin_engagement_log.md` (to create). Identify which connections are from TARGET COMPANIES (Scotia, RBC, BMO, CIBC, TD, BlackRock, Bloomberg, MSCI, S&P, pensions). Those become follow-up leads for warm-intro reachout.

---

## 2. 12-week post calendar

Each post has: (1) hook, (2) key arguments, (3) call-to-engagement. Draft takes ~90 min using Claude Code — ask for an outline, then edit for voice.

### Week 1 — "What formal model sign-off authority actually means in day-to-day ALM"

**Hook:** I get asked what sign-off authority on a multi-billion-dollar portfolio actually is. Here's the honest answer, drawn from four years of doing it.

**Arguments:**
- Sign-off is a governance delegation, not a title. It attests to the defensibility of specific analytical outputs — curves, sensitivities, aggregation logic — not the investment strategy.
- It's an exercise in disciplined pushback: when an output is mathematically correct but economically unsupported, the sign-off holder is the person who holds the release.
- The hard part is not the math. It's writing the escalation that survives the next ALCO.
- Question for the comments: for those of you with sign-off, what's the hardest call you've made in the last year?

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
- Both are portfolio-level risk-optimization problems under similar instruments and similar stresses.
- A CFA-plus-practitioner can move between these communities with more credibility than the specialist-in-one can.

### Week 4 — "Where Canadian life-insurer ALM teams are under-resourced right now"

**Hook:** After several years of insurer accounting-system builds, most insurers have the data infrastructure. Few have caught up on the insight infrastructure.

**Arguments:**
- Measurement doesn't equal management. Running the liability book is a daily exercise in cash-flow projection, derivative-overlay design, and scenario stress — not a reporting problem.
- Integrated asset-liability optimization is the next 3-year program at most Canadian life insurers.
- This is where the ALM talent pool at insurers needs to grow. Insurance-accounting fluency + ALM practitioner depth + derivatives is the rare combination.

### Week 5 — "Why documentation is 60% of the job at senior risk levels"

**Hook:** Junior analysts sometimes think senior risk roles are 80% quant. They're 60% writing.

**Arguments:**
- At Director level, the artefact that survives is the memo — the methodology doc, the validation report, the ALCO paper. These are what auditors, regulators, and successor staff read.
- The job of the senior practitioner is to make sure the memo outlives the author's tenure.
- Writing discipline is more load-bearing than the quantitative technique it documents. Every strong risk shop I've worked with has strong writers at the top.
- One pattern: every methodology debate closes with "let's land the memo" — not "let's re-run the model."

### Week 6 — "Agentic AI in production risk workflows — what works, what doesn't"

**Hook:** I've been using Claude Code and Cursor IDE every day for about a year in institutional risk-analytics work. Here's what moved the needle and what didn't.

**Arguments:**
- Works: code review first-pass, documentation drafts, test scaffold generation, refactoring spreadsheet logic into clean Python, agent-based orchestration of multi-step validation runs.
- Doesn't work: methodology design (still requires a human with the mental model), curve calibration debates, client-facing narrative decisions.
- The delta: agents take 60% of the grunt work off the critical path. Senior judgment becomes *more* valuable, not less.
- One practical note for governance teams: treat your OWN agent workflows as a model — validate inputs, validate outputs, keep audit logs.

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

### Week 9 — "NMD modelling — the quietest methodology debate on every bank's ALM desk"

**Hook:** If you want to know how a bank really thinks about IRRBB, don't look at the parallel DV01. Look at the non-maturity-deposit (NMD) behavioral model.

**Arguments:**
- Every Canadian Big 6 has a view on NMD core stability, run-off elasticity to rates, and pass-through on demand-deposit pricing. These are typically private methodology, not disclosed.
- Two banks with the same rate shock can produce very different EVE results based purely on NMD assumptions.
- When interviewers want to assess your ALM depth, they ask about NMD — specifically how you'd push back on an aggressive core-stability assumption.
- One practical heuristic: the 2022-2024 rate-hike cycle is a rich dataset. Use it to re-calibrate.

### Week 10 — "Canadian mortgage renewal behavior — the underappreciated IRRBB driver"

**Hook:** Canadian 5-year-fixed mortgages are the most IRRBB-sensitive asset on every Big 6 balance sheet, and behavioral renewal is where model results diverge most.

**Arguments:**
- Contractual duration = 25-year amortization. Behavioral duration = ~2.5 years average.
- Renewal elasticity to rates is non-linear; the 2023-2024 renewal cohort is a rich dataset we haven't fully digested.
- Every Big 6 treasury is re-estimating. The methodology debate matters more than the headline EVE number.

### Week 11 — "Liquidity analytics and IRRBB share more infrastructure than most teams admit"

**Hook:** Banks often build liquidity analytics and IRRBB analytics as separate programs. The underlying cash-flow engine is largely the same — you save a year by building once.

**Arguments:**
- Both depend on behavioral cash-flow projection under rate and deposit-retention assumptions.
- Both use the same bucketed-gap view of the balance sheet, with different stress overlays.
- Pension-fund LDI analytics, bank liquidity analytics, and bank IRRBB analytics overlap on 70%+ of infrastructure — build once, use three times.
- The organizational challenge is not technology; it's getting Treasury and Market Risk to agree on one source of truth.

### Week 12 — "Year in review — Toronto ALM / model-risk / vendor-platform hiring 2026"

**Hook:** Three months of active job search in the Toronto senior-finance market. Here's what I saw.

**Arguments:**
- Big 6 ALM and model-validation hiring has been consistently active. Director-level roles take 3-4 months from posting to offer.
- Vendor-platform demand from Bloomberg, MSCI, S&P, BlackRock Aladdin, SS&C Algorithmics is rising as banks and pensions modernize.
- Pension-fund in-house teams continue their 10-year trend of bringing analytics in-house.
- Consulting (Big 4, Mercer, WTW, Oliver Wyman) is staffing up to meet the same demand.
- Meta-observation: the candidate profile in greatest shortage is **practitioner + transformation-delivery + data-tooling**. Exactly the intersection this column has been writing about for 12 weeks.
- [Closing line that indicates, gently, you have landed somewhere — or if not, thanks the audience and signals continued engagement.]

---

## 3. Posting mechanics

- 400-600 words. Longer posts under-perform in LinkedIn's algorithm.
- 3-5 short paragraphs. Lots of white space. Lead with the hook.
- Include 2-3 hashtags at the bottom (not in-line): `#ALM #IRRBB #BalanceSheetRisk` / `#ModelRisk #CFA #RiskManagement` / `#FintechCanada #AssetLiabilityManagement`
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
| 1 | 2026-05-04 | Formal sign-off authority in ALM | <url> | | | | | | |
```

Review monthly. If any post exceeds 5,000 views, that's a topic you build another post on next month.

---

*Last updated: 2026-05-06 — 12-week calendar rebuilt around capability-led topics (sign-off authority, cash-flow engine design, methodology debates, agentic AI in production). Regulatory-calendar framing removed.*
