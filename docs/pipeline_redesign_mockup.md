# Pipeline page mockup — v3 wireframes

ASCII wireframes for the redesigned 🎯 Pipeline page. Eight states covering the realistic user journey. The widget vocabulary is constrained by Streamlit (no custom JS), so this is what's actually buildable.

Visual conventions:
- `▶`  primary action (red filled button)
- `▷`  secondary action (outlined button)
- `▸`  collapsible expander (closed)
- `▾`  collapsible expander (open)
- `📊` xlsx download · `📄` json download
- Status pills: `🟢 healthy`  `🟡 stale`  `🔴 fail/blocking`  `⏸ empty`  `⏵ needs review`  `⚠ quarantine`

Cards are bordered containers (`st.container(border=True)`). Headlines use `st.metric`. Dropdowns/multiselects/sliders rendered standard.

---

## State 1 — happy path: scoring is the next step

The most common state mid-week: scrape and gmail just refreshed, worklist rebuilt, lots of rows need scoring. Banner names ONE next action; everything else is reference.

```
🎯 Pipeline                                                    [🔄 Reload page]

╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ▶  Score 1,206 jobs       227 free re-score · 979 billable · ~$0.42, 5-18min║
║                                                                              ║
║    Last scoring run 7d ago · API key valid                  [▶ Score 1,206] ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ 🟢 ① INPUTS ─────────────────────────────────────────────────────  1,394 rows ─┐
│                                                                                │
│   🛰  Web scrape           1,360 rows · 33h ago · 18 sectors                   │
│       scan_20260525.json · 759 KB                                              │
│                                            [▷ Refresh scrape]    📊  📄        │
│                                                                                │
│   📬  Gmail alerts             34 rows · 0m ago · 6 alerts seen                │
│       scan_gmail_20260526_215041.json · 13 KB                                  │
│       2 geo-dropped (Prince Rupert, Ottawa)                                    │
│                                            [▷ Refresh Gmail]     📊  📄        │
│                                                                                │
│   ▸ Inspect rows                                                               │
└────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─ 🟢 ② WORKLIST ──────────────────────────────────────────  1,433 deduped rows ─┐
│                                                                                │
│   🛰 1,342 scrape · 📬 75 gmail · 🔁 16 both · 268 merges                       │
│   ⚠ 159 quarantined (legacy May-18 parser regression)                          │
│   Last rebuild 0m ago                                                          │
│                                                                                │
│   ▸ Inspect (recent · quarantine · merges · by source)              📊  📄    │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─ 🟢 ③ TRIAGE  (rule-based filter)  ─────────────────  728 passed · 705 dropped ─┐
│                                                                                │
│   Top drop reasons: 412 no_strong_keywords · 156 negative_term ·                │
│                     137 level_mismatch                                         │
│   Drop ratio 49% — within healthy range                                        │
│                                                                                │
│   ▸ Inspect (all drops · by rule · 🩹 rescue candidates)            📊  📄    │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─ 🔴 ④ SCORING ────────────────────────  1,206 unscored · 287 free re-score ───┐
│                                                                                │
│   Last run 7d ago · 602 verdicts in pool                                       │
│   Cost split: 227 fit_cache hits · 60 reusable from prev scored ·              │
│               979 fresh API calls (~$0.42)                                     │
│   Concurrency: 6 → ETA ~5–18 min                                               │
│                                                                                │
│   ▸ Inspect verdicts (top fits · by sector · drops · API errors)    📊  📄    │
│                                                                                │
│        [▶ Score 1,206 ($0.42, 5-18min)]    [⚙ Force rescore subset]            │
│                                                                                │
│   ▸ Score one URL  (manual side-channel)                                       │
└────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─ 🟢 ⑤ AUTO-PROMOTE ──────────────────────────  0 promotable at fit≥7 ────────┐
│                                                                                │
│   Last commit 7d ago · added 3 · skipped 4 · expired 0                         │
│   Threshold: fit≥7 · include-watch: off                                        │
│                                                                                │
│   ▸ Inspect (would add · would skip · last commit)                  📊  📄    │
│                                                                                │
│        [▷ Preview changes]    (Apply disabled — preview first)                 │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─ ⏵ ⑥ TRACKER ─────────────────────────────────────────────  64 jobs · 12 to review ─┐
│                                                                                │
│   12 Found · 3 Watch · 5 Applied · 44 Closed                                   │
│                                                                                │
│   [→ Review Queue (12)]    [→ Today's brief]    [→ Jobs Kanban]                │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

▸ Recent runs (5)                                          ⚙ Advanced config
```

---

## State 2 — multi-pending: promote takes priority over score

Promote is fast, free, deterministic. Banner picks Promote even with 1,200 unscored, because the user can act on tracker rows immediately while scoring runs later.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ▶  Promote 12 scored rows                            5 seconds, no API cost ║
║                                                                              ║
║    ↳ Also pending: Score 1,206 ($0.42, ~5min)        [▷ Preview] [▶ Apply] ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

(rest of cards unchanged from State 1, but ⑤ AUTO-PROMOTE shows `🟢 12 promotable`
and ④ SCORING shows secondary `[▷ Score later]` instead of primary)

---

## State 3 — scoring in progress

Banner becomes the live-job indicator. Stop button. Per-stage progress.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ 🟡  Scoring  ·  412 / 728 scored  ·  started 4m ago  ·  ETA 6m              ║
║                                                                              ║
║    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  56%               ║
║                                                                              ║
║    Stage 1 ✓  Stage 2 (LLM) running                          [⏹ Stop run]   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Stage cards below are dimmed (`disabled` styling) except their inspect expanders. Action buttons all disabled during a run. Live log tail accessible via `▸ Run output (tail)` expander on the running stage card.

---

## State 4 — last run failed, but downstream work is still doable

Failed run gets a red top-line, but a green secondary CTA recognises the failure didn't invalidate downstream work.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ 🔴  Last Refresh scrape failed 12 min ago               SSL: ZScaler proxy  ║
║                                                                              ║
║    Worklist still has 1,433 rows from previous scrape       [▷ View error] ║
║                                                                              ║
║                            ────────────────────                              ║
║                                                                              ║
║ ▶  Score 1,206 jobs anyway                              ~$0.42, 5-18min    ║
║                                                              [▶ Score 1,206]║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Stage ① shows 🔴 and the error message expanded inline. Other stages stay 🟢.

---

## State 5 — empty pipeline (first-time / blank slate)

No worklist yet. Onboarding lights up Inputs only; downstream stages render but greyed with explanation.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ⏸  Empty pipeline                                                           ║
║                                                                              ║
║    Two ways to start:                                                       ║
║                                                                              ║
║    1.  Connect Gmail in the sidebar, then click Refresh Gmail               ║
║    2.  Click Refresh scrape (~15-30 min, no API key needed)                 ║
║                                                                              ║
║                           [▷ Connect Gmail]    [▶ Refresh scrape]           ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ ⏸ ① INPUTS ──────────────────────────────────────────────────  no rows yet ─┐
│   🛰  Web scrape    not run yet                            [▶ Refresh scrape]│
│   📬  Gmail alerts  not connected                          [▷ Connect Gmail] │
└────────────────────────────────────────────────────────────────────────────────┘

┌─ ⏸ ② WORKLIST ────────────────────────────────────  Run scrape or Gmail first ─┐
└────────────────────────────────────────────────────────────────────────────────┘

┌─ ⏸ ③ TRIAGE / ④ SCORING / ⑤ AUTO-PROMOTE  ─────  Will activate after worklist ─┐
└────────────────────────────────────────────────────────────────────────────────┘

┌─ 🟢 ⑥ TRACKER ──────────────────────────────────────────────  0 jobs ─────┐
│   No jobs yet — they'll land here after Auto-promote runs               │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## State 6 — up to date

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ✅  Up to date  ·  next nightly refresh in 4h 12m                            ║
║                                                                              ║
║    Inputs fresh · 0 unscored · 0 promotable · tracker stable               ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

All stage cards 🟢. Action buttons present but secondary. The only `▶` primary on the page is `[▶ Run nightly refresh now]` in the Advanced config expander.

---

## Expander view — Stage ③ Triage Inspect (sub-tabs)

When user clicks `▸ Inspect` on the Triage card, it expands inline with sub-tabs:

```
┌─ ▾ Inspect triage  ────────────────────────────────────────────────────────────┐
│                                                                                │
│   [ All drops (705) ]  [ By rule ]  [ 🩹 Rescue candidates (23) ]              │
│                                                                                │
│   ── All drops tab ───────────────────────────────────────────────────────     │
│                                                                                │
│   Filter:  [search_______]  [rule ▾]  [sector ▾]                               │
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐ rescue   │
│   │ company        │ title                  │ rule_reason  │ score │  □       │
│   ├─────────────────────────────────────────────────────────────────┤          │
│   │ Visa           │ Senior Manager, Sales  │ negative_term│ 0     │  □       │
│   │ HOOPP          │ Director, IT Audit     │ level_mismatch│ 4    │  □       │
│   │ Manulife       │ Junior Risk Analyst    │ no_strong_kw │ 1     │  ☑       │
│   │ Scotiabank     │ Senior Director, …     │ no_strong_kw │ 4     │  ☑       │
│   │ ... 701 more rows ...                                          │          │
│   └─────────────────────────────────────────────────────────────────┘          │
│                                                                                │
│   2 selected for rescue       [🩹 Rescue 2 rows on next score run]             │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

`Rescue candidates` sub-tab pre-filters to rows that almost passed (e.g., rule_reason = `level_mismatch` AND score ≥ 4) — surfaces the most-likely misses without forcing the user to scan 705 rows.

---

## Expander view — Stage ⑤ Auto-promote preview→apply

The two-step UX. `[Preview changes]` runs classification dry, opens an inline expander with the diff. `[Apply to tracker]` only enables after preview.

### Before clicking Preview

```
[▷ Preview changes]    [Apply to tracker]   ← disabled
```

### After Preview (expander auto-opens)

```
┌─ ▾ Preview ─────────────────────────────  Generated 8s ago, fit≥7, !watch ───┐
│                                                                                │
│   ▶ 12 will be added to tracker                                                │
│   ┌────────────────────────────────────────────────────────────────┐          │
│   │ id                  │ company  │ title              │ tier │ url        │
│   ├────────────────────────────────────────────────────────────────┤          │
│   │ auto-rbc-9-irrbb… │ RBC      │ Director, IRRBB…   │  1   │ linkedin…  │
│   │ auto-bmo-9-alm-… │ BMO      │ Senior Manager, ALM│  1   │ linkedin…  │
│   │ ... 10 more ...                                              │           │
│   └────────────────────────────────────────────────────────────────┘          │
│                                                                                │
│   ▶ 4 will be skipped                                                          │
│      • 2 below_min_score (fit=6)                                               │
│      • 1 duplicate_lower_score (existing fit=8)                                │
│      • 1 geo (Vancouver)                                                       │
│                                                                                │
│   ▶ 0 will be expired                                                          │
│                                                                                │
│   Settings used:  --min-score 7  --include-watch off  --auto-tailor off        │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

[▷ Re-preview with different settings]    [✓ Apply 12 to tracker]   ← now enabled
```

`[Apply 12 to tracker]` commits exactly the previewed diff (preview + commit are two phases of one auto_promote.py invocation, so the diff is consistent — no race window between preview and apply).

`[Re-preview]` opens an inline form: `min-score slider`, `include-watch checkbox`, `auto-tailor checkbox`. Re-previewing wipes the preview cache and disables Apply until re-confirmed.

---

## Recent runs expander (bottom of page)

```
┌─ ▾ Recent runs (5) ──────────────────────────────────────────────────────────┐
│                                                                                │
│   ✅ Refresh Gmail        gmail_fetch_…219211   2m ago   34 rows kept         │
│   ✅ Score worklist       pipeline_…20210     1d ago   602 scored             │
│   ✅ Refresh scrape       pipeline_…20212     1d ago   1,360 rows kept        │
│   🔴 Refresh scrape       scrape_resume_…29   2d ago   SSL fail   [view]      │
│   ✅ Auto-promote          pipeline_…20214     7d ago   added 3                │
│                                                                                │
│                                              [→ Open Scan History page]       │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

5-row preview only. Full filterable history is the existing 📜 Scan History page; this expander deep-links there.

---

## Visual hierarchy summary

Three levels of weight:

1. **Banner** — top, full width, only PRIMARY (red filled) button on screen unless dimmed. Decides what the user does next.
2. **Stage cards** — bordered, equal weight, scroll-readable. Each has its own primary if applicable, but visually subordinate to the banner.
3. **Inspect expanders** — collapsed by default. Only the user who CHOOSES to drill in pays the rendering cost (large dataframes, sub-tab state).

What disappears from current UI:
- Run / Worklist / Scored / History tabs
- Two-sources panel (folded into Inputs + Worklist cards)
- Latest outputs panel (each card has its own downloads)
- Standalone Quick Actions row at the top (replaced by banner CTA + per-card actions)
- Score-this-URL standalone — moves into Scoring card as expander

What stays unchanged:
- Live log tail behavior (now scoped to running stage card)
- Sidebar (API key, Gmail, etc.)
- Advanced config expander (still at bottom)
- All CLIs and disk schemas

---

# v3.1 — feedback-loop wireframes

These layer onto v3 without changing the 6-stage skeleton. See `pipeline_redesign.md` § "v3.1" for rationale.

## State 7 — Scoring card with manual selection

User opens `▸ Inspect verdicts` on the Scoring card. Checkbox column appears, multiselect filters, and a footer action that bypasses the threshold-based promote. **Selection survives filter changes and reruns** — keyed on URL in `st.session_state["scoring_selected_urls"]`, derived into the checkbox column each render.

```
┌─ 🟢 ④ SCORING ────────────────────────  728 scored · 12 above fit≥7 ─────────┐
│                                                                                │
│   Last run 4h ago · API key valid                                              │
│                                                                                │
│   ▾ Inspect verdicts                                                           │
│                                                                                │
│     [ Top fits (38) ]  [ By sector ]  [ Verdicts ]  [ API errors (0) ]         │
│                                                                                │
│     Filter:  fit ≥ [7▾]   verdict [apply_now ▾]  sector [all ▾]  [search___]   │
│                                                                                │
│     ☐  fit  company         title                       sector          verdict│
│     ─────────────────────────────────────────────────────────────────────────  │
│     ☑  9   RBC              Director, IRRBB Risk         Big 6 Banks   apply   │
│     ☑  9   BMO              Sr Mgr, ALM Strategy         Big 6 Banks   apply   │
│     ☐  9   HOOPP            Assoc Dir, LDI Strategy      Pension       apply   │
│     ☑  8   Sun Life         Director, Investment Risk    Insurer       apply   │
│     ☐  8   Scotiabank       Sr Mgr, Treasury Risk        Big 6 Banks   apply   │
│     ☐  8   CIBC             Director, Capital Mgmt       Big 6 Banks   apply   │
│     ☑  8   OMERS            Mgr, Quant Strategy          Pension       tailor  │
│     ☐  7   TD               Sr Mgr, Liquidity            Big 6 Banks   apply   │
│     ... 30 more ...                                                            │
│                                                                                │
│     4 selected   ┃   [▶ Send 4 to tracker]   [Clear]   [Select all visible]   │
│                                                                                │
│     Will send 4 (0 below fit≥7, 0 suppressed, 0 geo-skipped)                  │
│     ↑ always-visible st.caption pre-flight, no modal                           │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

Below-threshold rows in the selection are accepted with `selection_mode: "manual_below_threshold"` in the promote report. Manually-selected `verdict=skip` rows promote as `Watch / tier 4` with `manual_override_skip_verdict: true` in notes — never silently dropped. Post-action toast: *"Sent 4 to tracker (4 manual; 0 silently dropped)."*

No confirm modal at any N. The `Will send N (...)` caption beneath the button is the pre-flight; below-threshold and suppressed counts visible before the click. The earlier draft proposed a modal at N≥25 — removed during review as patronising for a solo user with selection autonomy.

---

## State 8 — Review Queue card with mute menu (Streamlit-honest layout)

The user is acting on a Found job. Primary actions are the existing 5-button row plus a per-row archive button. Mute lives in an inline `st.popover("⋯ More")` placed in its own row beneath the action row — opens **inline below the card**, pushing later cards down. There is no floating menu in Streamlit; an earlier wireframe drew one anchored to the right and was wrong.

```
┌─ 📌 RBC — Director, IRRBB Risk Management ──────────────  fit 9 · Big 6 Banks ─┐
│                                                                                │
│   📍 Toronto · 🔗 linkedin.com/jobs/…                                           │
│   Posted 2d ago · 12 applicants · score 9/10 · verdict apply_now               │
│                                                                                │
│   ▸ JD summary  · ▸ Fit reasoning  · ▸ Skill match (8/10)                      │
│                                                                                │
│   [📌 Watch]  [✅ Apply]  [❌ Expire]  [🔗 Open JD]  [⏭ Skip]  [🚫 Archive]      │
│                                                                                │
│   [⋯ More options ▾]                                                           │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

When `[⋯ More options ▾]` is clicked, Streamlit's `st.popover` opens below the card body. Two items only — archive lives on the action row, not duplicated here:

```
┌─ ⋯ More options ──────────────────────────────────────────────────────────────┐
│                                                                                │
│   [🔇 Mute sector "Canadian Big 6 Banks"]                                       │
│   [🔇 Mute company "RBC"]                                                       │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Mute-sector inline confirm (NOT `st.dialog`)

Click `🔇 Mute sector "Big 6 Banks"` → mounts an inline confirm container beneath the Review Queue card, mirroring the existing `_rq_apply_open` pattern at `ui/app.py:8325`. No `st.dialog` — width is consistent with the page, no overlay jank, sector-impact stats cached behind `@st.cache_data(ttl=60)`.

```
┌─ Mute sector: Canadian Big 6 Banks ───────────────────────────────────────────┐
│                                                                                │
│   Coverage:                                                                    │
│   ▸ Will mute 47 of 51 worklist rows in this sector                            │
│   ▸ 4 unsectored Gmail rows pass through (unsectored fall-through; review     │
│     Triage Drops if they appear in tracker — fix is to add company mute)      │
│   ▸ 3 active tracker rows untouched (use per-row Archive if needed)            │
│                                                                                │
│   Duration:                                                                    │
│   ( ) 30 days   (●) 60 days   ( ) 90 days   ( ) Custom: [____] days            │
│   ( ) No auto-lift  ⚠  (yellow chip in suppression list — manual maintenance) │
│                                                                                │
│   Reason (recorded in suppressions_events.jsonl):                              │
│   ┌────────────────────────────────────────────────────────────────────────┐  │
│   │ Applied to 14 Big 6 roles, 1 interview. Lane is cold for now.          │  │
│   └────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│   ☑ Archive this job ("RBC — Director, IRRBB Risk") on confirm                 │
│                                                                                │
│                                          [▷ Cancel]    [✓ Mute for 60 days]   │
└────────────────────────────────────────────────────────────────────────────────┘
```

After confirm:

1. Suppression write succeeds first (higher-signal, less-frequently-corrected). Event line appended to `suppressions_events.jsonl`.
2. Archive of this job is attempted second.
3. **Both succeed** → green toast: `🔇 Muted "Canadian Big 6 Banks" for 60 days. Lifts 2026-07-26.  [Undo]`
4. **Archive fails** → yellow toast: `🔇 Mute saved; archive of "RBC — Director, IRRBB" deferred — retry from Review Queue.` The pending archive lands in `data/suppressions_pending_archives.jsonl`; on next page load, a `[Retry archive]` button appears on the affected row.

The `[Undo]` link in the success toast calls `suppressions.lift("sector", "Canadian Big 6 Banks")` directly. No round-trip to the Triage card needed for immediate-regret cases.

---

## State 9 — Triage card with active suppressions

Each suppression renders as its own bordered container with `st.columns([3, 1, 1, 1])` — fits below 900px viewport without wrap. Coverage column shows the unsectored fall-through count so users see the boundary, not just the headline.

```
┌─ 🟢 ③ TRIAGE  (rule-based filter)  ─────────────────  728 passed · 705 dropped ─┐
│                                                                                │
│   Top drop reasons: 156 negative_term · 47 suppressed_sector ·                 │
│                     412 no_strong_keywords · 137 level_mismatch                │
│   (ordering: negative_term → suppression → keyword/level — see redesign §B.5) │
│                                                                                │
│   ▾ Active suppressions (2)                                                    │
│                                                                                │
│     ┌──────────────────────────────────────────────────────────────────────┐  │
│     │ 🔇 sector  · Canadian Big 6 Banks                  [🔓 Lift] [+30d]  │  │
│     │ Until 2026-07-26 (60d)  ·  added 2026-05-27                          │  │
│     │ Coverage: 47 of 51 rows  ·  4 unsectored — pass through  ⓘ           │  │
│     │ Reason: 1/14 conversion. Lane cold.   [click to edit]                │  │
│     └──────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│     ┌──────────────────────────────────────────────────────────────────────┐  │
│     │ 🔇 company · Manulife                              [🔓 Lift] [+30d]  │  │
│     │ Until 2026-08-15 (80d)  ·  added 2026-05-27                          │  │
│     │ Coverage: 4 of 4 rows  ·  canonical_key = manulife                   │  │
│     │ Reason: ghosted x3      [click to edit]                              │  │
│     └──────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│     [+ Add suppression]                                                        │
│                                                                                │
│   ▸ Inspect (all drops · by rule · 🩹 rescue candidates · 🔇 suppressed)        │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

Tooltip ⓘ on the unsectored line: *"Sector mutes match on the row's `sector` tag. Gmail rows often arrive without a sector. To mute these, add a company-scoped mute (matches via canonical_brand)."*

### Add-suppression form (inline expander)

```
┌─ + Add suppression ───────────────────────────────────────────────────────────┐
│                                                                                │
│   Scope:    (●) Sector    ( ) Company                                          │
│   Name:     [Canadian Insurers              ▾]                                 │
│              ↑ dropdown sourced from automation/sectors.py KNOWN list;         │
│                free text rejected (sector renames silently break entries       │
│                — caught during review; registry-validated only)                │
│   Duration: ( ) 30d   (●) 60d   ( ) 90d   ( ) No auto-lift  ⚠                 │
│   Reason:   [_________________________________________________________]        │
│                                                                                │
│   Coverage preview:                                                            │
│   ▸ 35 of 38 worklist rows in "Canadian Insurers"                              │
│   ▸ 3 unsectored — pass through (use company mute if needed)                   │
│   ▸ Tracker rows: 0 active (no archive prompt shown)                           │
│                                                                                │
│                                            [▷ Cancel]    [✓ Add suppression]   │
└────────────────────────────────────────────────────────────────────────────────┘
```

`No auto-lift` shows a yellow chip in the suppression list (`⚠ no auto-lift`) so manual entries don't quietly accumulate forever.

---

## State 10 — Tracker card with archive expander + suppression mirror

The Tracker card adds a thin `▾ Active suppressions` mirror so the user who muted from Review Queue can lift without round-tripping to Pipeline. Same source of truth (`suppressions.json`); two read views. `[Restore]` is context-aware.

```
┌─ ⏵ ⑥ TRACKER ─────────────────────────────  64 active · 12 to review · 7 archived ─┐
│                                                                                │
│   12 Found · 3 Watch · 5 Applied · 44 Closed   (excludes 7 archived)            │
│                                                                                │
│   [→ Review Queue (12)]    [→ Today's brief]    [→ Jobs Kanban]                │
│                                                                                │
│   ▾ Active suppressions (2)   ← mirror; same source as Triage card              │
│       🔇 sector  · Canadian Big 6 Banks · 60d                  [🔓 Lift]       │
│       🔇 company · Manulife · 80d                              [🔓 Lift]       │
│                                                                                │
│   ▾ Archived (7)                                                               │
│                                                                                │
│     ┌──────────────────────────────────────────────────────────────────────┐  │
│     │ RBC · Director, IRRBB                                                 │  │
│     │   status when archived: Found  ·  archived 2026-05-27                │  │
│     │   reason: muted with sector "Canadian Big 6 Banks"                   │  │
│     │   [Restore (still muted ⚠)]  ← context-aware: confirms whether to   │  │
│     │                                  also lift the sector mute           │  │
│     ├──────────────────────────────────────────────────────────────────────┤  │
│     │ Visa · Sr Mgr, Sales                                                  │  │
│     │   status when archived: Watch  ·  archived 2026-05-21                │  │
│     │   reason: manual                                                      │  │
│     │   [Restore]   ← simple — no associated suppression                    │  │
│     ├──────────────────────────────────────────────────────────────────────┤  │
│     │ ... 5 more ...                                                       │  │
│     └──────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│     Note: archived rows still block re-promotion of the same URL              │
│           (dedupe key preserved). Hard delete is not provided —                │
│           archive solves the documented problem without the                    │
│           dedupe-resurrection bug hard delete would re-open.                   │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### `[Restore (still muted ⚠)]` confirm

```
┌─ Restore RBC — Director, IRRBB? ──────────────────────────────────────────────┐
│                                                                                │
│   This row was archived as part of muting sector "Canadian Big 6 Banks".      │
│   The mute is still active (lifts 2026-07-26).                                 │
│                                                                                │
│   If you only restore the row, the next pipeline run will skip it again at    │
│   triage (suppression still applies). To make it visible end-to-end:           │
│                                                                                │
│   ☐ Also lift sector mute "Canadian Big 6 Banks"                               │
│                                                                                │
│                              [▷ Cancel]    [✓ Restore + (un-)mute as picked]  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Banner — suppression-aware states

### SUPPRESS-AWARE-EMPTY (worklist has rows, but all suppressed)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ⏸  All scored rows are suppressed (3 active mutes)                          ║
║                                                                              ║
║    Lifting any one of these would unlock candidates:                        ║
║       • Big 6 Banks (47 rows, lifts in 60d)                                 ║
║       • Insurers   (35 rows, lifts in 28d)                                  ║
║       • Manulife    (4 rows, lifts in 80d)                                  ║
║                                                                              ║
║                                          [→ Manage suppressions]            ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### SUPPRESS-EXPIRED (lookback window: 7 days, not 1)

The earlier draft fired this banner only on the day a mute expired — easy to miss for a sporadic user. Updated to a 7-day window post-lapse; after 7d, demotes to a yellow chip in the Triage card header.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║ ⏸  Suppression "Canadian Big 6 Banks" lapsed 4 days ago                     ║
║                                                                              ║
║    47 rows have re-entered triage since. 12 of those reached scoring;       ║
║    3 hit fit≥7. If conversion data hasn't improved, extend before next      ║
║    pipeline run; the 3 will otherwise be auto-promoted.                     ║
║                                                                              ║
║              [▷ Extend 60d]    [▷ Replace narrower]    [▷ Let lapse stand]  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

After 7 days post-lapse: banner gone, yellow chip in Triage card header (`⚠ Big 6 Banks: lapsed 8d ago, 4 promoted since`) until acknowledged.

`Replace narrower` opens the add-suppression form pre-filled, prompting the user to consider e.g., muting a single bank instead of all six.

---

## What this mockup section corrects from the original v3.1 wireframes

The first pass of these mockups, before review, drew several things Streamlit cannot render. Recorded here as a design-history note:

- **Floating overflow menu** (original State 8) — anchored to the right edge of the action row, outside the card border. Streamlit has no anchored popovers, no z-index, no portal. Replaced with `st.popover` placed in its own row beneath the action row, opening inline below.
- **`st.dialog`-based mute confirm** — width-constrained, re-runs the script per radio click, would re-load `worklist.json` per interaction. Replaced with the existing `_rq_apply_open` inline-confirm pattern (`ui/app.py:8325`), with sector-impact stats cached behind `@st.cache_data(ttl=60)`.
- **Inline `[Lift] [Edit reason] [Extend 30d]` buttons in a dataframe row** (original State 9) — three buttons per row would wrap on narrow viewports and have no codebase precedent. Replaced with one bordered container per suppression and `st.columns([3, 1, 1, 1])` for the icon-button row.
- **N≥25 confirm modal on manual selection** — patronising for a solo user and the threshold itself was arbitrary. Replaced with always-on `st.caption` pre-flight beneath the `[Send N selected]` button.
- **One-day-only SUPPRESS-EXPIRED banner** — easy to miss. Replaced with 7-day lookback window plus post-window chip.
- **Selection state described as "lost on rerun (intentional)"** — contradicted by the same wireframe's "4 selected" footer. Replaced with `st.session_state["scoring_selected_urls"]: set[str]` keyed on URL, derived into the checkbox column each render.
- **Three archive entry points** (per-row button + overflow menu item + mute-modal checkbox) — duplicate doors to one action. Reduced to two with differentiated intent: per-row button (direct) and mute-modal checkbox (coupled to suppression). Overflow menu has only mute-sector / mute-company.

Full rationale for each correction lives in `pipeline_redesign.md` § "v3.1.1 — review-validated revisions."
