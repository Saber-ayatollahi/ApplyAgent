# Pipeline UI redesign

Single-source-of-truth for the v3 redesign of the 🎯 Pipeline page.

## Problem

Current UI has 4 tabs (Run / Worklist / Scored / History) + 6 panels (live, two-sources, latest outputs, gmail trash, scorer progress, banners). Asks the user to scan 7 surfaces to answer 3 questions: *where am I?*, *what now?*, *let me drill in*. The "Score worklist (1,433)" button stays red after scoring finishes — because the count uses the whole pool and the freshness flag (`is_new_since_last_score`) is stale by design.

Result: the page can't even tell *itself* whether scoring is the next step. So neither can the user.

## Goal

A vertical pipeline page that answers "what now?" in **one banner** at the top, then shows each stage as a card top-to-bottom, with downloads + drill-in inside each card. Tabs gone. State derived from disk every render — no stale flags.

## The 6 stages

```
INPUTS         🛰 scrape + 📬 gmail        (raw row sources)
   ↓
WORKLIST       deduped pool                (what scoring reads)
   ↓
TRIAGE         rule-based Stage-1 filter   ★ NEW — was hidden
   ↓
SCORING        LLM Stage-2 evaluation
   ↓
AUTO-PROMOTE   scored → tracker
   ↓
TRACKER        user's job pipeline         (downstream of agent)
```

Six is more than four, but each step has a real artifact + drop set the user might want to inspect or extract. The TRIAGE step (★) was previously buried in the Stage-1 drops sheet of the audit pack — making it a stage exposes WHICH rows the keyword/level rules killed before any LLM saw them, and lets the user rescue rows the rules over-reject.

## What "dry run" is

`auto_promote.py` is the only stage that mutates `data/job_tracker_data.json` — your tracker, holding applied dates, notes, status changes. Re-running scrape/score writes to `automation/outputs/` which is cheaply re-derivable; re-running promote risks corrupting state you care about.

- Without `--commit`: full classification + prints what would happen, **no write**.
- With `--commit`: writes.

That's "dry run". v3 renames the buttons:
- `[Dry-run]` → **[Preview changes]** — runs classification, opens an expander with the diff (N added, M skipped by reason, K expired)
- `[Commit]` → **[Apply to tracker]** — only enabled after a Preview, only commits the previewed diff

Two-step UX, no jargon. Other stages don't need this because their outputs are idempotent.

## Banner state machine

A single primary CTA at the top of the page, computed every render from on-disk state. **Pure function**: `compute_next_action(state) → Banner`. Lives in `ui/pipeline_state.py`, unit-testable without Streamlit.

### State vars (computed at render, never read from stale disk flags)

| Var | How computed |
|---|---|
| `scrape_age_h`, `gmail_age_h` | mtime of latest `scan_*.json` / `scan_gmail_*.json` |
| `worklist_total` | `len(worklist.json.results)` |
| `triage_passed`, `triage_dropped` | from `worklist_scored.json` `stage1_passed`/`stage1_dropped` |
| `billable_count` | `worklist URLs ∖ scored URLs ∖ fit_cache files` (set arithmetic, NOT `is_new_since_last_score` flag) |
| `cached_count` | count of `fit_cache/<hash>.v2.json` files matching worklist URLs |
| `reusable_count` | scored rows reusable via 2nd-chance read, **filtered** to exclude `bad_verdict\|bad_score\|bad_reasons` placeholders |
| `promotable_count` | `worklist_scored.json` rows above `--min-score` threshold not in tracker |
| `active_runs` | LIST of `{label, state, pct}` from `scan_runner.list_runs()` (multi-job is real) |
| `stage_outcomes` | per-stage status from latest `outputs/pipelines/pipeline_*.json` (not the rolled-up `last_run_state`) |
| `last_failure` | most recent failed run, structured |
| `quarantine_ratio` | `quarantine / (quarantine + worklist_total)` |
| `recent_promote_count` | rows promoted in last commit, decays over ~10 min for success-feedback |
| `api_key_valid`, `gmail_connected` | live checks |
| `pending_scheduled_run` | optional Windows task ETA, if registered |
| `scoring_concurrency` | from settings — affects time estimate |

### Priority ladder (higher rule wins)

```
1. SAFETY     quarantine_ratio > 0.5             → 🔴 most rows corrupt — investigate
2. ACTIVE     any active_runs                     → 🟡 [job] N% [Stop]
3. RECENT     fail within 30min on bottleneck     → 🔴 retry <stage>
              (failed scrape with usable worklist → green CTA wins)
4. PROMOTE    promotable >= 1                     → ▶ Promote N (fast, free)
5. REVIEW     just scored, 0 promotable, ≥1 verdict → ▶ Review verdicts
6. SCORE      billable + reusable_filtered > 0    → ▶ Score N (cost split inline)
              AND api_key_valid (else chip + skip)
7. REFRESH    max_input_age > 24h                 → ▶ Refresh inputs
8. EMPTY      no worklist                         → ⏸ Set up Gmail + scrape
9. DEFAULT                                         → ✅ Up to date · next nightly Xh
```

**Why Promote before Score:** Promote is seconds, free, deterministic. The user gets new tracker rows to act on now. The 1,200 unscored will still be there — scoring isn't time-sensitive, but having usable tracker rows is. Anti-argument ("but maybe scoring would surface a higher-fit role first") is a false economy: the threshold is `fit≥7`; new candidates ADD to the queue, don't displace the existing promotables.

**Chips, not states**: `🔑 API key invalid` doesn't block when scoring isn't the next action — promote works without a key. Same for `⚙️ Gmail not connected`. Render as chips composed into the action banner; never make them the banner alone.

**Success-feedback decay**: when `last_promote_h < 0.2`, overlay `✅ Promoted N · Open Tracker` on top of whatever the next CTA is, for ~10 minutes. Gives the user closure on what they just did.

## Stage card layout

Each card has the same skeleton:

```
[status-pill] [stage name]              [headline metric]
[1-line context: counts, ages, drops]
▸ Inspect (sub-tabs)             📊 xlsx  📄 json
[primary action button]   [advanced gear ⚙]
```

Status pills (6 levels): `🟢 healthy`, `🟡 stale/aging`, `🔴 failed/blocking`, `⏸ empty/no data`, `⏵ awaiting your review`, `⚠️ quarantine`.

Per-stage details below.

### ① INPUTS

| Field | |
|---|---|
| **Headline** | total rows from both sources |
| **Context** | per-source counts + ages + drop bits (geo, quarantine) |
| **Pill rules** | 🟢 if newest input < 24h · 🟡 if 24-72h · 🔴 if both > 72h · ⏸ if no inputs |
| **Inspect** | per-source row preview · drop reasons |
| **Downloads** | each source: `scan_*.json` + `scan_to_xlsx`, `scan_gmail_*.json` + `gmail_scan_to_xlsx` |
| **Actions** | `[Refresh scrape]` `[Refresh Gmail]` (per-source) |
| **Advanced** | scrape strategy (full/core/ats/linkedin/expansion), days window |

### ② WORKLIST

| Field | |
|---|---|
| **Headline** | pool size after dedup |
| **Context** | source breakdown (🛰/📬/🔁), merge count, quarantine count |
| **Pill rules** | 🟢 if rebuilt within 1h of newest input · 🟡 if drift · ⚠️ if quarantine_count > 0 |
| **Inspect** | sub-tabs: Recent additions · Quarantine · Merges · By source |
| **Downloads** | `worklist.json` + `worklist_to_xlsx` (Pool / Merges sheets) |
| **Actions** | `[Force rebuild]` (rare — auto-rebuilt by scrape/gmail) |
| **Advanced** | gmail window days (rolling pool) |

### ③ TRIAGE ★

| Field | |
|---|---|
| **Headline** | passed / dropped split |
| **Context** | top drop reasons (e.g., "412 no_strong_keywords · 156 negative_term · 137 level_mismatch") |
| **Pill rules** | 🟢 if drop ratio reasonable (<70%) · 🟡 if > 70% · 🔴 if 100% (rules misconfigured) |
| **Inspect** | sub-tabs: All drops · By rule · Rescue candidates (high-keyword score that still got dropped) |
| **Downloads** | new `triage_to_xlsx(worklist_scored.json)` — sheets: Passed / Dropped (with rule reasons) |
| **Actions** | `[Rescue selected rows]` — adds force-include URLs to next score run |
| **Advanced** | view the rule definitions (read-only ref to fit_scorer.py constants) |

This stage previously hidden; making it visible is the #1 ask from the user.

### ④ SCORING

| Field | |
|---|---|
| **Headline** | unscored rows + cost split |
| **Context** | "1,206 billable · 287 free re-score · last scored 7d ago" |
| **Pill rules** | 🟢 if billable=0 · 🟡 if billable < 100 · 🔴 if > 100 · ⏸ if triage didn't pass anything |
| **Inspect** | sub-tabs: Top fits · By sector · Verdicts (apply_now / tailor_and_apply / watch / skip) · API errors |
| **Downloads** | `worklist_scored.json` + `scored_to_xlsx` (Scored / Stage-1 drops sheets) |
| **Actions** | `[Score N rows]` — cost + ETA inline · `[⚙️ Force rescore subset]` |
| **Persistent expander** | **Score one URL** (manual side-channel — currently lives in Run tab, moves here) |
| **Advanced** | concurrency, model override (Haiku/Sonnet), retry-failed |

### ⑤ AUTO-PROMOTE

| Field | |
|---|---|
| **Headline** | promotable count at current threshold |
| **Context** | "12 ready at fit≥7 · last promote 7d ago · added 3 last run" |
| **Pill rules** | 🟢 if 0 promotable (caught up) · ⏵ if ≥1 promotable AND user hasn't reviewed in 24h · 🔴 if last commit failed |
| **Inspect** | sub-tabs: Would add · Would skip (with reason: dupe/below_score/geo/verdict) · Last commit history |
| **Downloads** | `promote_report_*.json` + `promote_to_xlsx` (Promoted / Skipped sheets) |
| **Actions** | **two-step**: `[Preview changes]` opens the diff inline → `[Apply to tracker]` (enabled only after preview) |
| **Advanced** | `--min-score`, `--include-watch`, `--auto-tailor`, `--expire-stale` |

### ⑥ TRACKER

| Field | |
|---|---|
| **Headline** | total rows + status breakdown |
| **Context** | "12 Found · 3 Watch · 5 Applied · 44 Closed" |
| **Pill rules** | 🟢 always (it's downstream of agent decisions, not a "needs work" target by itself) · ⏵ if Found count > 0 (review-queue prompt) |
| **Inspect** | abbreviated row preview (full goes to Jobs Kanban) |
| **Downloads** | `data/job_tracker_data.json` + tracker-specific xlsx (one sheet per status) |
| **Actions** | deep-link buttons: `[Review Queue (12)]` `[Today's brief]` `[Jobs Kanban]` |
| **No advanced** | tracker mutations happen on downstream pages, not here |

## Open issues from the design review

### Real (must-fix in this commit)

1. **Race condition in Review Queue** — `_rq_apply_action` writes `data/job_tracker_data.json` directly; `auto_promote._commit_mutator` writes through the `safe_json.mutate_json` portalocker lock. The new prominent `[Apply to tracker]` button invites simultaneous mutations. Fix: route Review Queue through the same lock.
2. **`is_new_since_last_score` is stale-by-design** — only `worklist.rebuild()` updates it. Banner must NEVER read it directly; recompute from `worklist_scored.json` URLs ∪ `fit_cache/` listing every render.
3. **Reusable count overstates "free"** — second-chance reuse skips rows with `bad_verdict | bad_score | bad_reasons` placeholders. Quality-filter before quoting "0 cost."
4. **Stage outcomes per pipeline run** — `last_run_state` rolled up from a multi-stage pipeline run loses the "scrape ok, score ok, promote failed" detail. Banner needs `outputs/pipelines/pipeline_*.json` per-stage status to recommend the right retry.

### Punted to v4

- **Rescue dropped triage rows** — design includes the button, implementation defers. Today's rescue path is `fit_scorer.py --only-url <URL>` (singular, repeated); a UI bulk-rescue handle would batch these calls. (Earlier draft of this doc named a `force_include_urls` feature — no such code exists; corrected during review.)
- **Cost ledger guardrails** — block large scoring runs that would push past daily/weekly budget.
- **Cache health** — surface `fit_cache/` corrupt-file count, age distribution, hit rate over last N runs.

## v3.1 — feedback loops and selection control

The original v3 design was a *visibility* upgrade: surface every stage, show what's stale, name the next action. It assumed the threshold-based promote (`--min-score 7` → tracker) was the right model.

User feedback exposed three gaps the original v3 did not address:

1. **No way to slice and dice scored rows and commit a hand-picked subset.** Threshold-only promote is fine when the threshold matches taste; it doesn't accommodate "skip these 4 even though they cleared the bar."
2. **No way to remove a job from the tracker.** Status flips (Watch/Applied/Expired) preserve the row forever. There is no "I don't want to see this anymore."
3. **No feedback loop for sector- or company-level conversion failure.** "I applied to 14 Big 6 bank roles, got 1 interview, want to mute that lane for 60 days" has nowhere to land. Next week the same banks come back with the same fit≥7 scores. The user re-rejects them. Treadmill.

v3.1 layers four additions on top of v3 without changing the 6-stage skeleton:

### A. Suppression list — `data/suppressions.json`

A small disk-backed config that triage consults before passing rows to scoring or promote. Shape:

```json
{
  "sectors":  [{"name": "Canadian Big 6 Banks", "until": "2026-07-26",
                "reason": "1 interview / 14 apps", "added": "2026-05-27"}],
  "companies":[{"name": "RBC", "until": "2026-08-01",
                "reason": "ghosted x2", "added": "2026-05-27"}]
}
```

Design rules:

- **TTL required.** No permanent mutes — Saber's career situation changes. Default offered: 30 / 60 / 90 days. Manual `until: null` allowed but flagged in UI as "no auto-lift" with a yellow chip.
- **Applied at triage**, not worklist. Suppressed rows still appear in `worklist.json` (auditable pool) and in the triage Drops sub-tab with `rule_reason: suppressed_sector_60d` so the user can see what was hidden and why.
- **Hard skip by default** — no LLM call, no API cost. Advanced toggle later for "soft suppress" (score but don't promote) when conversion-feedback maturity makes it useful.
- **Granularity v1: sector + company.** Combos (e.g., sector AND title-regex) and sector-with-company-overrides are v4.
- **Unsectored rows skipped.** Many Gmail rows have no sector tag; conservative default is to *not* apply sector suppression to them. Company suppression applies if company name matches.
- **Concurrency-safe writes.** Same `safe_json.mutate_json` portalocker lock as the tracker — suppression edits and a running promote should not corrupt each other.

### B. Manual scored → tracker selection

Add a checkbox column to the Scoring card's `Inspect → Top fits` (and `By sector`, `Verdicts`) sub-tabs. Below the dataframe: `[▶ Send N selected to tracker]`.

The button does **not** write tracker JSON from Streamlit. It calls `auto_promote.py --commit --only-urls <tempfile>` so:

- Same `safe_json.mutate_json` lock as the threshold-based path.
- Same geo gate, dedupe, and verdict→status mapping.
- Same `promote_report_*.json` audit trail (now with `selection_mode: "manual"`).

Manual selection **overrides `--min-score`**: user explicitly chose, respect it. Geo gate stays (hard correctness boundary). Below-threshold rows in the selection are flagged in the report, not silently dropped.

Confirmation modal when selection ≥ 25 rows ("Add 25 to tracker — exceeds typical Found queue depth"). Below 25, no modal — fluency over ceremony.

### C. Tracker archive (not hard delete)

New field on tracker rows: `archived: true | false` (default false). Effects:

- Hidden from Review Queue, Today's brief, Jobs Kanban active views.
- **Still in dedupe** — promote will not re-add the URL. This is the entire point: hard-delete causes resurrection on the next scan; archive does not.
- Status preserved. Archive is orthogonal to outcome (an Applied job can be archived without losing application history).
- **Distinct from Expired.** Expired = the posting closed. Archive = "I don't want to see this." Different semantics, different report bucket.

UI:

- Per-row `🚫 Archive` button on Review Queue card and in Jobs Kanban row menu.
- New Tracker view: `▸ Archived (47)` expander listing archived rows with `[Restore]` per row.
- Archive page never auto-purges; user lifts manually.

### D. Mute-from-Review-Queue (closes the loop)

The Review Queue is where the user sees an actual unwanted role; it's the highest-signal moment to capture the suppression intent. Add a secondary action, not a primary button (the primary path is still acting on the job):

```
[📌 Watch]  [✅ Apply]  [❌ Expire]  [🔗 Open JD]  [⏭]
                                                  [⋯ More ▾]
                                                       🔇 Mute sector "Canadian Big 6 Banks"
                                                       🔇 Mute company "RBC"
                                                       🚫 Archive this job
```

Clicking `🔇 Mute sector` opens a modal: duration picker (30 / 60 / 90 d) + reason field, with the current job auto-archived on confirm. Writes to `suppressions.json`. The next pipeline run skips the muted sector at triage.

This single interaction is what closes the Big-Six bank treadmill: the bank rows that prompted the user's frustration become the moment the suppression is recorded.

### How v3.1 changes the existing cards

| Card | Change |
|---|---|
| ③ TRIAGE | Add `▸ Active suppressions (N)` expander listing entries with `[Lift]` per row + `[+ Add suppression]` form. Drop reasons in the inspect sub-tab now include `suppressed_sector_*` / `suppressed_company_*`. |
| ④ SCORING | Inspect sub-tabs gain a checkbox column + `[Send N selected to tracker]` action below the dataframe. |
| ⑤ AUTO-PROMOTE | Headline now reads "12 ready at fit≥7 *(after suppressions)*" so the user knows the count is post-filter. Inspect's `Would skip` sub-tab adds a `suppressed` reason bucket. |
| ⑥ TRACKER | Adds `▸ Archived (N)` expander. Status breakdown unchanged (archive is orthogonal). |

### Banner-copy additions

```
SUPPRESS-AWARE-EMPTY  ⏸ All scored rows suppressed (3 active mutes)
                       [→ Review suppressions]
SUPPRESS-EXPIRED      ⏸ Suppression "Big 6 Banks" expired today
                       [→ Lift / Extend / Replace]
```

Both states fall between EMPTY and DEFAULT in the priority ladder (rule 8.5).

### Why these four together (not a subset)

The four are coupled. Manual selection without archive means a hand-picked job lives in the tracker until heat death. Archive without suppression resurrects on the next scrape. Suppression without a UI to add it from the moment of frustration (Review Queue) requires a separate workflow no one will use. The set is the minimum coherent unit.

## v3.1.1 — review-validated revisions

The v3.1 design above is the product of one round of design without code review. Two critique passes (one UI, one backend) ran against it independently and converged on four risk clusters. This section records the corrections — kept separate from §v3.1 so the design history is auditable, not rewritten.

The single most damaging pattern in the original v3.1 was **silent failure**: the design promised feedback and selection but at multiple layers (selection state, suppression matching, archive migration, mute atomicity) would fail without telling the user. A feature that lies erodes trust faster than a feature that's missing. The corrections below close those silent-failure modes.

### Cluster A — Selection state must persist across reruns and filters

**Problem.** The mockup's "4 selected · [Send 4 to tracker]" footer contradicts the doc's claim that selection is "lost on rerun (intentional)." Streamlit reruns the script on every interaction; the existing `st.data_editor` in `ui/app.py:5598` matches state by row index in the *new* DataFrame, so filtering 1,400→38 rows silently jumps selections to wrong rows. **Plus** the backend layer can quietly drop user selections: `auto_promote.py:317` skips `verdict=skip` rows entirely, so a user who selects a `skip`-verdict row gets a "Sent N to tracker" toast but only N-1 land.

**Fix.**
1. **Selection source-of-truth = `st.session_state["scoring_selected_urls"]: set[str]`**, keyed on URL (the only stable identity). Each render derives the checkbox column by `df["promote"] = df["url"].isin(state_set)`. On `st.data_editor` callback, diff the edited frame back into the set: `state_set ^= edited_urls_changed`. Filter changes become non-destructive.
2. **`--only-urls` honors every selection.** `verdict=skip` rows are promoted as `status=Watch, urgency=Low, tier=4` with `manual_override_skip_verdict: true` in notes. Below-threshold rows promote normally with `selection_mode: "manual_below_threshold"`. Never silently drop a user's explicit pick.
3. **Drop the N≥25 confirm modal.** Replace with always-on `st.caption` beneath the button: *"Will send 27 (4 below fit≥7, 1 will skip on suppression, 0 geo)"*. Threshold-based ceremony patronizes a solo user who knows what they selected.
4. **Per-row `selection_mode` in promote report.** Values: `threshold | manual | manual_below_threshold | manual_override_skip`. Report-level mode is `"threshold"` for a default run, `"manual"` when `--only-urls` is used, or `"mixed"` if both modes contributed rows in the same run. **`--only-urls` is EXCLUSIVE** — it pre-filters the scored input down to the URLs in the file (mirroring `--only-url`'s contract). Threshold-eligible rows the user did NOT pick are NOT silently included. Consequently `"mixed"` is unreachable from `--only-urls` alone in current invocations; the field is preserved for forward compatibility with future invocation modes that explicitly combine both populations. The Pipeline headline ("12 ready at fit≥7") derives from current `worklist_scored.json` post-suppression — never from `last_run_state.added`, which conflates threshold and manual runs.

### Cluster B — Suppression matching must use canonical keys + must be visible

**Problem (matching).** Suppressions key on free-text "RBC". Tracker carries `"company": "RBC"`, scrapes carry `"Royal Bank of Canada"`, Gmail carries `"RBC Capital Markets"`. `automation/brand_aliases.py:canonical_brand()` already exists for cross-source dedup but the original v3.1 didn't use it. Sector names live in `auto_promote.py:77` as a hardcoded const; renaming a sector silently breaks every entry pointing at the old name with no migration path.

**Problem (visibility).** "Unsectored rows skipped" is correct conservative behavior but invisible. Saber mutes Big 6 Banks, sees a Gmail-sourced RBC role appear in tracker next run (no sector tag → not suppressed), concludes the feature is broken.

**Fix.**
1. **Every suppression entry stores `name` AND `canonical_key`.** For companies: `canonical_key = canonical_brand(name).lower()`. Match condition: `canonical_brand(row.company).lower() == canonical_key`. Catches RBC ⇄ Royal Bank of Canada ⇄ RBC Capital Markets without per-entry alias maintenance.
2. **Sector registry is the new single source of truth.** New `automation/sectors.py` exposes `KNOWN: list[str]`, `TIER_OF: dict[str, int]`, and `is_known(name) -> bool`. `auto_promote.py` imports from it; `SECTOR_ROUGH_TIER` const is removed. Suppression entries with `name not in sectors.KNOWN` are dropped on read with a `SUPPRESS-INVALID` banner listing them.
3. **`version: 1` field on `suppressions.json`** for future migrations.
4. **Coverage column on `Active suppressions` table.** Display `47 of 51 rows · 4 unsectored — pass through` with tooltip. Same coverage line in the mute confirm: *"4 Gmail rows in this sector lack tags and will not be muted — review them in Triage Drops."* Optional: company-name pattern fall-through for unsectored rows (deferred to v4).
5. **Triage ordering = `negative_term → suppression → keyword/level`.** Negative-term is hard correctness (interns/sales never the lane); suppression is preference; keyword/level is taste. Ordering matches escalating reversibility.
6. **`--only-url` (rescue) overrides suppression** with `override_reason: manual_only_url` written to the row's `rule_reasons`. User can rescue a suppressed row, but the audit trail captures the override.

### Cluster C — Archive must migrate cleanly and propagate everywhere it matters

**Problem.** v3.1 named three read sites for the new `archived: bool` field. Audit found at least seven: Today's queue follow-up gate (`ui/app.py:2847`), Review Queue (`ui/app.py:8090+`), Jobs Kanban (`ui/app.py:5882+`), `auto_promote._classify_against` expire-stale logic (`auto_promote.py:367`), `morning_brief.py`, `outcome_feedback.py:179-188` (cold-lane denominator), and the NBA pipeline's lane multipliers. Plus: `_rq_apply_action` at `ui/app.py:8281` does naked `json.loads / save_tracker` — bypasses the `safe_json.mutate_json` lock that `auto_promote` uses, inviting a race the v3 doc already flagged but didn't yet fix.

**Problem (semantics).** Archive ≠ Expired. Archived `status=Applied` jobs should not nag follow-ups. Archived rows distort cold-lane math if counted as "active in lane." NBA scoring boost from a smaller active denominator post-archive *boosts* archived sectors, which is the inverse of intent.

**Fix.**
1. **Replace `safe_json.archive_job/restore_job` with `automation/tracker_ops.py`.** Pure functions over the tracker dict: `archive(t, id)`, `restore(t, id)`, `set_status(t, id, s)`, `is_active(job)`, `apply_followup_gate(job)`. Composed at edges via `mutate_json(TRACKER, lambda t: tracker_ops.archive(t, id))`. Keeps `safe_json.py` as a generic concurrency primitive — no domain logic.
2. **One-time migration at every tracker entrypoint startup.** New `automation/tracker_migrate.py` stamps `archived: False` on every row when `meta.schema_version < 3`, bumps to 3. Idempotent. Backed up via the existing `*.bak.YYYY-MM-DD.json` pattern.
3. **Single `tracker_ops.is_active(job)` helper** is the gate every read site routes through. Defined once: `not job.get("archived", False) and job.get("status") not in TERMINAL_STATUSES`. Grep-replace-and-verify pass across the seven sites.
4. **Follow-up gate widens.** `_NO_FOLLOWUP_STATUSES or job.get("archived")` gates nag suppression. Archive an `Applied` job → no more follow-up reminders, application history preserved.
5. **NBA cold-lane math.** Archived rows excluded from active-in-lane denominator; included in historical conversion math. Documented in the `project_nba_architecture` memory.
6. **`_rq_apply_action` race fix is no longer optional.** Replace the naked write at `ui/app.py:8289` with `mutate_json(TRACKER, lambda t: tracker_ops.set_status(t, job_id, new_status))`. One line, removes the race the doc has been flagging since v3.

### Cluster D — Mute + Archive needs an atomicity-or-recovery story

**Problem.** The mute modal performs two writes (`suppressions.json` + `tracker.json`) with two locks and no cross-file transaction. AV holds a lock past the 10s `safe_json.py:60` timeout; the suppression write succeeds; the tracker archive fails. User sees the toast "Muted, lifts 2026-07-26 · RBC archived" but the RBC row remains in Review Queue. Next click is Apply on a job in a sector they explicitly muted. This is the highest-signal interaction in v3.1 — if it can lie, the entire feature loses.

**Plus:** the suppression list itself has no audit trail. Click `[Edit reason]` once, the original is gone. Six months later, no record of why Big 6 was muted from May to July.

**Fix.**
1. **Order matters: suppression first, archive second.** Suppression is the higher-signal, less-frequently-corrected write. Lift on regret is one click; archive on regret is one click. Order = "preserve the more important state first."
2. **No pretense of atomicity.** Wrap both writes in a try/except. On second-write failure: append the deferred archive to `data/suppressions_pending_archives.jsonl` (`{ts, job_id, reason, attempts}`); show yellow toast *"Mute saved; archive of 'RBC — Director, IRRBB' deferred — retry from Review Queue"*; on next page load the UI checks the queue and offers a `[Retry archive]` button per pending entry. Don't roll back the suppression — it's the load-bearing write.
3. **Append-only event log = source of truth.** `data/suppressions_events.jsonl`: every `add | lift | extend | edit_reason` writes one line `{ts, action, scope, name, old, new, actor:"ui"}`. The active-state file `suppressions.json` is derived from the log on read; rebuildable from events. Subsumes the "history archive" — same file, two responsibilities (current state + audit trail).
4. **Lazy TTL expiry on read.** `suppressions.load_active()` filters `until is None or until > today`. Separate `load_recently_expired(window=7d)` powers the SUPPRESS-EXPIRED banner — 7d, not 1d, because the user is sporadic. Expired entries move to `data/suppressions_history.json` on next pipeline run or next mutation; never silently deleted.
5. **Snapshot suppressions at pipeline-run start.** `automation/pipeline.py` writes `runs/<run_id>/suppressions_snapshot.json` and passes the path through to subprocesses. A 22-minute pipeline run sees one consistent suppression state even if the user mutes mid-run. The UI's `[Lift]` button writes to live state; only the next pipeline run picks it up. Embedded snapshot makes audits reproducible six months out.
6. **Re-check at promote time.** `auto_promote._classify_against` re-reads the suppression snapshot and shifts any matching row into a new `suppressed_after_score` bucket in the promote report. Race-window selections surface in the report rather than silently passing or silently failing.
7. **`data/suppressions.json` is gitignored.** Reasons will be candid ("ghosted by RBC", "shitty culture"). Ship `data/suppressions.example.json` as the seed; `suppressions.load()` lazy-creates the live file from the example. Same pattern as `.env` / `.env.example`. Same gitignore for the events log, history, and pending-archives queue.

### UI hygiene corrections

These are smaller but still material:

- **Drop the floating `[⋯ More ▾]` menu fiction.** Streamlit has no anchored popover, no z-index, no portal. Replace with `st.popover("⋯ More")` placed in its own row beneath the action buttons — opens inline below the card, pushing later cards down. Honest about Streamlit's block flow. Wireframes corrected in the mockup doc.
- **Mute modal uses inline-confirm pattern, not `st.dialog`.** Mirror the existing `_rq_apply_open` pattern at `ui/app.py:8325`: `st.session_state["_rq_mute_open"] == job_id` flag, container with border, mounted beneath the card. Already proven; renders cleanly; no `st.dialog` width/rerun jank. Cache sector-impact computation behind `@st.cache_data(ttl=60)` so radio-clicks don't re-read 1,400 rows.
- **Single archive entry point.** Per-row `🚫 Archive` button on Review Queue card and Kanban row menu. Mute modal's archive checkbox stays (intent-coupled). Remove the `🚫 Archive this job` line from the `[⋯ More]` menu — duplicate of the per-row button. `[⋯ More]` reduces to mute-sector / mute-company.
- **Context-aware `[Restore]` on archived rows.** If the archived row's reason references a still-active suppression, the button reads `[Restore (still muted ⚠)]` and the click confirms with a "Lift sector mute too?" checkbox. Wires to the suppressions API. Solves the "I clicked Restore and nothing happened" trap.
- **Mute-confirm toast carries `[Undo]`.** The most common immediate-regret case is "did I mute the right scope?" — a one-click undo from the toast removes the need to navigate to the Triage card to find the entry and lift it.
- **Suppression admin mirrored on Tracker page.** The mute action lives on Tracker (Review Queue), the admin lives on Pipeline (Triage card). Add a thin `▾ Active suppressions (N)` expander to the Tracker page header so the round-trip stays on one page. Same source of truth (`suppressions.json`), two read views.
- **Triage-card per-suppression layout = bordered container per entry**, not inline buttons in a dataframe. `st.columns([3, 1, 1, 1])` per entry: name + scope (3 cols), `[🔓 Lift]` icon button (1), `[+30d Extend]` (1), click-name-to-edit-reason (1). Fits below 900px viewport without wrap.
- **Worklist headline acknowledges suppression.** *"1,206 unscored (200 hidden by 2 mutes)"* with tooltip listing the mutes. Audit pack's main Triage sheet adds a `suppressed_by` column (empty for non-suppressed rows) so a downstream xlsx reader can filter without cross-sheet joins.

### What's punted to v4

- **Outcome-feedback unification.** Backend reviewer suggested cross-referencing manual mutes with `outcome_feedback.py`'s auto-detected cold lanes via a unified `data/lane_signals.json`. Real concern, but with suppression at triage, the LLM never sees muted rows — so the "double-signal in prompt" risk is less acute than the four clusters above. Defer.
- **Promote dedupe semantics on suppression lift.** Worklist rows in a sector that gets muted then lifted 60d later: re-promote retroactively, or only on next score? Doc says "next score only," but the mechanism (`last_eligible_for_promote_at` timestamp on scored rows + `invalidate_scored_in_sector(name)` on lift) is its own design. Defer.
- **Granularity beyond sector + company.** Combos like "sector AND title-regex" or "company except director-level". Real but not load-bearing for the bank treadmill.
- **Hard delete on tracker.** Archive is sufficient for the documented problem. Hard delete would re-open the dedupe-resurrection issue archive was designed to close.

### Resolution of the "open questions for Saber"

Original §v3 left four open questions. Updated answers given v3.1.1:

1. **Tracker pill state:** `⏵ awaiting review` when active (non-archived) Found > 0. Confirmed.
2. **Recent runs:** thin expander at bottom of Pipeline; deep-links to Scan History page. Confirmed.
3. **Bundle the Review Queue race fix:** must bundle. The race fix is a one-line consequence of routing through `tracker_ops` + `mutate_json`, and the prominent `[Apply to tracker]` invites the race.
4. **TRIAGE rescue UX:** checkbox + bulk. Same pattern as scoring-card selection (Cluster A) — same `set[str]` keyed on URL state; same `[Rescue N selected]` action that shells `fit_scorer.py --only-url` per URL.

### Manual-selection vs. suppression precedence (resolved during E2E Round 2)

Two questions arose during integration testing that the spec didn't initially answer. Recording the decisions here so the Phase 3 UI builds against a single, documented contract.

**Q1: When `--only-urls` is passed, are threshold-eligible rows in the scored file ALSO promoted, or excluded?**

**Decision: EXCLUDED (exclusive semantics).** `--only-urls` pre-filters the scored input down to the URLs in the file, mirroring `--only-url`'s contract. The user's mental model is *"I picked these N; promote N"*. Additive behavior would silently include threshold-eligible rows the user did NOT pick — a P0 violation of the `[Send N selected]` UX. As a consequence, the run-level `selection_mode = "mixed"` is unreachable from `--only-urls` alone in current invocations; the field is preserved for forward compatibility with hypothetical future modes that explicitly combine populations.

**Q2: When the user manually selects a row via `--only-urls` that is currently suppressed by a sector or company mute, what happens?**

**Decision: PROMOTE WITH AUDIT.** The row goes to the tracker tagged `selection_mode: "manual_override_suppression"` with the would-be drop reason (`suppressed_sector_60d`) recorded in the row's `notes` field. The promote report's `suppressed_after_score` bucket also records the override with `promoted_anyway: true`. This mirrors `fit_scorer --only-url`'s rescue behavior (Cluster B item 6) — manual selection is explicit user intent, suppression is a preference signal that is *softer* than explicit selection. The user can lift the mute if they want a permanent fix; the override gives them an immediate exception with a clean audit trail.

**Threshold-mode rows in a muted sector still drop into `suppressed_after_score` (race-window catch).** The asymmetry is the design: bulk threshold promotion is implicit / automatic, so suppression wins by default; manual selection is explicit, so user intent wins. Same row, two outcomes depending on how the user invoked the run.

### Phase 2.5 — Suppressions CLI (operator UX)

The fresh-clone reviewer flagged that Phase 2 shipped the suppressions *engine* but no command-line surface, forcing the user to write Python (`from automation import suppressions; suppressions.add_sector(...)`) just to add a mute. That breaks the "tomorrow-ready" bar for the only persona who matters here.

`automation/suppressions.py` now exposes a subcommand CLI with seven verbs:

| Command | What it does |
|---|---|
| `add-sector NAME [--days N | --until DATE] --reason ...` | Mute a sector (lenient name match via `sectors.canonical`) |
| `add-company NAME [--days N | --until DATE] --reason ...` | Mute a company (canonicalized via `brand_aliases.canonical_brand`) |
| `list [--scope sector|company|all] [--include-expired] [--json]` | Inspect active mutes; pull last 20 expired from history if asked |
| `lift {sector|company} NAME` | Remove an active mute (no-op + audit event if absent) |
| `extend {sector|company} NAME --days N` | Push the `until` date forward |
| `edit-reason {sector|company} NAME --reason ...` | Update the reason field in place |
| `audit [--limit N]` | Tail the JSONL audit log |

Every verb supports `--json` so future UI work in Phase 3 (the SUPPRESSIONS section of the Pipeline page) can shell out instead of importing the module. The subprocess + in-process tests in `automation/_tests/test_suppressions_cli.py` lock the contract: 18 cases covering round-trips, mutual-exclusion guards (`--days` vs `--until`), no-op lift semantics, and the `__main__` entrypoint.

## v3.1.2 — permanent company exclude-list (source-level block)

Distinct from suppressions. Suppression is a TTL'd preference signal applied **at triage** — the company is still scraped and its rows still sit in the worklist; they just don't reach scoring/promote until the mute lapses. The exclude-list is a **permanent, source-level block**: the user picks companies (initially the 6 Canadian Big-6 banks) that should never be fetched or shown again. Driven by the user's actual ask — *"no longer want to see new jobs from the Big 6 Canadian banks."*

### Design

- **New module `automation/excludes.py`** mirrors `suppressions.py`'s lazy-seed + lock-safe persistence but is deliberately simpler: **no TTL, no reason, no audit/event log, no history, no pending-archive queue.** Live file `data/excludes.json` (gitignored), lazy-created from committed `data/excludes.example.json`. API: `load() -> set[str]`, `list_excluded()`, `is_excluded(name, snapshot=None)`, `add(name)`, `remove(name)`, `filter_targets(targets, snapshot=None)`, `filter_rows(rows, snapshot=None)`. CLI: `add`/`remove`/`list`/`--smoke`, all `--json`.
- **Canonical matching everywhere** via `brand_aliases.canonical_brand()`. This is load-bearing on the **scrape side too** (not just Gmail): `TD Asset Management` uses TD Bank's Workday tenant and `BMO Asset Management` uses BMO's, so a raw-name match would leave the sibling, which then queries the excluded bank's board and re-tags the jobs. Excluding `TD Bank` (key `td`) therefore also excludes `TD Asset Management`; the UI checkbox label names the affected siblings so it's not a silent surprise.
- **brand_aliases fix:** added `banque nationale` / `banque nationale du canada` / `banque nationale financiere` / `bnc` → `nbc`. Without these, `canonical_brand('Banque Nationale')` returned `banque` and a Quebec-sourced National Bank alert leaked past an NBC exclude.

### Four enforcement points (not three)

1. **Web scrape** — `jd_scraper.main()` calls `excludes.filter_targets(targets)` **after** the expansion-build and `--company`/`--sector` include filters, **before** `scan()`. So `_targets_signature` reflects the filtered set on both write and `--resume` (a stale checkpoint mismatches rather than resurrecting an excluded company), and the excluded tenant is never primed in `_wd_cache`.
2. **`jd_scraper --gmail` harvest loop** — drops alert rows whose company canonicalizes to an excluded key; `gmail_diag.dropped_excluded` records the count.
3. **Standalone `gmail_fetch.py`** (the UI "Refresh Gmail" button) — an audited `filter_rows` stage between the geo gate and the envelope write; `harvest_diagnostics.rows_dropped_excluded` + `excluded_dropped_rows` mirror the geo audit-trail shape.
4. **`worklist.rebuild()`** — **the primary can't-leak chokepoint.** rebuild() replays the latest web scan + the last 30 days of `scan_gmail_*.json` on every run, so without filtering here an excluded company's on-disk rows would re-materialize for ~30 days after the tick. Both `_add` paths are guarded (the Gmail guard sits after `_clean_alert_fields` so canonicalization sees the cleaned name); `stats.excluded_dropped` records the count. Points 1–3 become cost optimizations that also stop fetching; point 4 guarantees nothing on disk resurfaces.

### Why no score/promote guard is needed (downstream-propagation audit)

A review raised that `fit_scorer.py` and `auto_promote.py` don't re-check the exclude-list (unlike suppressions, which IS re-checked at promote time). Audited every retrieval/consumer path; the conclusion is that **filtering at the source propagates to every automated consumer**, so a downstream guard would be redundant:

- **`fit_scorer`** scores `worklist.json` (the rebuild-filtered pool) by default, or `--scan <file>` of a scan that `jd_scraper` already wrote post-exclude. Both inputs are clean.
- **`auto_promote`** promotes `worklist_scored.json`, derived from that clean pool.
- **`scan_delta` → `morning_brief --auto-add`** (the nightly auto-add-to-tracker chain) diffs the raw `scan_*.json`, which `jd_scraper` wrote **after** `filter_targets`. The delta is clean, so the auto-added rows are clean.

The invariant the user articulated: *"if a job is not retrieved it never makes it to the scorer."* Because exclusion happens at fetch, no excluded row exists on disk for a downstream stage to pick up. (The contrast with suppressions — which *are* re-checked at promote — is that suppression rows are deliberately KEPT on disk and only muted at triage, so a mute added mid-pipeline needs a second look; exclusion deletes the row at the source, so there's nothing to re-check.)

The one exception, `score_url.py`, is handled explicitly below.

### Fifth touch-point: `score_url.py` — warn but allow (manual override)

`score_url.py` (and its UI "Score this URL" button) is the deliberate manual-override path: paste a single JD URL the scraper missed (a friend's employer, a role outside TARGETS) and optionally `--add-to-tracker`. It does NOT route through `worklist.rebuild()`, so the exclude-list does not apply automatically. Per the user's decision this is **warn-but-allow**, not block: pasting the URL is explicit intent.

- When the resolved company canonicalizes to an excluded key, `score_url` prints a `⚠` warning carrying the stable marker phrase `"on the permanent exclude-list"` to stderr, then scores anyway. With `--add-to-tracker` it re-announces (`⚠ Adding an EXCLUDED company …`) so the override is never silent.
- The UI's `_render_score_url` greps the merged log for that marker phrase and renders a `🚫` warning banner above the verdict. The marker string is a cross-file coupling pinned by `test_excludes_score_url.py`.
- A malformed/unreadable exclude file never blocks a manual score (the check is wrapped in a swallow).

### UI

A checkbox admin (`_render_excluded_companies_admin()`) over the **canonical-deduped** TARGETS, grouped by sector (Big-6 first), mounted in `render_two_sources_panel()` (the shared ① Inputs entry). State model is **Cluster-A-safe**: `data/excludes.json` is the sole source of truth, read fresh each render; the checkbox `value` derives from disk membership and a change diffs against **disk** (never a seeded session value) then writes + reruns. De-dup-by-canonical avoids a `StreamlitDuplicateElementKey` crash on the RBC/TD/BMO pairs; the display label is the shortest raw name and names its siblings inline (`RBC ＋1`). An always-visible `🚫 N excluded: …names…` caption sits above the toggle (so an accidental tick is obvious at a glance) and the toggle auto-opens on first run (N==0) for discoverability. The scrape/Gmail/worklist funnel captions gain a `🚫 N excluded` bit. The suppression company-mute help cross-references the exclude control.

### Out of scope / deferred

- **Existing rows already in worklist/tracker before the tick** — untouched; the user archives them. Future rebuilds won't re-add them.
- **No `run_pipeline.py` change** — it subprocesses `jd_scraper`, which reads the file directly; no flag/env/snapshot pass-through needed (exclusion is applied synchronously at fetch/rebuild, unlike the minutes-long pipeline run that needs a frozen suppression snapshot).
- **Free-text add, sector-level exclude, TTL/reason/audit** — omitted by design; checkboxes over TARGETS, permanent until unchecked.
- **FR aliases for the other 5 banks** — only National Bank surfaces in French commonly; revisit if a leak is observed.

### Defense-in-depth deliberately NOT added

- **No `fit_scorer` / `auto_promote` exclude guard** — considered and rejected after the propagation audit above. Source-level filtering means no excluded row reaches them in any automated flow; a guard would be dead code on the normal path and would only fire if an operator hand-points `--scan` at a pre-exclude raw artifact (treated as an explicit override, same spirit as `score_url`).

### Implementation hardening discovered during integration

Three real defects were found and fixed while wiring this up (all regression-tested):
- **`excludes.py` must be bare-importable.** The UI and `run_pipeline.py` launch `jd_scraper.py` / `gmail_fetch.py` / `worklist.py` as bare scripts (`__package__ == ''`), and those import `excludes` with no degradation path — so a hard `from .safe_json import …` would crash a real scrape/rebuild. `excludes.py` dual-imports its own deps (try package, fall back to bare), mirroring `worklist.py`'s `brand_aliases` import.
- **Shared-mutable-default.** `_EMPTY_LIVE` as a module constant handed out via `dict(...)` (a *shallow* copy) shared its inner `companies` list, so the first `add()` on a not-yet-created file appended into the shared list and poisoned every later "empty" default — in tests AND in the long-lived Streamlit process. Replaced with an `_empty_live()` factory.
- **Malformed-field false match.** `_canon(["RBC"])` did `str(["RBC"])` → `"['RBC']"`, which `canonical_brand`'s substring match resolved to `rbc`, wrongly excluding a row with a list/dict company field. `_canon` now returns `''` for any non-`str` input.

Tests: `automation/_tests/test_excludes.py` (module + canonical + scrape/gmail filters + FR alias + shared-tenant + malformed-field + dormant fast-path), `test_excludes_worklist.py` (the rebuild chokepoint), `test_excludes_cli.py` (CLI + gitignore safety + UI dedup logic), `test_excludes_score_url.py` (warn-but-allow contract + the score_url↔UI marker-phrase coupling).

## v3.2 — Pipeline page split into 3 sub-pages (Refresh / Score / Promote)

**Supersedes** the original "tabs gone, one vertical scroll" design (§"Stage card layout") and retires the `_PIPE_VERTICAL` strangler-fig toggle + classic-tabs escape hatch. Driven by Saber's report that the single Pipeline page — one mega-scroll mixing input-gathering, scoring, and promote — is a *temporal-intent* overload (gather vs. evaluate vs. act). The 6 stage cards split 2-per-page:

- **① Refresh** = ① Inputs + ② Worklist (pull jobs in, build the worklist)
- **② Score** = ③ Triage + ④ Scoring (filter + LLM fit)
- **③ Promote** = ⑤ Auto-promote + ⑥ Tracker (promote into the tracker + act)

### Mechanism (low-risk view-dispatch)

The ~800-line preamble and the four `_render_*_card` closures stay exactly in place — **not** hoisted to module scope (that was considered and rejected as the higher-risk path: dozens of `_wstats`→`ctx.*` rewrites, each a latent `NameError`). Instead:

- The router matches the three page strings via one clause: `elif page in ("🎯 Pipeline · Refresh", "🎯 Pipeline · Score", "🎯 Pipeline · Promote")`. A `_pipe_view = page.rsplit("·",1)[-1].strip()` selects the view.
- Each of the 6 stage-card `with st.container(border=True):` blocks keeps its original 8-space indent; only the wrapping guard changes from the old `if not _PIPE_VERTICAL: … else:` to `if _pipe_view == "<View>":`. No card body moves or re-indents.
- View-specific chrome is guarded the same way: the nightly-refresh strip and the scrape pause/resume controls render only on **Refresh**; the funnel renders on **Refresh + Score** (Promote stays lean — the ⑤ card's promotable headline carries the end count); the banner, last-activity strip, and `_pipeline_live_panel()` render on **all three**.

### Nav + cross-page routing

- `_NAV_GROUPS["🎯 Pipeline"]` gains three children (`Refresh`/`Score`/`Promote`); the existing sub-radio machinery renders them with no further change. Default = Refresh.
- **Back-compat:** `_LEGACY_PAGE_TO_GROUP["🎯 Pipeline"] = ("🎯 Pipeline", "Refresh")` so a saved nav state / AppTest / external write using the old string lands on Refresh. The legacy shim was tightened to **only seed the sub-page when one isn't already chosen** — otherwise the Refresh alias would clobber an explicit Score/Promote pick (or a banner CTA jump) every rerun.
- **`_route_banner_cta` cross-page fix (load-bearing):** with the cards now on separate pages, opening an inspect toggle is no longer enough — the CTA must also switch the nav to the page hosting that card. A `_TOGGLE_TO_SUBPAGE = {worklist:Refresh, triage:Score, scoring:Score, promote:Promote}` map drives setting `_applyagent_nav` + `_nav_sub_🎯 Pipeline` alongside the toggle. Same proven pattern as the ⑥ Tracker "→ Jobs Kanban" deep-link.

### Next-action banner is Promote-only

The next-action banner (`compute_next_action`) renders **only on the ③ Promote view**. The Dashboard already owns the cross-surface "what now?" via its own richer Next-Best-Action hero (`compute_next_best_action` — jobs + recruiters + outcomes with lane multipliers), and a dominant red "Promote N" CTA on the *Refresh* (pull-jobs-in) and *Score* views was off-key. The snapshot is still **computed** on every view (the ⑤ Auto-promote card consumes `_promotable_n`); only the visible banner is gated to Promote. Pinned by `test_banner_cta_is_a_live_button_on_promote` (CTA present on Promote) + `test_banner_absent_on_refresh_and_score` (no `_banner_cta_*` button on Refresh/Score).

### Fixed: "Next step" panel contradicted the banner (pre-existing)

The last-activity strip's "Next step" hint decided "scored?" by **filename-stem match** (`scan_<stamp>` in the scored filename). Since the pipeline scores the merged worklist (`worklist.json` → `worklist_scored.json`, the v3 worklist contract), the stem never matched and it falsely said "Scan exists but not scored yet" even with 512 real LLM scores on disk — directly contradicting the banner's "N ready to promote". Now decided by **mtime freshness** (scored artifact is current iff at least as new as the latest web scan), which is naming-convention-agnostic.

### ② Score — operational "Last scoring run" status table

The ④ Scoring card gained an always-visible status block (`_render_scorer_status`, distinct from the live `render_scorer_progress` panel) so the user sees *how scoring went* without opening the heavy verdict inspector: an `st.metric` grid of **Input · Triaged · Scored · Errors / Cached(free) · New(paid) · Model · Last run (age)**, a fatal `api_error` warning, and a collapsed **📜 Scoring logs** expander (tails the latest score/pipeline run via `scan_runner`). All sourced from on-disk artifacts already written — `fit_scorer_progress.json` (cache_hits, cost.llm_calls, errors, cost.per_model) + `worklist_scored.json` (stage counts, scored_at, api_error); model display falls back to the `FIT_SCORER_MODEL` constant when per-run attribution is absent. While a run is live it defers to the live progress panel. No scorer/worklist code changed — read-only.

### ① Refresh — worklist auto-opens after a session rebuild + freshness header

The ② Worklist inspect table defaults closed (perf — ~1,400 rows). It now **auto-opens once** when a scrape/Gmail/rebuild completes *during the session*, detected by comparing `worklist.status().rebuilt_at` against a session cache (`_seen_rebuilt_at`). The cache is **seeded on the first Pipeline render** so a cold load stays closed; it's one-shot per distinct `rebuilt_at` (the user can re-close until the next rebuild). When open, a `🕒 Worklist rebuilt <ts>` caption sits at the top so freshness is always visible. The header dedup caption was enriched from raw source counts to also show `✂️ N exact + M near-dup merged · 🆕 K new since last score` (from the envelope's `dedup_stats` + `stats`). Pinned by `test_worklist_closed_on_cold_load`, `test_worklist_autoopens_after_session_rebuild`, `test_scorer_status_renders_on_score`, `test_worklist_dedup_line_present_on_refresh`.

### Out of scope / retained

- **Footer (audit pack + run history)** lives on **Promote** only — the "end of the pipeline, grab everything" surface.
- The intra-page stage-jump rail is dropped (each view has 2 cards, no scroll tax; cross-stage movement is the sub-radio).
- Per-card `_vc_inspect_*` defaults preserved (scoring/promote open by default; worklist/triage closed for first-load perf).

Tests: `tests/test_pipeline_vertical_layout.py` rewritten for the 3 views (per-view header assertions incl. negative "no other view's card leaks", audit/launch on Promote, worklist-inspect on Refresh, bulk-confirm on Score, plus a regression guard that `_route_banner_cta` sets the right sub-page). `tests/test_pages.py` + `test_consolidated_nav.py` + `test_populated_tracker.py` updated to the 3 page strings. `automation/_tests/test_pipeline_state.py` unaffected (the pure banner-state functions are untouched).

## Implementation scope

### v3 (visibility)

| File | Δlines | Change |
|---|---|---|
| `ui/pipeline_state.py` (new) | +~150 | Pure-function state derivation + `compute_next_action`; no Streamlit imports; unit-testable |
| `ui/app.py` | -~600 / +~400 | Replace Pipeline-page tabs with 6 stage cards; remove dead "Latest outputs" panel (each card carries its own downloads); banner widget at top |
| `automation/_tests/test_pipeline_state.py` (new) | +~120 | Priority-ladder test cases from the state-machine review (≥15 scenarios). *(Landed in `automation/_tests/`, beside the modules under test; the UI-card render tests live in `tests/test_pipeline_vertical_layout.py`.)* |
| `automation/audit_pack.py` | +~30 | Add `triage_to_xlsx(worklist_scored.json)` |
| Review Queue race fix | +~20 / -~10 | Route `_rq_apply_action` through `safe_json.mutate_json` |

### v3.1 (feedback loops + selection control)

| File | Δlines | Change |
|---|---|---|
| `automation/suppressions.py` (new) | +~180 | Load/save/lift API for `data/suppressions.json`; lazy TTL expiry → `suppressions_history.json`; canonical-key matching via `brand_aliases.canonical_brand`; sector registry validation; append-only event log to `suppressions_events.jsonl`; lock-safe writes |
| `automation/sectors.py` (new) | +~40 | Single source of truth for sector names + canonical-key map; replaces the duplicated `SECTOR_ROUGH_TIER` const in `auto_promote.py` (which becomes `from sectors import TIER_OF`) |
| `data/suppressions.json` | gitignored | Live file is per-machine. `data/suppressions.example.json` ships as `{"version": 1, "sectors": [], "companies": []}` seed; `suppressions.load()` creates the live file from example on first read |
| `automation/tracker_ops.py` (new) | +~120 | Pure functions: `archive(t,id)`, `restore(t,id)`, `set_status(t,id,s)`, `is_active(job)`, `apply_followup_gate(job)`. No I/O. Composed via `mutate_json(TRACKER, lambda t: tracker_ops.archive(t, id))` at every call site |
| `automation/tracker_migrate.py` (new) | +~50 | One-time migration: stamps `archived: False` on every row when `meta.schema_version < 3`; bumps `meta.schema_version`. Idempotent; runs at startup of any tracker-reading entrypoint |
| `automation/fit_scorer.py` | +~50 | Triage ordering becomes `negative_term → suppression → keyword/level`; emits `suppressed_sector_*` / `suppressed_company_*` drop reasons; `--only-url` overrides suppression with `override_reason: manual_only_url` written to `rule_reasons` |
| `automation/auto_promote.py` | +~70 | Add `--only-urls FILE` mode; manually-selected `verdict=skip` rows are promoted as `Watch / tier 4` with `manual_override_skip_verdict: true` (never silently dropped); re-checks `suppressions.is_suppressed(row)` at promote time → `suppressed_after_score` bucket in promote report; per-row `selection_mode ∈ {threshold, manual, manual_below_threshold, manual_override_skip}`; report-level `selection_mode = "mixed"` when both present; remove duplicated `SECTOR_ROUGH_TIER` (now from `sectors.py`) |
| `automation/pipeline.py` (and direct fit_scorer/auto_promote entrypoints) | +~30 | Snapshot `suppressions.json` to `runs/<run_id>/suppressions_snapshot.json` at run start; pass snapshot path through subprocesses so the run sees one consistent suppression state |
| `ui/app.py` (Scoring card) | +~120 | Selection state: `st.session_state["scoring_selected_urls"]: set[str]` keyed on URL (NOT row index); checkbox column derived from set membership each render; filter changes are non-destructive. `[Send N selected]` shells `auto_promote.py --only-urls`. Drop the N≥25 confirm modal — replace with always-on `st.caption` pre-flight summary below the button. Pre-flight shows below-threshold count, suppressed-by-sector count, geo-skip count |
| `ui/app.py` (Review Queue) | +~80 | Drop the floating `[⋯ More ▾]` fiction. Render an inline `st.popover("⋯ More")` button in its own row beneath the action row (Streamlit-honest — opens inline below). Mute modal uses the existing inline-confirm pattern at `ui/app.py:8325` (mirrors `_rq_apply_open` pattern), NOT `st.dialog`. Mute-confirm toast carries `[Undo]` action that calls `lift()` directly. Replace naked `_rq_apply_action` write with `mutate_json(TRACKER, ...)` lambda |
| `ui/app.py` (Triage card) | +~80 | `Active suppressions` table per-row layout: each entry as its own `st.container(border=True)` with `st.columns([3, 1, 1, 1])` — `[Lift]` icon-button, `[+30d]` extend, click-row-to-edit reason. Coverage column: `47 of 51 rows · 4 unsectored — pass through` with tooltip explaining unsectored fall-through. `[+ Add suppression]` form sector picker is a dropdown of `sectors.KNOWN` (no free text) |
| `ui/app.py` (Tracker / Kanban) | +~70 | Single archive entry point: per-row `🚫 Archive` button on Review Queue card and Kanban row menu only. Archive checkbox in Mute modal stays (coupled, different intent). `[⋯ More]` keeps mute-sector / mute-company only. `[Restore]` becomes context-aware: if archived row's reason references an active suppression, prompt "Lift sector mute too?" with checkbox |
| `ui/pipeline_state.py` | +~80 | Headline counts derive from current `worklist_scored.json` post-suppression (NOT `last_run_state.added`). New banner states: `SUPPRESS-AWARE-EMPTY`, `SUPPRESS-EXPIRED` (7-day window post-lapse, then demotes to chip). Coverage stats include unsectored-row count |
| `automation/audit_pack.py` | +~30 | `triage_to_xlsx` adds `Suppressed` sub-sheet AND `suppressed_by` column on the main Triage sheet; `promote_to_xlsx` adds per-row `selection_mode` column |
| `automation/_tests/test_suppressions.py` (new) | +~150 | TTL lazy expiry; canonical-key matching (RBC vs Royal Bank of Canada vs RBC Capital Markets); sector registry validation; unsectored-row pass-through; lock contention with promote; mute+archive partial-failure recovery via `suppressions_pending_archives.jsonl`; snapshot-at-run-start behavior |
| `automation/_tests/test_tracker_ops.py` (new) | +~100 | `archive` / `restore` / `is_active` / followup-gate semantics; migration idempotency; archived-row exclusion from cold-lane denominators |
| `automation/_tests/test_pipeline_state.py` | +~60 | Two new banner states + 7-day SUPPRESS-EXPIRED window + post-suppression headline counts |
| `.gitignore` | +~5 | Add `data/suppressions.json`, `data/suppressions_events.jsonl`, `data/suppressions_pending_archives.jsonl`, `data/suppressions_history.json`. Reasons can be candid; never sync across machines |

v3 total: ~600 line delta. v3.1.1 (post-review) adds ~1,200 on top. CLI changes: `--only-urls FILE` on `auto_promote.py`. Disk schema changes:
- `data/suppressions.json` (new, gitignored, lazy-created from `.example.json`)
- `data/suppressions_events.jsonl` (new, append-only event log; source of truth)
- `data/suppressions_history.json` (new, expired entries archive)
- `data/suppressions_pending_archives.jsonl` (new, partial-failure recovery queue)
- `data/job_tracker_data.json`: `archived: bool` field added; `meta.schema_version` bumps to 3 with migration on first read
All forward-compatible: older readers still parse, but won't honor `archived` until updated. Migration is idempotent — safe to run multiple times.

## Out of scope

- Dashboard redesign — keep Quick Actions identical for now. Pipeline ships first; if it works, Dashboard either becomes a thin pipeline mirror or stays as the human-work entry point.
- Sidebar restructuring — the global one stays as-is.
- Scan History — its own page, linked from "▸ Recent runs" expander at the bottom of Pipeline.
- Score-this-URL becomes a persistent expander INSIDE the Scoring card (not a stage). Side-channel, not pipeline.

## Banner copy reference

```
SAFETY     🔴 Most rows quarantined (200 of 205) — investigate before scoring
ACTIVE     🟡 Scoring · 412/728 done · started 4m ago [Stop]
RECENT     🔴 Last Refresh scrape failed [View error]
              ▶ Score 60 jobs anyway ($0.72, ~4 min)            ← green secondary
PROMOTE    ▶ Promote 12 scored rows (5s, free)            [Preview] [Apply]
              ↳ also: 1,206 unscored ($0.48, ~5min)
REVIEW     ▶ Review 38 verdicts · ✅ no auto-promote candidates  [Open Scored]
SCORE      ▶ Score 1,206 jobs (227 free + 979 billable, ~$0.42, ~5–18 min)
              🔑 if api_key_invalid AND scoring is the only pending action
REFRESH    ▶ Refresh inputs — last scrape 36h ago, last gmail 28h ago
EMPTY      ⏸ Empty pipeline — connect Gmail (sidebar) and run a scrape
DEFAULT    ✅ Up to date · next nightly refresh in 4h 12m
SUCCESS    ✅ Promoted 12 to tracker — Open Tracker          ← overlay, ~10 min
```

## Open questions for Saber

1. **Tracker pill state** — show `⏵ awaiting review` when Found > 0, OR keep `🟢 always` and rely on the deep-link button count? I lean ⏵ — it makes the page tell you when there's new agent output to look at.
2. **Recent runs** — separate Scan History page (already exists), or thin expander at bottom of Pipeline that deep-links into Scan History? I lean expander.
3. **Bundle the Review Queue race fix in this commit** (since the redesigned Auto-promote card visibly invites the race), or split into a follow-up? I lean bundle.
4. **TRIAGE rescue UX** — checkbox-select rows in the drops table to send them through scoring on next run, OR per-row "rescue" button? I lean checkbox + bulk.
