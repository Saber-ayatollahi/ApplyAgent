# v3.1.1 implementation plan

Phased build-out of the v3.1.1 redesign in `pipeline_redesign.md`. Goal: every commit lands a self-contained, testable slice; no half-states between phases. Each phase ends with the app fully runnable — slice can be reverted independently.

## Phase ordering — why this shape

The dependency graph fans out from two foundational pure-data modules (`sectors.py`, `brand_aliases.py` already exists) into three concurrency-safe layers (`tracker_ops`, `suppressions`, `tracker_migrate`), then into automation wiring (`fit_scorer`, `auto_promote`, `pipeline`), then into UI (`pipeline_state`, `ui/app.py` cards). Tests at `automation/_tests/` get added phase-by-phase — never a separate "test phase."

Phase boundary rule: no phase ships unless every existing test still passes AND the app runs end-to-end with the new slice in a default-off / no-op state. Default-on flips happen incrementally, not all at once.

## Phase 1 — foundation (pure data + concurrency primitives)

**Parallelizable.** Three disjoint file sets; no inter-track dependencies.

### Track 1A — `automation/sectors.py` ★ I write this myself

Single source of truth for sector names + canonical-key map. Replaces the duplicated `SECTOR_ROUGH_TIER` const in `auto_promote.py:77`.

API:
```python
KNOWN: list[str]                    # canonical sector display names (sorted)
TIER_OF: dict[str, int]             # display name → 1..4
def is_known(name: str) -> bool
def canonical(name: str) -> str | None  # input → KNOWN entry, None if unknown
```

DOD:
- All 18 sector names from `auto_promote.SECTOR_ROUGH_TIER` migrated.
- `auto_promote.py` imports `from sectors import TIER_OF` (defer the actual edit to Phase 2 to avoid blocking parallelism).
- Smoke test: `python -m automation.sectors --smoke` prints the registry.

Why I write this: it's 40 lines, foundational, and unblocks Tracks 1B+1C running in parallel.

### Track 1B — tracker layer

**Files:**
- `automation/tracker_ops.py` (new, ~120 lines)
- `automation/tracker_migrate.py` (new, ~50 lines)
- `automation/_tests/test_tracker_ops.py` (new)

Pure functions over the tracker dict; no I/O. `safe_json.py` stays a generic concurrency primitive — no domain logic added there.

API:
```python
# tracker_ops.py
TERMINAL_STATUSES: frozenset[str]    # {"Rejected","Withdrawn","Offer","Hired","Expired"}
def is_active(job: dict) -> bool       # not archived AND status not in TERMINAL
def archive(t: dict, job_id: str) -> dict          # sets archived=True, archived_at, archive_reason
def restore(t: dict, job_id: str) -> dict          # clears archived
def set_status(t: dict, job_id: str, status: str) -> dict
def set_archive_reason(t: dict, job_id: str, reason: str) -> dict
def apply_followup_gate(job: dict) -> bool  # widens _NO_FOLLOWUP_STATUSES with archived

# tracker_migrate.py
SCHEMA_VERSION = 3
def migrate_in_place(t: dict) -> dict   # idempotent; bumps meta.schema_version to 3
                                        # stamps archived=False on every row when < 3
def needs_migration(t: dict) -> bool    # cheap pre-check
```

Wiring: NOT in Phase 1. The migration runs at first-read sites in Phase 2/3. In Phase 1 it sits as a pure module with tests.

DOD:
- `pytest automation/_tests/test_tracker_ops.py` passes (≥10 cases: archive, restore, set_status, is_active matrix, followup gate, migration idempotency).
- Migration is idempotent (running twice = same result; covered by test).
- Existing tracker (64 rows) loaded into a fixture and migrated cleanly without losing fields.

### Track 1C — suppressions layer

**Files:**
- `automation/suppressions.py` (new, ~180 lines)
- `data/suppressions.example.json` (seed)
- `automation/_tests/test_suppressions.py` (new)
- `.gitignore` (+~5 lines for live files)

Depends on: `brand_aliases.canonical_brand` (exists) + `sectors` (Track 1A — start with `sectors.KNOWN` import, will resolve once Track 1A merges).

API:
```python
# suppressions.py
def load_active(now: date | None = None) -> dict   # {sectors: [...], companies: [...]}
def load_recently_expired(window_days: int = 7, now=None) -> list[dict]
def load_all() -> dict                              # active + expired, for admin views
def add_sector(name: str, until: date | None, reason: str) -> None
def add_company(name: str, until: date | None, reason: str) -> None
def lift(scope: str, name: str) -> None
def extend(scope: str, name: str, days: int) -> None
def edit_reason(scope: str, name: str, new_reason: str) -> None

def is_suppressed(row: dict, snapshot: dict | None = None) -> tuple[bool, str | None]
    # returns (suppressed, drop_reason); reason like "suppressed_sector_60d" / "suppressed_company_60d"

def snapshot_to(path: Path) -> Path     # writes runs/<id>/suppressions_snapshot.json
def coverage(scope: str, name: str, rows: list[dict]) -> dict
    # {matched: int, total: int, unsectored: int}
```

Wire-format:
- `data/suppressions.json` (live, gitignored) — `{version: 1, sectors: [...], companies: [...]}`
- `data/suppressions_events.jsonl` (gitignored, append-only event log; source of truth)
- `data/suppressions_history.json` (gitignored, expired entries archive)
- `data/suppressions_pending_archives.jsonl` (gitignored, partial-failure recovery queue)

Each entry: `{name, canonical_key, scope, until: ISO|null, reason, added_at, version: 1}`.

Concurrency: every mutation goes through `safe_json.mutate_json` on `suppressions.json` AND appends one line to the events log inside the same lock window.

DOD:
- `pytest automation/_tests/test_suppressions.py` passes (≥15 cases): canonical-key matching (RBC ⇄ Royal Bank of Canada ⇄ RBC Capital Markets via `brand_aliases.canonical_brand`); sector registry validation (rejects unknown sector names); unsectored-row pass-through; lazy TTL expiry → history archive; `load_recently_expired` 7d window; `is_suppressed` ordering precedence; coverage stats; lock contention with a simulated promote write; events-log append on every mutation; rebuild active state from events log alone.
- `data/suppressions.example.json` ships with `{"version": 1, "sectors": [], "companies": []}`.
- `.gitignore` lines: `data/suppressions.json`, `data/suppressions_events.jsonl`, `data/suppressions_history.json`, `data/suppressions_pending_archives.jsonl`.
- No production code yet imports this module — it sits dormant until Phase 2.

## Phase 2 — automation wiring (after Phase 1 lands)

**Mostly sequential.** Each track touches a single existing entrypoint; ordering matters because `auto_promote` depends on triage emitting suppression drop reasons.

### Track 2A — `fit_scorer.py` triage integration

- Triage ordering: `negative_term → suppression → keyword/level`.
- Suppression check uses snapshot path passed via env var `APPLYAGENT_SUPPRESSIONS_SNAPSHOT` (falls back to live file if unset).
- Drop reasons: `suppressed_sector_60d`, `suppressed_company_30d`, etc.
- `--only-url` overrides suppression with `override_reason: manual_only_url` written to `rule_reasons`.
- Test additions to `test_scorer_*.py` covering ordering and override.

### Track 2B — `auto_promote.py` --only-urls + selection_mode

- Remove duplicated `SECTOR_ROUGH_TIER` const → `from sectors import TIER_OF`.
- Add `--only-urls FILE` mode: read newline-delimited URLs, restrict promotion candidates to that set. Manually-selected `verdict=skip` rows promote as `Watch / tier 4` with `manual_override_skip_verdict: true`.
- Per-row `selection_mode ∈ {threshold, manual, manual_below_threshold, manual_override_skip}`.
- Re-check `suppressions.is_suppressed` at promote time → new `suppressed_after_score` bucket in promote report.
- Replace naked tracker writes with `tracker_ops` calls via `safe_json.mutate_json`.
- Test additions covering: `--only-urls` happy path, skip-verdict override, suppressed-after-score race window.

### Track 2C — `pipeline.py` snapshot

- At pipeline-run start, snapshot `suppressions.json` to `runs/<run_id>/suppressions_snapshot.json`.
- Pass snapshot path via env to all subprocesses (scorer, promote).
- Snapshot path embedded in `pipeline_*.json` status file for audit reproducibility.

## Phase 3 — UI integration (after Phase 2 lands)

**Sequential by card.** All edits to `ui/app.py` so file-level conflicts force ordering.

### Track 3A — `ui/pipeline_state.py` updates

- Headline counts derive from current `worklist_scored.json` post-suppression (NOT `last_run_state.added`).
- New banner states: `SUPPRESS-AWARE-EMPTY`, `SUPPRESS-EXPIRED` (7-day window).
- Coverage stats include unsectored-row count.
- Test additions: 2 banner state cases + 7-day SUPPRESS-EXPIRED window + post-suppression headline.

### Track 3B — Scoring card selection (Cluster A)

- `st.session_state["scoring_selected_urls"]: set[str]` keyed on URL — survives filter/rerun.
- Checkbox column derived from set membership each render; `st.data_editor` callback diffs back into the set.
- `[Send N selected]` shells `auto_promote.py --only-urls <tempfile>`.
- Pre-flight `st.caption` below button: below-threshold + suppressed + geo-skip counts.
- Drop the N≥25 confirm modal.

### Track 3C — Triage card suppression admin

- `Active suppressions` rendered as one bordered container per entry; `st.columns([3, 1, 1, 1])`.
- Coverage column shows unsectored fall-through.
- `[+ Add suppression]` form sector picker = dropdown of `sectors.KNOWN`.
- `[Lift]` / `[+30d Extend]` / click-to-edit-reason actions wire to suppressions API.

### Track 3D — Tracker / Review Queue / Kanban (Cluster C+D)

- Per-row `🚫 Archive` button on Review Queue + Kanban.
- `[⋯ More options ▾]` `st.popover` row beneath action row — mute-sector / mute-company only (archive removed from this menu — it's already on the action row).
- Mute confirm uses inline `_rq_mute_open` pattern (mirrors `_rq_apply_open` at `ui/app.py:8325`); NO `st.dialog`.
- Mute confirm executes: write suppression first (events log + active file inside one lock); attempt archive second; on archive failure append to `suppressions_pending_archives.jsonl` + yellow toast.
- Mute success toast carries `[Undo]` action calling `suppressions.lift()`.
- Tracker `▾ Archived (N)` expander; context-aware `[Restore]` confirm modal when archived row's reason references active suppression.
- Tracker `▾ Active suppressions (N)` mirror expander (read-only of same source as Triage card).
- Replace naked `_rq_apply_action` write with `mutate_json(TRACKER, lambda t: tracker_ops.set_status(t, job_id, new_status))`.
- Migration trigger: on first read of `data/job_tracker_data.json` from any UI entrypoint, run `tracker_migrate.migrate_in_place` if `needs_migration`. Backed up via existing `.bak.YYYY-MM-DD.json` pattern before write.
- Read-site audit: route every `j.get("status") in ...` filter through `tracker_ops.is_active(j)` at the seven sites named in `pipeline_redesign.md` § Cluster C.

## Phase 4 — audit pack + integration

- `audit_pack.py`: `triage_to_xlsx` adds `Suppressed` sub-sheet AND `suppressed_by` column on main Triage sheet; `promote_to_xlsx` adds `selection_mode` column.
- Integration test: full pipeline run with one sector mute + one manual selection; verify all artifacts (worklist_scored.json, promote_report, audit pack xlsx, snapshot json) carry consistent state.

## Definition of done (whole feature)

1. `pytest automation/_tests/` — all green, including new test files.
2. App starts, all pages render, Pipeline page shows the new banner states correctly across the priority ladder.
3. Manual end-to-end:
   - Run scrape + score → see scored rows on Pipeline.
   - Manually select 3, click Send → tracker gains 3 rows; `selection_mode: manual` in promote report.
   - Mute "Big 6 Banks" 60d from Review Queue → confirm archive; suppressions.json + events log updated.
   - Re-run scoring → bank rows hit `suppressed_sector_60d` drop reason in audit pack.
   - Lift sector mute → bank rows re-eligible at next pipeline run.
   - Archive a tracker row → row hidden from Review Queue + Kanban + Today's brief; preserved in Archived expander; URL still blocks re-promotion.
4. No row writes bypass `safe_json.mutate_json`. Verified by grep: no naked `json.dump.*tracker` or `TRACKER.write_text` outside `safe_json.py` itself.
5. `git diff --stat` matches the implementation-scope table in `pipeline_redesign.md` within ~10%.

## Risk register

| Risk | Mitigation |
|---|---|
| Migration corrupts existing tracker | Idempotent + backup before write + dry-run flag for first 24h |
| Lock timeout under heavy AV / OneDrive load | `LOCK_TIMEOUT_SEC = 10s` already in place; mute+archive partial-failure path catches it |
| Selection state grows unbounded across sessions | `set` keyed on URL is bounded by worklist size; cleared on `[Clear]` button or page-leave |
| Suppression registry drift if sector renamed | Phase 1C tests + `SUPPRESS-INVALID` banner already specified |
| Streamlit `st.popover` API churn | Stable since 1.32; if it breaks, fall back to `st.expander` (uglier, same semantics) |
| Phase boundary leaves UI broken between phases | Default-off / dormant module pattern in Phase 1; flips happen at Phase 2/3 entry points only |

## Out of scope (deferred to v4)

Per `pipeline_redesign.md` § "What's punted to v4":
- Outcome-feedback unification with manual mutes.
- Promote-on-suppression-lift retroactive semantics.
- Granularity beyond sector + company.
- Hard delete on tracker.

Plus from this plan:
- Test infrastructure migration (`ui/_tests/` → `automation/_tests/`) — accepted as is; test files for new modules go in `automation/_tests/`.
- Streamlit version pin verification (`st.popover` requires ≥1.32, `st.dialog` ≥1.36) — if local env is older, surface an explicit error; do not silently degrade.
