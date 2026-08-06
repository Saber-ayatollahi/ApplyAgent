# US-Remote Job-Search Game Plan — Saber Ayatollahi

**Goal:** Leave current role; land a remote role with a US company/startup while staying in Canada.
**Constraint:** No US visa / no sponsorship. (You stay physically in Canada, so *no US work authorization is needed at all.*)
**Created:** 2026-06-19 · review weekly.

---

## 0. The key insight that makes this work

Because you'd work **remotely from Canada**, this is not a visa problem — it's a *hiring-mechanism* problem. A US company brings you on one of three ways:

1. **Employer of Record (EOR)** — Deel, Remote.com, Oyster, Borderless. The EOR is your legal employer in Canada, runs payroll, issues a T4. **This is the standard route** when the company has no Canadian entity.
2. **Contractor** — you invoice them (sole-prop or incorporated). Faster to start, but watch CRA misclassification rules for full-time work.
3. **Their existing Canadian entity** — biggest US firms already have one.

Your job is to find roles where the company will do (1), (2), or (3). You are not asking anyone to sponsor a visa — **lead with that**, because it removes the single biggest reason US postings filter out non-US applicants.

**Two structural advantages you have:**
- **Eastern Time** — you're already in the US business day. Huge for "remote (US/Americas)" teams.
- **CFA + dual MSc + Moody's pedigree** travels globally and reads as senior to US fintech/risk-tech.

---

## 1. The repositioning (Canada → US-remote)

Your current pipeline targets Canadian **banks and pensions** (RBC, HOOPP, Scotiabank, BMO, TD, CPP, OMERS…). That lane barely exists as remote-from-Canada in the US — regulated bank ALM/risk roles are onshore and on-site. So the center of gravity shifts:

| Your lane | US-remote viability | Where it lands |
|---|---|---|
| **Vendor-Platform / Solutions Engineering** | **Highest** — risk-tech is distributed by design | Risk/analytics software vendors |
| **Model Validation & Model Risk** | **High** — fintech credit/fraud/AML model validation is booming and remote-friendly | Fintech, lenders, neobanks, advisory |
| **Investment & Market Risk Analytics (VaR/CVaR)** | **Medium** — asset managers, risk-tech | Buy-side analytics, vendors |
| **Bank ALM / IRRBB / Treasury** | **Lower remote** — but neobanks/crypto have real treasury/ALM needs | Fintech treasury teams |

**Net:** lead with **Solutions Engineering at a risk-tech vendor** and **Model Validation for fintech**. These are your fastest remote paths and both are squarely true to your Moody's experience.

---

## 2. Target map (research lists — verify remote-Canada eligibility per posting)

These are *illustrative* targets grouped by angle. Confirm each posting is open to Canada (or hires via EOR) before applying — many "remote" US roles are US-residents-only.

**A. Risk / analytics software vendors (Solutions Engineering, Implementation, Client Analytics, Model-Validation Services)** — your Moody's-adjacent home turf:
Moody's Analytics, S&P Global Market Intelligence, MSCI, Bloomberg, BlackRock (Aladdin), FIS, Numerix, Quantifi, SS&C Algorithmics, SAS/Kamakura, QRM (Quantitative Risk Management), Empyrean, ZM Financial Systems, Abrigo, nCino, Yields.io, Evalueserve, Beacon.

**B. Fintech / neobanks / lenders / crypto (Model Risk & Validation, Treasury/ALM, Risk Analytics):**
Affirm, Upstart, SoFi, Chime, Mercury, Brex, Cross River, Column, Coinbase, Block, Plaid, Pagaya, Figure. Credit/fraud/AML-model validation is the most common remote opening here.

**C. Rating agencies & research (Analyst / Senior Analyst — some remote):**
Moody's Ratings, S&P, Fitch (you've already applied), KBRA, Morningstar/DBRS.

**D. Advisory / model-risk consultancies with remote postings:**
Protiviti, Crowe, RSM, plus risk boutiques.

> Action: I can extend your existing `jd_scraper` company list (currently ~155 Canadian-weighted) with a US-remote expansion set and adjust `location_filter.py` to accept "remote (US/Americas/Canada/global)" — see §5.

---

## 3. Channels & where to look

- **Boards that surface remote roles open to Canada:** We Work Remotely, Remote OK, Built In (remote fintech/finance), Remote.co, Dynamite Jobs, Indeed.ca ("US companies hiring Canadians / remote"), SimplyHired.ca, LinkedIn (set location filter to *Remote* + keyword "Canada").
- **Best signal filters in postings:** "Remote – Americas," "Remote – Canada & US," "we hire via Deel/Remote," "global/distributed team." Avoid "Remote (US only)" / "must be authorized to work in the US."
- **Company-direct > board:** for vendors (list A), apply on their careers page and filter to Remote.
- **LinkedIn:** keep "Open to Work" **recruiter-only**, and set preferences to *Remote* with locations Canada **and** United States. Your new About line + reframed Solutions-Engineering bullets already support this pivot.

---

## 4. How to answer "are you authorized to work in the US?"

You'll see this on most US ATS forms. Be accurate and disarm it up front:

> "I'm based in Toronto and work fully remotely. I'm authorized to work in Canada and can be engaged through an Employer of Record or as a contractor — **no US visa or sponsorship required.** I overlap fully with US Eastern hours."

- If a form has a hard "Are you authorized to work in the US? Y/N" with no remote option, and the role is genuinely US-only, skip it.
- Put a one-line banner at the top of your resume/cover note for US apps: *"Remote from Toronto (ET) · available via EOR/contract · no US sponsorship required."*

---

## 5. Leverage your existing automation (highest-leverage move)

You already have a 5-agent scrape→score→tailor pipeline. Don't run a separate manual US search — **extend the machine**:

1. **Add a US-remote company set** to `automation/expansion_companies.py` (lists A–D above).
2. **Relax the geo gate:** update `location_filter.py` to *pass* roles tagged remote-US / remote-Americas / remote-Canada / global-remote, instead of GTA-only.
3. **Add US-remote keywords** to the fit scorer (e.g., "remote," "Americas," "EOR," "distributed").
4. **Spin a US-resume variant:** clone your resume_data template with the §4 remote banner + Solutions-Engineering-forward summary, so tailored US resumes render automatically.
5. Keep the Canadian pipeline running in parallel as your floor while the US funnel fills.

> I can implement 1–4 for you — say the word and I'll draft the diffs.

---

## 6. Weekly rhythm (≈6–8 focused hrs/wk)

- **Mon:** triage the weekend scrape; shortlist 8–12 US-remote roles that pass the Canada-eligibility check.
- **Tue–Wed:** apply (tailored resume + the remote banner). Target **10–15 quality apps/week**, not spray.
- **Thu:** outreach — message 5 people at target companies (hiring managers, ex-Moody's contacts now in fintech/vendors). Warm intros >> cold applies for remote roles.
- **Fri:** run the pipeline; log outcomes; send 2–3 recommendation requests (ties into your LinkedIn fixes).

---

## 7. Timeline

- **Weeks 1–2 (now):** finish LinkedIn fixes; build the US target list + resume variant; extend automation; first 10–15 US apps out.
- **Weeks 3–6:** steady 10–15 apps/wk + 5 outreaches/wk; expect first screens. Refine targeting from response data.
- **Weeks 7–12:** interviews; deepen with 2–3 vendors/fintechs where you have warm contacts. Negotiate EOR terms (USD comp, equity, benefits).
- **Throughout:** stay in current job until a signed remote offer — leaving is the *outcome*, not step one.

---

## 8. Realities to price in

- **Comp:** US risk-quant roles average ~US$170k (range ~$135k–$200k); strong upside vs Canadian comp, and a favorable FX. Via EOR you're paid in CAD/USD and taxed in Canada.
- **Fewer ALM-at-bank remote roles** — that's why §1 steers you to vendors + fintech model risk.
- **"Remote" ≠ "remote-Canada"** — always verify; it's the #1 time-waster.
- **Equity** at startups is real upside but illiquid — weigh it, don't bank on it.
- **You are not desperate** — you have a job. That's leverage; be selective.

---

## 9. This week — concrete next steps

1. Finish the LinkedIn pivot (Skills curation, Projects, recommendation requests).
2. Approve the §2 target list (add/remove companies).
3. Let me extend the automation (§5) for US-remote sourcing.
4. Create the US resume variant with the remote banner.
5. Get the first 10–15 US-remote applications out.

---

*Not legal/tax advice. EOR vs contractor classification and cross-border tax should be confirmed with an accountant; immigration is not a factor while you remain in Canada.*
