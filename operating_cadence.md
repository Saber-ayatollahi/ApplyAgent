# Operating Cadence — 10-Week Campaign

> **Dates:** 2026-05-03 → 2026-07-12 (10 weeks). Review and extend week-by-week.
> **Owner:** Saber Ayatollahi.
> **Purpose:** Turn research into applications, applications into interviews, interviews into offers. This is the *only* doc that tells you what to do today.

---

## 1. North-Star KPIs (weekly)

| KPI | Target | Why |
|---|---|---|
| Tailored applications submitted | **8** | One resume-tailored + cover-letter-tailored app ≥ 5× the conversion of a generic app. 8/wk is sustainable; 12+/wk degrades quality. |
| Outbound outreach messages (recruiter, hiring mgr, alumni) | **10** | ~70% of Director+ hiring is referral-driven in Toronto finance. Cold-apply alone is the slow lane. |
| Coffee chats / video calls (outside Moody's) | **3** | One of every three turns into a referral or lead. 3/wk → ~1 warm referral/wk. |
| LinkedIn posts (content marketing) | **1** | Builds inbound. 12 posts over the campaign = visibility surface. |
| Recruiter conversations | **2** | Toronto finance recruiters warm up slowly — sustained contact is what moves them. |

**Stretch KPIs (not required):**
- Interview-stage conversions: ≥ 2/wk after Week 3.
- Offer milestones: ≥ 1 offer by Week 10.

**Track KPIs in `job_tracker_data.json` + `recruiter_crm.json`. Generate a weekly report every Friday evening using `automation/weekly_report.py`.**

---

## 2. Daily ritual (90 min/day, every weekday)

### 07:00–07:20 — Morning scan (20 min)
1. Open `job_tracker_data.json` → check followup_schedule for anything due today.
2. LinkedIn jobs email digest → 2-min triage, save candidates with company + link into `inbox.md`.
3. Check 3 priority portals for new postings (rotate Mon-Fri: Scotia/RBC/BMO, CIBC/TD/NBC, HOOPP/OMERS/OTPP/CPP, BlackRock/Bloomberg/MSCI/S&P, Manulife/Sun Life/Canada Life).

### 12:00–12:15 — Lunch check (15 min)
1. Respond to any recruiter InMails or email replies (never wait > 24 hrs).
2. Like/comment on 2 target-company LinkedIn posts.

### 19:00–20:00 — Evening execution (60 min)
Cycle through this priority stack until the hour is up:
1. **Apply** — if any `Apply This Week` role has a tailored resume drafted and outreach sent, submit.
2. **Tailor** — use `jd_tailor.py` on the next highest-urgency role.
3. **Outreach** — send 2 warm-intro / recruiter / alumni messages.
4. **Prep** — if interview scheduled, 30-min prep slot.
5. **Content** — if Sunday, draft next Monday LinkedIn post.

---

## 3. Weekly rhythm

### Monday
- Publish 1 LinkedIn post (scheduled Sunday evening, goes live Mon 07:30).
- Select the week's 8 `Apply This Week` targets. Write them in `this_week.md` at the top.
- 1 recruiter call scheduled for the week ahead.

### Tuesday–Thursday
- 2–3 applications submitted per day (peak).
- Coffee chats scheduled (aim 1 Tue, 1 Wed, 1 Thu).
- Outreach: 3–4 messages/day.

### Friday
- 18:00 — run `weekly_report.py`. Review KPI deltas. Identify stalled apps (> 21 days with no response — resend follow-up or close).
- 20:00 — plan next week's 8 apply targets. Move cards on tracker.

### Saturday
- Off unless interview scheduled. Decompress.
- Optional: 1 hour reading OSFI / Basel / IRRBB — feeds LinkedIn content engine.

### Sunday
- 17:00–18:00 — draft Monday LinkedIn post (see `linkedin_content_engine.md`).
- 20:00 — review tracker; update any stale statuses.

---

## 4. Follow-up cadence (per application)

After Apply:
- **D+3:** LinkedIn connect request to hiring manager (if identifiable) or recruiter, short note referencing the role.
- **D+7:** Second LinkedIn InMail or email to HM/recruiter if no response — brief value-add (e.g., "I saw your team is working on X — here's a 2-line POV").
- **D+14:** Email recruiter/HM — status check if any contact has been made; if none, decide to escalate (LinkedIn post tagging the company, referral activation, etc.).
- **D+21:** If still no response → mark **Ghosted**. Move on. Do not keep tailoring resumes for the same posting.

For each applied role, set `date_last_followup` and `followup_schedule.next_due` in the tracker.

---

## 5. Interview protocol

- 24 hours after scheduling: run `jd_tailor.py` again against the company to regenerate prep brief.
- Open `interview_prep.md` → technical Q&A + STAR stories.
- 1 hour before: re-read the JD, the master repo §5 bullet library, and the company's latest earnings call transcript for investment banks / publicly-traded AMs.
- Ask 3 prepared questions of the interviewer (see `interview_prep.md` §9).
- Within 4 hours after: email a 3-line thank-you referencing 1 specific thing discussed.
- Within 24 hours: log outcome + key quotes in `job_tracker_data.json` notes.

---

## 6. Rejection response protocol

- **Recruiter-screen rejection:** ask for one specific reason ("Was it the comp band, the seniority level, or a technical gap?"). Log in `rejection_reason` field. Many rejections are comp-band mismatches — useful signal.
- **Post-interview rejection:** email thank-you; ask to stay in touch for future roles; save recruiter / HM as LinkedIn contact with note.
- **Silent rejection / ghost:** D+21, mark Ghosted. Do not email again.
- **Ego-bruising rejection:** 1 hour of boxing / gym. No same-day response.

---

## 7. 10-week rolling calendar

### Week 1 — 2026-05-03 → 05-09 — **"Ship the backlog"**
**Objective:** Apply to every confirmed-live Tier 1 role. Stand up all operating infrastructure.
- **Apply targets (8):** scot-001, scot-002, scot-003, bmo-001, cib-001, bloom-001, br-001, spg-001.
- **Outreach targets (10):** BlackRock Toronto hiring managers (Aladdin team); S&P Risk Solutions Toronto leads; MSCI Toronto hiring managers; 3 Moody's alumni at Scotia/BMO/RBC; 2 Ortec→HOOPP/OMERS/IMCO alumni; EY FSRM 2021-2022 ex-managers.
- **Coffee chats (3):** 1 Moody's alum, 1 CFA Toronto society contact, 1 Western MSc alum.
- **LinkedIn post:** "OSFI E-23 and the shape of Canadian model-risk hiring in 2026" (analytic, 400 words, positions Saber as the informed insider).
- **Infrastructure:** Set up `jd_tailor.py`, `jd_scraper.py`, `weekly_report.py`. First scrape run.

### Week 2 — 2026-05-10 → 05-16 — **"Expand the vendor front"**
- **Apply targets (8):** bloom-001 resubmit if needed + msci-001, spg-001, fset-001, numerix-001, ssc-algo-001, deloitte-fsi-001, ey-fsrm-001, mercer-001.
- **Outreach:** 2 Moody's→Bloomberg, 2 Moody's→S&P, 2 Moody's→MSCI, 2 EY→consulting, 2 Ortec→Mercer/WTW.
- **Coffee chats:** 1 vendor-platform insider, 1 pension insider, 1 consulting insider.
- **LinkedIn post:** "Why multi-asset cash-flow projection engines are under-appreciated in LDI design".

### Week 3 — 2026-05-17 → 05-23 — **"Pension sweep"**
- **Apply targets (8):** cpp-001, otpp-001, omers-001, hoopp-002, imco-001, psp-001, caat-001, optrust-001.
- **Outreach:** direct-message Risk and Fixed Income heads at each Maple 8 via LinkedIn InMail; activate Ortec alumni for warm intro.
- **Coffee chats:** 3 pension-industry contacts.
- **LinkedIn post:** "LDI meets IRRBB — where pension-fund ALM and bank balance-sheet risk converge".

### Week 4 — 2026-05-24 → 05-30 — **"Insurer + mid-bank sweep"**
- **Apply targets (8):** manulife-001, slim-001, canadalife-001, intact-001, ia-001, eqb-001, rga-001, definity-001.
- **Outreach:** IFRS 17 networking — EY / Mercer / WTW contacts with insurer relationships; LinkedIn InMail to Heads of ALM at top 3 insurers.
- **Coffee chats:** 3 insurer contacts.
- **LinkedIn post:** "IFRS 17 is done — now what? Post-implementation ALM opportunities at Canadian life insurers".

### Week 5 — 2026-05-31 → 06-06 — **"Interview density"** (expected first-round density)
- **Apply targets (6):** fill from any live roles surfaced; otherwise US-bank sweep (jpm-001, citi-001, hsbc-001) + gs-001 + ms-001 + db-001.
- **Prep:** expect ≥ 3 first-round interviews this week based on Week 1-3 applications.
- **Outreach:** lower (4–5 messages) to protect interview prep time.
- **Coffee chats:** 2 (lower).
- **LinkedIn post:** "What a 'formal sign-off' actually means in bank model governance" (reinforces credibility during active interviews).

### Week 6 — 2026-06-07 → 06-13 — **"Follow up + top-up"**
- Every Week 1-3 application that hasn't responded: D+28 or D+35 — move to Ghosted, close out.
- New applications: top up to 8 from any fresh postings surfaced by scraper.
- **Coffee chats:** 3, weighted to second-round targets.
- **LinkedIn post:** "Agentic AI in production risk workflows — what works, what doesn't".

### Week 7 — 2026-06-14 → 06-20 — **"Second rounds / on-sites"**
- Interview prep is the priority. Apps secondary (4–5).
- **Outreach:** only to recruiters/HMs at active interview companies.
- **LinkedIn post:** "The 3 scenarios every IRRBB program needs to explicitly run".

### Week 8 — 2026-06-21 → 06-27 — **"Finalist mode"**
- References activation. Offer negotiation prep.
- Apps: light (3–4).
- Compensation research re-run for any company at final-round stage.
- **LinkedIn post:** "Calypso to modern platforms — what the migration actually looks like from the client side".

### Week 9 — 2026-06-28 → 07-04 — **"Close the offer"**
- Negotiation phase if offers are in hand. Counter-offer scripts from `references_and_salary.md`.
- Reference checks complete.
- Apps: none unless no offers (in which case, escalate to recruiter pressure + reactivate Week 1-4 ghosts).
- **LinkedIn post:** (skip if in active negotiation; otherwise "OSFI B-12 update — what it means for 2027 planning").

### Week 10 — 2026-07-05 → 07-11 — **"Decision / bridge"**
- Offer accepted → decline others with grace; start-date confirmed.
- If no offer: debrief, run a `campaign_retrospective.md`, extend by 4 more weeks with positioning tweaks based on feedback patterns.

---

## 8. When to deviate

- **You get a great offer in Week 3:** pause outbound, focus on closing. Do not dilute.
- **You get 3+ rejections citing the same reason:** stop applying; fix the positioning before resuming.
- **Ortec / EY reaches out with a referral for a role:** reprioritize. Referred applications convert 5-10× vs. cold.
- **An interviewer flags a skill gap you don't have:** honest self-assessment — is this a 2-week skill-up or a positioning problem? Decide and act.
- **You are losing steam:** cut the KPIs in half for 1 week, recover, resume. Burnout in Week 4 means no Week 8 offers.

---

## 9. Anti-patterns (things that will feel productive but aren't)

- ❌ Polishing the Master Repo / tracker beyond what's needed for Monday's 8 apps.
- ❌ Rewriting a resume from scratch for a role that's a Tier 4 Medium fit.
- ❌ Applying to 20 jobs in a day with the same resume.
- ❌ Reading every job description end-to-end before a first triage.
- ❌ Waiting to hear back from one role before applying to others.
- ❌ Writing long cover letters. Target: 300–350 words max.
- ❌ LinkedIn posts that are self-promotional humble-brags. Post analysis, not status.
- ❌ Scheduling 5 coffee chats in one week and then cancelling. Commit or don't.

---

*This file is your compass. Open it every Monday 07:00. If you deviate, write why in your tracker notes.*

*Last updated: 2026-05-03*
