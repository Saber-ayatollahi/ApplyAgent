"""Saber's Job Search — Streamlit Dashboard.

Run:
    streamlit run ui/app.py

Agentic pipeline:  Scrape -> Score -> Triage -> Promote -> Tailor
One page, one flow. Background execution via ui/scan_runner.py.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    _HAVE_AUTOREFRESH = True
except ImportError:
    _HAVE_AUTOREFRESH = False

    def st_autorefresh(interval: int = 2000, limit: int = 0, key: str = ""):
        """No-op shim when streamlit-autorefresh isn't installed."""
        return 0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_runner  # noqa: E402
import api_key  # noqa: E402
import gmail_ui  # noqa: E402
import pipeline_state  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))
import cost_ledger  # noqa: E402

try:
    import error_log  # noqa: E402
except Exception:
    error_log = None  # type: ignore

api_key.hydrate_env()

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"
CRM = ROOT / "data" / "recruiter_crm.json"
OUT_DIR = ROOT / "automation" / "outputs"
RUNS_DIR = OUT_DIR / "runs"
PIPELINE_DIR = OUT_DIR / "pipelines"


# ── UI palette ──────────────────────────────────────────────────────────
# Centralized color tokens. Two semantic axes are intentionally separate:
#
#   URGENCY (job listing)   — Low=green ("not on fire"). This is the
#                              listing's heat: how time-sensitive is it.
#   PRIORITY (recruiter CRM) — Low=gray  ("not in focus right now"). This
#                              is *our* attention budget for the contact.
#
# Don't unify these — they encode different things, and merging them
# would reverse the meaning of "Low" on either CRM or Analytics. Tier
# (1-4) and verdict palettes are also kept here so cross-page rendering
# stays consistent if the design ever needs a global retheming pass.
_C_RED, _C_AMBER, _C_GREEN = "#ef4444", "#f59e0b", "#10b981"
_C_BLUE, _C_INDIGO, _C_GRAY, _C_SLATE = "#3b82f6", "#6366f1", "#6b7280", "#94a3b8"

URGENCY_COLORS = {
    "High":    _C_RED,
    "Medium":  _C_AMBER,
    "Low":     _C_GREEN,
    "Unknown": _C_SLATE,
}
PRIORITY_COLORS = {
    "High":    _C_RED,
    "Medium":  _C_AMBER,
    "Low":     _C_GRAY,
}
TIER_COLORS = {1: _C_GREEN, 2: _C_BLUE, 3: _C_AMBER, 4: _C_GRAY}
VERDICT_COLORS = {
    "apply_now":         _C_GREEN,
    "tailor_and_apply":  _C_AMBER,
    "watch":             _C_INDIGO,
}
CRM_STATUS_COLORS = {
    "Not_Contacted":  _C_GRAY,
    "Outreach_Sent":  _C_BLUE,
    "Active":         _C_GREEN,
    "Paused":         _C_AMBER,
    "Closed":         _C_RED,
}

# Lane economics. Mirrors fit_scorer.RESUME_VARIANTS. As of the 2026-05 strategy
# rebalance, VEN (Vendor-Platform) and QUANT (Investment & Market Risk) are
# PRIMARY lanes co-equal with ALM/VAL — they must get a boost and a badge, not
# fall through to 1.0 / "Other". Keep this dict and LANE_LABELS as the single
# source of truth so the scorer taxonomy and the UI cannot diverge again.
LANE_MULTIPLIERS = {"ALM": 1.5, "VAL": 1.2, "VEN": 1.3, "QUANT": 1.3}

# Short label per lane for the activity strip and badges. Unmapped -> "Other".
LANE_LABELS = {"ALM": "ALM", "VAL": "Validation", "VEN": "Vendor", "QUANT": "Quant"}

# Badge accent colour per lane (Review Queue tag row).
LANE_COLORS = {"ALM": _C_INDIGO, "VAL": _C_BLUE, "VEN": _C_AMBER, "QUANT": _C_GREEN}


def lane_mult(job: dict) -> float:
    pv = (job.get("primary_variant") or "").upper()
    return LANE_MULTIPLIERS.get(pv, 1.0)


def extract_bridge(job: dict, max_len: int = 130) -> str:
    """Extract a one-line 'your X → their Y' bridge from fit_notes.

    Uses the first item from the '| Top reasons:' section which the scorer
    writes for every scored job. Falls back to the first sentence of the
    verdict if the delimiter is missing.
    """
    fn = job.get("fit_notes") or ""
    if not fn:
        return ""
    if "| Top reasons:" in fn:
        reasons = fn.split("| Top reasons:", 1)[1].strip()
        first = reasons.split(";")[0].strip()
    else:
        first = fn.split(".")[0].strip()
    if not first:
        return ""
    if len(first) > max_len:
        first = first[:max_len].rsplit(" ", 1)[0] + "..."
    return first


@st.cache_data(ttl=600)
def _target_counts() -> dict:
    """Live company counts for the scrape buttons, read from the actual
    target lists so the UI labels can never drift from reality (the old
    hardcoded "77 core targets" string was stale — the list is 66).

    Returns {"core": int, "expansion": int, "full": int}. On any import
    failure (e.g. requests/bs4 missing in a thin env) falls back to the
    last-known counts rather than crashing the page."""
    try:
        sys.path.insert(0, str(ROOT / "automation"))
        from jd_scraper import TARGETS  # noqa: E402
        from expansion_companies import EXPANSION_TARGETS  # noqa: E402
        core = len(TARGETS)
        expansion = len(EXPANSION_TARGETS)
        # Union by name — core and expansion are disjoint today, but guard
        # against future overlap so "full" never overstates coverage.
        names = {t["name"] for t in TARGETS} | {t["name"] for t in EXPANSION_TARGETS}
        return {"core": core, "expansion": expansion, "full": len(names)}
    except Exception:
        return {"core": 66, "expansion": 93, "full": 159}


@st.cache_data(ttl=15)
def load_tracker():
    """Read tracker, auto-migrating schema on first read after a clone or
    upgrade. Phase-3D contract: every UI code path that reads the tracker
    flows through this, so the `archived` field is guaranteed to exist on
    every row by the time it's queried by tracker_ops.is_active().

    The migration is idempotent — running it on an already-migrated file
    is a no-op (tracker_migrate.needs_migration returns False)."""
    if not TRACKER.exists():
        return {"jobs": [], "meta": {}}
    raw = json.loads(TRACKER.read_text(encoding="utf-8"))
    try:
        from automation import tracker_migrate as _tm  # noqa: WPS433
    except Exception:
        return raw
    if not _tm.needs_migration(raw):
        return raw
    # Migration WILL mutate. Persist via the same lock-protected path the
    # rest of the UI uses, with a `.bak.` snapshot before write so the
    # original is recoverable if anything goes wrong downstream.
    try:
        from safe_json import mutate_json as _mj  # noqa: WPS433
    except Exception:
        # Fallback: in-memory migrate only. Caller still sees the migrated
        # dict; the disk file gets persisted on the next write.
        return _tm.migrate_in_place(raw)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TRACKER.with_suffix(f".bak.{stamp}.json")
    try:
        bak.write_text(TRACKER.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass
    migrated = _mj(TRACKER, _tm.migrate_in_place,
                    default={"jobs": [], "meta": {}})
    return migrated


@st.cache_data(ttl=15)
def load_crm():
    if CRM.exists():
        return json.loads(CRM.read_text(encoding="utf-8"))
    return {}


def _web_scan_age_hours() -> float | None:
    """Age of the most recent web scan in hours, or None if no scan exists."""
    files = sorted(
        [f for f in OUT_DIR.glob("scan_*.json")
         if "_scored" not in f.name
         and "scan_gmail_" not in f.name
         and "scan_checkpoint" not in f.name],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not files:
        return None
    return (datetime.now().timestamp() - files[0].stat().st_mtime) / 3600


def _file_age_hours(path: Path) -> float | None:
    """Age of a file in hours, or None if it doesn't exist."""
    if not path.exists():
        return None
    return (datetime.now().timestamp() - path.stat().st_mtime) / 3600


def _latest_glob_age_hours(pattern: str, base: Path = None) -> float | None:
    """Age (hours) of the most recent file matching glob `pattern` under `base`
    (defaults to OUT_DIR). None if no match."""
    base = base or OUT_DIR
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return (datetime.now().timestamp() - files[0].stat().st_mtime) / 3600


def _today_brief_exists() -> bool:
    """True if a brief_<today>.json already exists for today."""
    return (OUT_DIR / f"brief_{datetime.now().strftime('%Y%m%d')}.json").exists()


def _latest_artifact(pattern: str, exclude: tuple[str, ...] = ()) -> Path | None:
    """Most-recent file matching glob `pattern` (with optional substring excludes)."""
    files = [p for p in OUT_DIR.glob(pattern)
             if not any(ex in p.name for ex in exclude)]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _humanize_age_h(age_h: float | None) -> str:
    if age_h is None:
        return "?"
    if age_h < 1:
        return f"{int(age_h * 60)}m ago"
    if age_h < 48:
        return f"{age_h:.0f}h ago"
    return f"{age_h / 24:.0f}d ago"


def _content_age_h(json_path: Path) -> float | None:
    """Read the canonical 'when was this run produced' timestamp from inside
    the artifact. Falls back to file mtime for legacy artifacts.

    Different artifacts use different fields:
      - scan_*.json:           scan_timestamp / scan_date
      - scan_gmail_*.json:     scan_timestamp
      - worklist.json:         rebuilt_at
      - worklist_scored.json:  scored_at
      - promote_report.json:   scan_date

    The file mtime can lag REAL run time when:
      - a repair script rewrites the file (mtime jumps forward, content stale)
      - a sync tool touches the file (mtime jumps but content unchanged)
    """
    try:
        import json as _json
        d = _json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return _file_age_hours(json_path)
    for key in ("scored_at", "rebuilt_at", "scan_timestamp"):
        v = d.get(key)
        if v:
            try:
                # Strip trailing Z and parse — ISO-8601 with optional Z suffix
                ts = datetime.fromisoformat(v.replace("Z", "+00:00")
                                              if v.endswith("Z") else v)
                # If the ts has no tz, treat it as local
                if ts.tzinfo is None:
                    age = (datetime.now() - ts).total_seconds() / 3600
                else:
                    from datetime import timezone as _tz
                    age = (datetime.now(_tz.utc) - ts).total_seconds() / 3600
                return max(age, 0.0)
            except Exception:
                continue
    # scan_date is YYYYMMDD — coarse but useful
    sd = d.get("scan_date")
    if sd and isinstance(sd, str) and len(sd) == 8:
        try:
            ts = datetime.strptime(sd, "%Y%m%d")
            return (datetime.now() - ts).total_seconds() / 3600
        except Exception:
            pass
    return _file_age_hours(json_path)


@st.cache_data(show_spinner=False, max_entries=64)
def _build_xlsx_cached(builder_name: str, path_str: str,
                       mtime: float, size: int) -> bytes:
    """Build an artifact's xlsx once per (file, mtime, size) and memoize.

    Keyed on builder_name + path + mtime + size — all primitives — so a
    rerun that hasn't touched the file returns instantly, but a freshly
    written artifact (new mtime/size) rebuilds. The builder is resolved by
    name from audit_pack (not passed as a function object) to keep the
    cache key hashable and stable across reruns.

    Builders are 20–470 ms each; memoizing makes the eager build below a
    one-time, per-session cost instead of a per-render one. This is what
    lets the 📊 xlsx button be a SINGLE-click direct download (Streamlit's
    download_button materialises `data` at render, so the bytes must exist
    before the click — the old two-click build→reveal dance is what read
    as "downloads not working").
    """
    import sys as _sys
    import importlib as _il
    _ad = str(ROOT / "automation")
    if _ad not in _sys.path:
        _sys.path.insert(0, _ad)
    # Reload guard (cache-miss only): a Streamlit-held audit_pack imported
    # before a builder shipped would lack it; reload picks it up without a
    # server restart. Cheap because it runs at most once per (file, mtime).
    if "audit_pack" in _sys.modules:
        _il.reload(_sys.modules["audit_pack"])
    import audit_pack as _ap
    builder = getattr(_ap, builder_name)
    return builder(Path(path_str))


def render_artifact_download(label: str, json_path: Path | None,
                              xlsx_builder, key_prefix: str,
                              container=None) -> None:
    """Render a 3-column row: filename caption + JSON download + xlsx download.

    `xlsx_builder` is a callable taking the json path and returning xlsx bytes
    (one of the per-artifact builders in audit_pack.py). The xlsx is built
    eagerly and memoized via `_build_xlsx_cached` (keyed on file mtime), so
    the 📊 button is a single-click direct download rather than the previous
    build→reveal two-step.
    """
    target = container or st
    if json_path is None or not json_path.exists():
        target.caption(f"⏸ {label} — no artifact yet")
        return
    # Two ages: when the run actually produced the data (canonical) vs.
    # when the file was last touched (mtime). Repair-script writes bump
    # mtime without changing the underlying run timestamp, so showing
    # both prevents the "scored 2h ago" lie when the real scoring run
    # was a week ago.
    content_age = _content_age_h(json_path)
    file_age = _file_age_hours(json_path)
    age_label = _humanize_age_h(content_age)
    repaired_tag = ""
    if (content_age is not None and file_age is not None
            and content_age - file_age > 0.5):  # mtime newer by >30 min
        repaired_tag = f" · file touched {_humanize_age_h(file_age)}"
    size_kb = json_path.stat().st_size / 1024

    c1, c2, c3 = target.columns([3, 1, 1])
    c1.markdown(
        f"**{label}** · `{json_path.name}` · {age_label}{repaired_tag} "
        f"· {size_kb:,.0f} KB"
    )
    # JSON: eagerly read bytes — cheap (KB range, occasional MB on worklist).
    # The previous lazy-callable form (data=json_path.read_bytes) only works
    # on Streamlit ≥1.34; older versions raise "Invalid binary data format".
    try:
        c2.download_button(
            "📄 JSON",
            data=json_path.read_bytes(),
            file_name=json_path.name, mime="application/json",
            key=f"dl_json_{key_prefix}", width='stretch',
        )
    except Exception as e:
        c2.caption(f"JSON err: {e}")
    # xlsx: single-click direct download. The bytes are built eagerly and
    # memoized by _build_xlsx_cached (keyed on file mtime), so the button
    # below carries real data the instant it renders — one click downloads.
    # Resolve the builder's NAME so the cache key stays hashable; fall back
    # to __name__ when a bare function is passed.
    _builder_name = getattr(xlsx_builder, "__name__", None)
    try:
        _stat = json_path.stat()
        _xlsx_bytes = _build_xlsx_cached(
            _builder_name, str(json_path), _stat.st_mtime, _stat.st_size,
        )
        c3.download_button(
            "📊 xlsx",
            data=_xlsx_bytes,
            file_name=f"{json_path.stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_xlsx_{key_prefix}", width='stretch',
            help="Excel workbook with input/filter/output sheets. "
                 "Built on first render, cached after.",
        )
    except Exception as e:
        c3.caption(f"xlsx err: {e}")


def _render_suppressions_admin() -> None:
    """Phase 3C — Triage card suppression admin.

    Renders an expander with:
      - One bordered container per active mute, columns([3,1,1,1]):
        name+scope (3) / [🔓 Lift] / [+30d Extend] / click-to-edit-reason.
      - [+ Add suppression] form with sector dropdown (sectors.KNOWN) +
        company freetext + 30/60/90/permanent picker + reason field.

    Writes happen synchronously via the suppressions module — same lock
    the CLI uses, milliseconds. UI doesn't shell subprocesses for these.
    Reads are tolerant of a missing/corrupt registry (lazy-creates from
    the example seed)."""
    try:
        from automation import suppressions as supp  # noqa: WPS433
        from automation import sectors as _sectors  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Suppressions module unavailable: {exc}", icon="⚠️")
        return

    try:
        active = supp.load_active()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not read suppressions: {exc}", icon="⚠️")
        return

    sec_list = active.get("sectors") or []
    co_list = active.get("companies") or []
    n_active = len(sec_list) + len(co_list)

    # Lazy: load drop-counts per entry from the latest scored file once,
    # so coverage rendering doesn't re-read 1,400 rows on each radio click.
    @st.cache_data(ttl=60, show_spinner=False)
    def _coverage_map(scored_path_str: str | None,
                       mtime_key: float,
                       entries_key: tuple) -> dict:
        """Build {canonical_key: coverage_dict} for the given scored file.

        Cache key is (path, mtime, entries) — recomputed when any of those
        change. entries_key is a tuple of (scope, canonical_key) so adding
        / lifting an entry busts the cache cleanly."""
        if not scored_path_str:
            return {}
        try:
            data = json.loads(
                Path(scored_path_str).read_text(encoding="utf-8")
            )
        except Exception:
            return {}
        rows = data.get("results") or []
        out: dict = {}
        for entry in sec_list + co_list:
            key = entry.get("canonical_key", "")
            if not key:
                continue
            try:
                out[key] = pipeline_state.coverage_for_entry(entry, rows)
            except Exception:
                out[key] = {"matched": 0, "total": 0, "unsectored": 0}
        return out

    scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    scored_path = scored_files[0] if scored_files else None
    cov_map = _coverage_map(
        str(scored_path) if scored_path else None,
        scored_path.stat().st_mtime if scored_path else 0.0,
        tuple((e.get("scope", "?"), e.get("canonical_key", ""))
              for e in sec_list + co_list),
    )

    # Surface SUPPRESS-INVALID inline so the user sees it on the same card
    # they edit, not just in the global banner.
    invalid_names = pipeline_state._suppression_invalid_names(active)
    if invalid_names:
        st.warning(
            "These sector mutes reference unknown sectors (likely renamed): "
            + ", ".join(invalid_names) + ". Lift or rename them.",
            icon="⚠️",
        )

    expander_label = (
        f"🔇 Active suppressions ({n_active})"
        if n_active else "🔇 Active suppressions"
    )
    with st.expander(expander_label, expanded=False):
        if n_active == 0:
            st.caption(
                "No active mutes. Use the form below to skip a sector or "
                "company at scoring + promote time."
            )
        else:
            from datetime import date as _date  # noqa: WPS433
            today = _date.today()
            for entry in sec_list + co_list:
                _render_suppression_entry(entry, today, cov_map, supp)

        st.markdown("---")
        _render_add_suppression_form(_sectors)


def _render_suppression_entry(entry: dict,
                                today,
                                cov_map: dict,
                                supp_module) -> None:
    """One bordered container per entry. Columns: name+scope / Lift / Extend /
    edit-reason. Inline-confirm pattern for edit (mirrors _rq_apply_open)."""
    canonical_key = entry.get("canonical_key", "")
    scope = entry.get("scope", "?")
    name = entry.get("name", "?")
    reason = entry.get("reason", "")
    until_iso = entry.get("until")
    cov = cov_map.get(canonical_key, {})
    edit_state_key = f"_supp_edit_{canonical_key}"

    with st.container(border=True):
        col_name, col_lift, col_extend, col_reason = st.columns([3, 1, 1, 2])

        with col_name:
            scope_chip = "🏭 sector" if scope == "sector" else "🏢 company"
            st.markdown(f"**{name}** &nbsp; {scope_chip}")
            sub_bits = [pipeline_state.format_until_label(until_iso, today)]
            if cov:
                m, t, u = cov.get("matched", 0), cov.get("total", 0), \
                          cov.get("unsectored", 0)
                if t:
                    sub_bits.append(f"{m} of {t} rows match")
                if u:
                    sub_bits.append(f"{u} unsectored — pass through")
            st.caption(" · ".join(sub_bits))

        with col_lift:
            if st.button("🔓 Lift", key=f"_supp_lift_{canonical_key}",
                          help="Remove this mute. Audit trail preserved."):
                try:
                    supp_module.lift(scope, name)
                    st.toast(f"Lifted {scope} mute on {name!r}", icon="🔓")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Lift failed: {exc}")
                st.rerun()

        with col_extend:
            if st.button("+30d", key=f"_supp_ext_{canonical_key}",
                          help="Extend this mute by 30 days from its current "
                               "expiry."):
                try:
                    supp_module.extend(scope, name, 30)
                    st.toast(f"Extended {scope} mute by 30d", icon="📅")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Extend failed: {exc}")
                st.rerun()

        with col_reason:
            editing = st.session_state.get(edit_state_key, False)
            if not editing:
                # Click-to-edit pattern. Rendering reason text as a button
                # keeps the affordance discoverable without a separate icon.
                btn_label = (reason[:40] + "…") if len(reason) > 40 else \
                            (reason or "_(no reason)_")
                if st.button(btn_label,
                              key=f"_supp_reason_btn_{canonical_key}",
                              help="Click to edit this reason. Old value "
                                   "preserved in events log."):
                    st.session_state[edit_state_key] = True
                    st.rerun()
            else:
                new_reason = st.text_input(
                    "reason", value=reason,
                    key=f"_supp_reason_in_{canonical_key}",
                    label_visibility="collapsed",
                )
                save_col, cancel_col = st.columns(2)
                if save_col.button("Save",
                                    key=f"_supp_reason_save_{canonical_key}",
                                    type="primary"):
                    try:
                        supp_module.edit_reason(scope, name, new_reason)
                        st.toast("Reason updated", icon="✏️")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Save failed: {exc}")
                    st.session_state[edit_state_key] = False
                    st.rerun()
                if cancel_col.button("Cancel",
                                       key=f"_supp_reason_cancel_{canonical_key}"):
                    st.session_state[edit_state_key] = False
                    st.rerun()


def _render_add_suppression_form(sectors_module) -> None:
    """[+ Add suppression] form. Calls validate_suppression_form for the
    error path so a malformed input never reaches the lock-protected write."""
    with st.form("add_suppression_form", clear_on_submit=False):
        c_scope, c_name, c_dur = st.columns([1, 2, 1])
        with c_scope:
            scope = st.radio(
                "Scope", ("sector", "company"),
                horizontal=True, key="_supp_form_scope",
            )
        with c_name:
            if scope == "sector":
                name = st.selectbox(
                    "Sector", options=[""] + list(sectors_module.KNOWN),
                    key="_supp_form_sector_name",
                )
            else:
                name = st.text_input(
                    "Company", key="_supp_form_company_name",
                    placeholder="RBC, KOHO, …",
                    help="Free text — canonicalized via brand_aliases. "
                         "RBC ⇄ Royal Bank of Canada match the same key. "
                         "This is a TTL'd triage mute (still scraped). For a "
                         "PERMANENT source-level block that stops fetching "
                         "entirely, use 🚫 Excluded companies on the ① Inputs "
                         "card.",
                )
        with c_dur:
            ttl_choice = st.selectbox(
                "Duration", ("30d", "60d", "90d", "permanent"),
                index=1, key="_supp_form_ttl",
            )
        reason = st.text_input(
            "Reason (visible in audit log)",
            placeholder="e.g. 1 interview / 14 apps in 8 weeks",
            key="_supp_form_reason",
        )
        submitted = st.form_submit_button("➕ Add suppression", type="primary")

        if submitted:
            ttl_days: int | None
            if ttl_choice == "permanent":
                ttl_days = None
            else:
                ttl_days = int(ttl_choice.rstrip("d"))
            ok, err, until, canon = pipeline_state.validate_suppression_form(
                scope=scope, name=name or "",
                ttl_days=ttl_days, reason=reason,
            )
            if not ok:
                st.error(err, icon="❌")
                return
            try:
                from automation import suppressions as supp  # noqa: WPS433
                if scope == "sector":
                    supp.add_sector(canon, until,
                                     reason or "manual via UI")
                else:
                    supp.add_company(canon, until,
                                      reason or "manual via UI")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Save failed: {exc}", icon="❌")
                return
            until_msg = "permanent" if until is None else f"until {until.isoformat()}"
            st.success(
                f"Muted {scope} {canon!r} ({until_msg})", icon="🔇",
            )
            if until is None:
                st.warning(
                    "This is a permanent mute (no auto-lift). "
                    "Lift manually when you're ready to see this scope again.",
                    icon="⚠️",
                )
            st.rerun()


@st.cache_data(ttl=300, show_spinner=False)
def _excludable_company_groups() -> list[tuple[str, list[dict]]]:
    """Canonical-deduped TARGETS companies grouped by sector, for the exclude
    checkbox UI.

    Returns [(sector, [{canon, label, names:[...]}, ...]), ...] with the Big-6
    sector first. De-dupes by canonical key so RBC / RBC Global Asset
    Management collapse onto ONE checkbox (avoids a Streamlit duplicate-key
    crash AND makes the one-box-affects-two behaviour explicit via `names`).
    Display label = the SHORTEST raw name for the key (deterministic). Cached
    5 min — TARGETS is a static module constant."""
    try:
        sys.path.insert(0, str(ROOT / "automation"))
        from jd_scraper import TARGETS  # noqa: E402
        from brand_aliases import canonical_brand  # noqa: E402
    except Exception:
        return []

    # canon -> {sector, names:set}. First sector wins for grouping; the bank
    # block is listed before its asset-management siblings in TARGETS, so the
    # Big-6 entries land under "Canadian Big 6 Banks".
    by_canon: dict[str, dict] = {}
    sector_order: list[str] = []
    for t in TARGETS:
        name = t.get("name", "")
        sector = t.get("sector", "") or "(unsectored)"
        canon = canonical_brand(name).lower()
        if not canon:
            continue
        if canon not in by_canon:
            by_canon[canon] = {"sector": sector, "names": []}
            if sector not in sector_order:
                sector_order.append(sector)
        by_canon[canon]["names"].append(name)

    groups: dict[str, list[dict]] = {}
    for canon, info in by_canon.items():
        label = min(info["names"], key=len)  # shortest = cleanest display name
        groups.setdefault(info["sector"], []).append({
            "canon": canon, "label": label, "names": sorted(info["names"]),
        })

    # Big-6 first (the headline use case), then the rest in TARGETS order.
    ordered = sorted(
        sector_order,
        key=lambda s: (0 if "Big 6" in s else 1, sector_order.index(s)),
    )
    return [(s, sorted(groups[s], key=lambda g: g["label"])) for s in ordered]


def _render_excluded_companies_admin() -> None:
    """Permanent company exclude-list admin — checkboxes over TARGETS.

    Distinct from suppressions: this is a PERMANENT, source-level block (the
    scraper never queries the company, both Gmail paths drop its rows, and
    worklist rebuild never re-materializes them). No TTL, no reason.

    State model is Cluster-A-safe: the on-disk `data/excludes.json` is the SOLE
    source of truth, read FRESH every render. The checkbox `value` derives from
    disk membership; on a change we diff the widget return against DISK (never
    against a seeded session value), write immediately, and rerun. So an
    unrelated rerun on the same card can never drift the rendered state."""
    try:
        from automation import excludes as _excl  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Exclude-list module unavailable: {exc}", icon="⚠️")
        return

    try:
        disk_set = _excl.load()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not read exclude-list: {exc}", icon="⚠️")
        return

    groups = _excludable_company_groups()
    if not groups:
        st.caption("Target list unavailable — cannot render exclude controls.")
        return

    st.caption(
        "Tick a company to **permanently** stop fetching its jobs — from the "
        "web scrape, both Gmail paths, and worklist rebuilds. Untick to bring "
        "it back. This is a hard source-level block; for a temporary lane "
        "mute use 🔇 suppressions on the ③ Triage card instead."
    )

    for sector, items in groups:
        st.markdown(f"**{sector}**")
        # Up to 3 checkboxes per row to keep the list compact.
        for i in range(0, len(items), 3):
            cols = st.columns(3)
            for col, item in zip(cols, items[i:i + 3]):
                canon = item["canon"]
                label = item["label"]
                # Name the siblings one box silences, so it's never a surprise.
                others = [n for n in item["names"] if n != label]
                help_txt = (f"Also affects: {', '.join(others)} "
                            f"(shared canonical key {canon!r})." if others
                            else f"Canonical key {canon!r}.")
                shown = label + (f"  ＋{len(others)}" if others else "")
                on_disk = canon in disk_set
                checked = col.checkbox(
                    shown, value=on_disk, key=f"_excl_cb_{canon}",
                    help=help_txt,
                )
                if checked != on_disk:           # diff vs DISK, never session
                    try:
                        if checked:
                            _excl.add(label)
                        else:
                            _excl.remove(label)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Exclude-list write failed: {exc}", icon="❌")
                    else:
                        verb = "Excluded" if checked else "Restored"
                        st.toast(f"{verb} {label}"
                                 + (f" (+{len(others)} sibling"
                                    f"{'s' if len(others) != 1 else ''})"
                                    if others else ""))
                    st.rerun()


def _classify_worklist_against_cache() -> dict:
    """Bucket every worklist row by what scoring would do.

    Returns counts:
      total              — rows in worklist
      new                — flagged is_new_since_last_score (URL not in
                            previous scored output)
      cached             — has a fit_cache_v2 entry on disk (re-score is
                            free for these)
      in_scored          — URL exists in worklist_scored.json (previously
                            scored, even if cache file is missing)
      needs_llm          — would force a fresh LLM call (no cache, no prev
                            scored entry). This is what the user pays for.
      stale_in_scored    — in scored output but cache file missing (orphaned
                            cache; second-chance read avoids the API call)
    """
    out = {
        "total": 0, "new": 0, "cached": 0, "in_scored": 0,
        "needs_llm": 0, "stale_in_scored": 0,
    }
    wl_path = OUT_DIR / "worklist.json"
    if not wl_path.exists():
        return out
    try:
        wl = json.loads(wl_path.read_text(encoding="utf-8"))
    except Exception:
        return out

    # Lazy-import fit_scorer for the canonical URL hash function so the
    # buckets line up with what the scorer would actually find.
    try:
        import sys as _sys
        _ad = str(ROOT / "automation")
        if _ad not in _sys.path:
            _sys.path.insert(0, _ad)
        from fit_scorer import _url_hash  # type: ignore
    except Exception:
        return out
    fit_cache_dir = OUT_DIR / "fit_cache"

    scored_urls: set[str] = set()
    sc_path = OUT_DIR / "worklist_scored.json"
    if sc_path.exists():
        try:
            sc = json.loads(sc_path.read_text(encoding="utf-8"))
            for r in sc.get("results", []) or []:
                u = r.get("link") or r.get("url") or ""
                if u:
                    scored_urls.add(u)
        except Exception:
            pass

    rows = wl.get("results", []) or []
    out["total"] = len(rows)
    for r in rows:
        url = r.get("link") or r.get("url") or ""
        if not url:
            continue
        is_new = bool(r.get("is_new_since_last_score"))
        try:
            has_cache = (fit_cache_dir / f"{_url_hash(url)}.v2.json").exists()
        except Exception:
            has_cache = False
        in_scored = url in scored_urls
        if is_new:
            out["new"] += 1
        if has_cache:
            out["cached"] += 1
        if in_scored:
            out["in_scored"] += 1
            if not has_cache:
                out["stale_in_scored"] += 1
        # "Needs LLM": no cache AND not in previous scored output. Anything
        # already in scored output reuses the prior verdict via the
        # second-chance fit-cache read in fit_scorer.
        if not has_cache and not in_scored:
            out["needs_llm"] += 1
    return out


def render_two_sources_panel(container=None) -> None:
    """Show how the two job-list sources feed the worklist.

    Layout (3 cards side-by-side):
      ┌─────────────┐   ┌─────────────┐      ┌─────────────────┐
      │ 🛰 Web scrape│   │📬 Gmail alerts│ ──► │📋 Merged worklist│
      │  N rows     │   │  N rows      │      │  N rows         │
      │  Xh ago     │   │  Xm ago      │      │  scrape: A      │
      │  drops: …   │   │  filters: …  │      │  gmail:  B      │
      └─────────────┘   └─────────────┘      │  both:   C      │
                                              └─────────────────┘

    Each card shows last-run age, row counts, and what each filter dropped
    so the user can see the funnel at a glance instead of having to dig
    into the audit pack.
    """
    target = container or st
    out = OUT_DIR

    # ── Web scrape ──────────────────────────────────────────────────────
    scan_files = sorted(
        [p for p in out.glob("scan_*.json")
         if "_scored" not in p.name
         and "scan_gmail_" not in p.name
         and "scan_checkpoint" not in p.name],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    scan_path = scan_files[0] if scan_files else None
    scan_d = {}
    if scan_path:
        try:
            scan_d = json.loads(scan_path.read_text(encoding="utf-8"))
        except Exception:
            scan_d = {}
    scan_rows = len(scan_d.get("results", []) or [])
    scan_companies = scan_d.get("companies_scanned", 0)
    scan_dedup = scan_d.get("dedup_stats", {}) or {}
    scan_drops = scan_d.get("filter_drops") or {}
    scan_title_drops = len(scan_drops.get("title", []) or [])
    scan_geo_drops = len(scan_drops.get("geo", []) or [])
    scan_age = (_file_age_hours(scan_path) if scan_path else None)

    # ── Gmail ───────────────────────────────────────────────────────────
    gmail_files = sorted(out.glob("scan_gmail_*.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
    gmail_path = gmail_files[0] if gmail_files else None
    gmail_d = {}
    if gmail_path:
        try:
            gmail_d = json.loads(gmail_path.read_text(encoding="utf-8"))
        except Exception:
            gmail_d = {}
    gmail_diag = gmail_d.get("harvest_diagnostics", {}) or {}
    gmail_kept = len(gmail_d.get("results", []) or [])
    gmail_alerts = gmail_diag.get("linkedin_alerts_seen", 0)
    gmail_parsed = gmail_diag.get("rows_parsed", 0)
    gmail_geo_drops = gmail_diag.get("rows_dropped_location", 0)
    gmail_excluded_drops = gmail_diag.get("rows_dropped_excluded", 0)
    gmail_quarantine = len(gmail_diag.get("quarantine", []) or [])
    gmail_age = (_file_age_hours(gmail_path) if gmail_path else None)

    # ── Worklist ─────────────────────────────────────────────────────────
    wl_path = out / "worklist.json"
    wl_d = {}
    if wl_path.exists():
        try:
            wl_d = json.loads(wl_path.read_text(encoding="utf-8"))
        except Exception:
            wl_d = {}
    wl_stats = wl_d.get("stats", {}) or {}
    wl_total = wl_stats.get("total", 0)
    wl_scrape = wl_stats.get("scrape", 0)
    wl_gmail = wl_stats.get("gmail", 0)
    wl_both = wl_stats.get("both", 0)
    wl_new = wl_stats.get("new_since_last_score", 0)
    wl_excluded = wl_stats.get("excluded_dropped", 0)
    wl_merges = len(wl_d.get("merged_pairs", []) or [])
    wl_quarantine = len(wl_d.get("quarantine", []) or [])
    wl_age = _file_age_hours(wl_path) if wl_path.exists() else None

    target.markdown("#### 🔀 Job-list sources → worklist")
    target.caption(
        "Two independent feeds converge into the worklist that the scorer "
        "reads. Each filter that drops a row is shown — click 📊 xlsx on "
        "Latest outputs below to see WHICH rows got dropped."
    )
    col_scrape, col_arrow1, col_gmail, col_arrow2, col_pool = target.columns(
        [4, 1, 4, 1, 5]
    )

    # Web scrape card
    with col_scrape:
        with st.container(border=True):
            st.markdown("**🛰 Web scrape**")
            if scan_path is None:
                st.caption("No scrape yet")
            else:
                st.metric("Rows kept", f"{scan_rows:,}")
                st.caption(
                    f"`{scan_path.name}` · {_humanize_age_h(scan_age)}"
                )
                st.caption(f"📡 {scan_companies} companies scanned")
                if scan_dedup:
                    st.caption(
                        f"🔁 {scan_dedup.get('input', 0):,} raw → "
                        f"{scan_dedup.get('dropped_url', 0)} URL-dup, "
                        f"{scan_dedup.get('dropped_near', 0)} near-dup"
                    )
                if scan_title_drops or scan_geo_drops:
                    _bits = []
                    if scan_title_drops:
                        _bits.append(f"{scan_title_drops} title")
                    if scan_geo_drops:
                        _bits.append(f"{scan_geo_drops} geo")
                    st.caption(f"🚫 dropped: {' / '.join(_bits)}")

    with col_arrow1:
        st.markdown(
            "<div style='text-align:center;padding-top:60px;font-size:24px'>+</div>",
            unsafe_allow_html=True,
        )

    # Gmail card
    with col_gmail:
        with st.container(border=True):
            st.markdown("**📬 Gmail alerts**")
            if gmail_path is None:
                st.caption("No Gmail fetch yet")
            else:
                st.metric("Rows kept", f"{gmail_kept:,}")
                st.caption(
                    f"`{gmail_path.name}` · {_humanize_age_h(gmail_age)}"
                )
                st.caption(
                    f"📨 {gmail_alerts} alert(s) · {gmail_parsed} parsed"
                )
                _bits = []
                if gmail_geo_drops:
                    _bits.append(f"{gmail_geo_drops} geo")
                if gmail_excluded_drops:
                    _bits.append(f"{gmail_excluded_drops} excluded")
                if gmail_quarantine:
                    _bits.append(f"{gmail_quarantine} ⚠ quarantine")
                if _bits:
                    st.caption(f"🚫 dropped: {' / '.join(_bits)}")

    with col_arrow2:
        st.markdown(
            "<div style='text-align:center;padding-top:60px;font-size:24px'>→</div>",
            unsafe_allow_html=True,
        )

    # Worklist card
    with col_pool:
        with st.container(border=True):
            st.markdown("**📋 Merged worklist**")
            if not wl_d:
                st.caption("No worklist built yet")
            else:
                st.metric(
                    "Pool size", f"{wl_total:,}",
                    delta=f"{wl_new:,} new since last score" if wl_new else None,
                    delta_color="off",
                )
                st.caption(
                    f"`worklist.json` · {_humanize_age_h(wl_age)}"
                )
                st.caption(
                    f"🛰 {wl_scrape:,} scrape · 📬 {wl_gmail:,} gmail · "
                    f"🔁 {wl_both:,} both"
                )
                _wl_bits = []
                if wl_merges:
                    _wl_bits.append(f"{wl_merges} merges")
                if wl_excluded:
                    _wl_bits.append(f"{wl_excluded} excluded")
                if wl_quarantine:
                    _wl_bits.append(f"{wl_quarantine} ⚠ quarantine")
                if _wl_bits:
                    st.caption(f"🔧 dedup: {' / '.join(_wl_bits)}")

    # Cache-classification strip — what scoring would do per row. Lives
    # below the three cards so the user sees scoring economics at a glance:
    # "If I hit Score now, X rows hit cache (free), Y need LLM (paid)."
    if wl_d:
        target.markdown("")  # spacer
        cls = _classify_worklist_against_cache()
        bm1, bm2, bm3, bm4 = target.columns(4)
        bm1.metric(
            "🆕 New since last score", f"{cls['new']:,}",
            help="URLs not in the previous worklist_scored output. "
                 "These are the rows the scorer would re-evaluate.",
        )
        bm2.metric(
            "💾 Cached (free)", f"{cls['cached']:,}",
            help="Rows with a fit_cache_v2 file on disk — re-scoring "
                 "reads the cached verdict and pays nothing.",
        )
        bm3.metric(
            "♻️ Reuse from scored", f"{cls['in_scored']:,}",
            delta=(f"{cls['stale_in_scored']} orphaned cache"
                   if cls['stale_in_scored'] else None),
            delta_color="off",
            help="Rows whose URL is in worklist_scored.json. Even when the "
                 "fit_cache file is missing, the scorer's second-chance "
                 "read pulls the verdict from there — still free.",
        )
        bm4.metric(
            "💸 Needs LLM (paid)", f"{cls['needs_llm']:,}",
            help="No cache AND not in previous scored output → the scorer "
                 "would make a fresh API call. This is the only bucket "
                 "that costs money on Score now.",
        )
        if cls["needs_llm"] == 0 and cls["total"] > 0:
            target.success(
                f"✅ Every row is cached or already scored — clicking "
                f"**🤖 Score worklist** would be free.",
                icon="💰",
            )
        elif cls["needs_llm"] > 0:
            target.caption(
                f"💡 Clicking **🤖 Score worklist** would re-score "
                f"{cls['cached'] + cls['in_scored']:,} cached rows for free "
                f"and make ~{cls['needs_llm']:,} API call(s) for the "
                f"uncached ones."
            )

    # ── Permanent company exclude-list ──────────────────────────────────
    # Always-visible summary (names listed even when collapsed) so an
    # accidental tick is obvious at a glance. The checkbox admin is gated
    # behind an inspect toggle that auto-opens on first run (nothing excluded
    # yet) for discoverability. Reads disk fresh — the count is cheap.
    target.markdown("")  # spacer
    try:
        from automation import excludes as _excl_mod  # noqa: WPS433
        _excl_entries = _excl_mod.list_excluded()
    except Exception:
        _excl_entries = []
    _excl_n = len(_excl_entries)
    if _excl_n:
        _names = ", ".join(e.get("name", "?") for e in _excl_entries)
        target.caption(f"🚫 **{_excl_n} excluded** (never fetched): {_names}")
    else:
        target.caption("🚫 No companies excluded — tick one below to never "
                       "fetch its jobs again.")
    if _vc_inspect_toggle(
        "inputs_exclude", "🚫 Excluded companies (never fetch)",
        default=(_excl_n == 0),
    ):
        _render_excluded_companies_admin()


def render_latest_outputs_row(container=None, key_prefix: str = "out") -> None:
    """Reusable 'Latest outputs' panel — one row per artifact (scrape, gmail,
    worklist pool, scored, promote, brief). Each row offers JSON + xlsx
    downloads via render_artifact_download(). Lazy-imports audit_pack.
    """
    target = container or st
    try:
        import sys as _sys
        import importlib as _il
        _ad = str(ROOT / "automation")
        if _ad not in _sys.path:
            _sys.path.insert(0, _ad)
        # Streamlit holds modules across reruns — if `audit_pack` was imported
        # before the per-artifact builders shipped, the cached object lacks
        # them and the `from … import …` below raises ImportError. Force a
        # reload so a stale cache picks up new functions without a restart.
        if "audit_pack" in _sys.modules:
            _il.reload(_sys.modules["audit_pack"])
        from audit_pack import (
            gmail_scan_to_xlsx, scan_to_xlsx, scored_to_xlsx,
            worklist_to_xlsx, promote_to_xlsx,
        )
    except Exception as e:
        target.caption(f"Per-artifact downloads unavailable: {e}")
        return

    with target.container(border=True):
        st.markdown("#### 📦 Latest outputs")
        st.caption(
            "Every action emits a JSON artifact under `automation/outputs/`. "
            "Hit 📊 to convert to an Excel workbook on the fly."
        )
        # Scrape
        scan_path = _latest_artifact(
            "scan_*.json",
            exclude=("_scored", "scan_gmail_", "scan_checkpoint"),
        )
        render_artifact_download(
            "🛰 Scrape", scan_path, scan_to_xlsx,
            f"{key_prefix}_scan",
        )
        # Gmail fetch
        gmail_path = _latest_artifact("scan_gmail_*.json")
        render_artifact_download(
            "📬 Gmail fetch", gmail_path, gmail_scan_to_xlsx,
            f"{key_prefix}_gmail",
        )
        # Worklist (pool that scoring reads from)
        wl_path = OUT_DIR / "worklist.json"
        render_artifact_download(
            "📋 Worklist pool", wl_path if wl_path.exists() else None,
            worklist_to_xlsx, f"{key_prefix}_worklist",
        )
        # Scored
        sc_path = OUT_DIR / "worklist_scored.json"
        render_artifact_download(
            "🤖 Scored", sc_path if sc_path.exists() else None,
            scored_to_xlsx, f"{key_prefix}_scored",
        )
        # Promote — needs the .json sibling (only emitted by post-this-commit
        # runs; older promotes only have .md, which has no row data)
        pr_path = _latest_artifact("promote_report_*.json")
        render_artifact_download(
            "📋 Promote report", pr_path, promote_to_xlsx,
            f"{key_prefix}_promote",
        )


def _vc_inspect_toggle(stage: str, label: str, default: bool = False) -> bool:
    """Button-gated inspect flag for a vertical stage card.

    Critic perf-fix: st.expander still RUNS its body every rerun (collapse
    only hides output client-side). A session-state toggle lets the caller
    `if`-skip the heavy body entirely when closed, so six stacked cards
    don't re-parse thousands of rows on every one of the page's ~40
    st.rerun() calls. Returns True when the body should render.
    """
    _key = f"_vc_inspect_{stage}"
    _open = st.session_state.setdefault(_key, default)
    _icon = "▾" if _open else "▸"
    if st.button(f"{_icon} {label}", key=f"_vc_inspect_btn_{stage}",
                 width="stretch"):
        st.session_state[_key] = not _open
        st.rerun()
    return st.session_state[_key]


# v3.2: maps each stage-card inspect toggle to the Pipeline sub-page that hosts
# it, so a banner CTA can cross pages (see _route_banner_cta). Keys match the
# `_vc_inspect_<stage>` toggle names; values are the `_nav_sub_🎯 Pipeline` keys.
_TOGGLE_TO_SUBPAGE = {
    "worklist": "Refresh",   # ② Worklist inspect → ① Refresh view
    "triage":   "Score",     # ③ Triage / suppressions → ② Score view
    "scoring":  "Score",     # ④ Scoring verdicts → ② Score view
    "promote":  "Promote",   # ⑤ Auto-promote → ③ Promote view
}


def _route_banner_cta(action: str | None, active_runs: list | None = None) -> None:
    """Make the top-of-page banner CTA actually *do* something.

    Streamlit has no scroll anchor, so "go to stage X" is realised by opening
    that stage card's inspect toggle (`_vc_inspect_<stage>` session flag) so
    its body is visible after the rerun. On top of that:

      • promote        → open ⑤ + launch a dry-run promote PREVIEW (no tracker
                         write). The ⑤ card then shows the report + an
                         [✅ Apply to tracker] commit button (preview→commit,
                         the flow the user picked). Skips the launch if a run
                         is already active.
      • score          → open ④ Scoring (② Score view — the 🤖 Score worklist
                         button lives there after the v3.2 split). Not
                         auto-launched — scoring costs API spend, so the user
                         clicks the cost-labelled button themselves.
      • review_verdicts → ② Score (verdicts live in the ④ scored card).
      • review_suppressions → ② Score (③ Triage suppression admin).
      • refresh / setup / retry_* → ① Refresh, where the always-visible 🛰
                         scrape / 📬 Gmail launch buttons live on the ① Inputs
                         card. (No inspect toggle — those buttons aren't gated.)
      • stop_run       → signal-stop the active run immediately.
      • quarantine     → open ② so the user can inspect the merged pool.
      • set_api_key    → guidance toast (the key widget owns its sidebar
                         expander; we can't force it open from here).

    Page routing: `open_toggle` opens a card's _vc_inspect_<stage> flag AND
    implies its host sub-page via _TOGGLE_TO_SUBPAGE. `target_view` overrides
    the destination sub-page WITHOUT opening a toggle — used for the refresh/
    setup/retry CTAs whose launch buttons are always-visible on ① Refresh.

    All paths end in st.rerun() so the freshly-set toggle/flags take effect.
    """
    open_toggle = None          # which _vc_inspect_<stage> to force-open
    target_view = None          # explicit Pipeline sub-page (Refresh/Score/Promote)
    toast = None

    if action == "promote":
        open_toggle = "promote"
        if not any_work_active:
            try:
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--skip-scrape", "--skip-score",   # dry-run promote preview
                ])
                st.session_state["_last_launch"] = {
                    "run_id": rec.run_id, "label": "Promote preview",
                }
                # Arm the Apply button — it only enables after a preview that
                # was launched THIS session (doc §167 "enabled only after a
                # preview"), so a stale on-disk report can't invite a commit.
                st.session_state["_promote_preview_armed"] = True
                toast = ("📋 Promote preview running — review the report in ⑤, "
                         "then Apply to tracker.")
            except Exception as e:  # noqa: BLE001
                toast = f"Couldn't launch promote preview: {e}"
        else:
            toast = "A run is active — opened ⑤; preview once it finishes."
    elif action == "score":
        # 🤖 Score worklist now lives on the ④ Scoring card (② Score view),
        # not the ⑤ run card — route there. Not auto-launched: scoring costs
        # API spend, so the user clicks the cost-labelled button themselves.
        open_toggle = "scoring"
        toast = "Opened ④ Scoring — hit 🤖 Score worklist (cost shown on the button)."
    elif action in ("review_verdicts",):
        open_toggle = "scoring"
        toast = "Opened ④ Scoring — inspect verdicts to hand-pick roles."
    elif action in ("review_suppressions",):
        open_toggle = "triage"
        toast = "Opened ③ Triage — manage suppressions in the admin panel."
    elif action == "refresh":
        target_view = "Refresh"
        toast = "Opened ① Refresh — launch 🛰 scrape / 📬 Gmail to refresh inputs."
    elif action == "setup":
        target_view = "Refresh"
        toast = ("Opened ① Refresh — connect Gmail in the sidebar, then launch "
                 "a scrape to populate the worklist.")
    elif action and action.startswith("retry_"):
        target_view = "Refresh"
        toast = f"Opened ① Refresh — relaunch the {action[len('retry_'):]} stage."
    elif action == "stop_run":
        _runs = active_runs or []
        if _runs:
            try:
                scan_runner.stop_run(_runs[0].get("run_id"))
                toast = "⏹ Stop signal sent — the run exits after its current step."
            except Exception as e:  # noqa: BLE001
                toast = f"Couldn't stop the run: {e}"
        else:
            toast = "No active run to stop."
    elif action == "quarantine":
        open_toggle = "worklist"
        toast = ("Opened ② Worklist — inspect the pool; a high quarantine "
                 "ratio usually means a parser/source regression.")
    elif action == "set_api_key":
        toast = "Set your key in the sidebar → Manage Anthropic API key."
    else:
        toast = "Opened the relevant stage below."

    if open_toggle:
        st.session_state[f"_vc_inspect_{open_toggle}"] = True
    # v3.2: the stage cards now live on 3 separate Pipeline sub-pages, so
    # opening a toggle is no longer enough — we must also switch to the page
    # that hosts that card, or the toggle opens an off-page card and nothing
    # visible happens. This handler runs AFTER the Pipeline sub-radio has
    # instantiated, so a direct write to its key is dropped by Streamlit.
    # Stash the target in a non-widget key; the pre-radio transfer block
    # (near the legacy-nav shim) applies it next run. An explicit target_view
    # wins over the toggle-implied page (for CTAs with no card to open).
    _sub = target_view or _TOGGLE_TO_SUBPAGE.get(open_toggle)
    if _sub:
        st.session_state["_pipe_pending_view"] = _sub
    if toast:
        st.toast(toast)
    st.rerun()


def _vc_download_row(stage: str) -> None:
    """Per-card 📄 JSON / 📊 xlsx downloads for a vertical stage card.

    Reuses render_artifact_download (lazy two-click xlsx, no per-rerun
    pandas cost). Maps each stage to its on-disk artifact(s) + builder.
    Lazy-imports audit_pack with a reload so a stale Streamlit module
    cache picks up new builders without a restart (same guard as
    render_latest_outputs_row).
    """
    try:
        import sys as _sys
        import importlib as _il
        _ad = str(ROOT / "automation")
        if _ad not in _sys.path:
            _sys.path.insert(0, _ad)
        if "audit_pack" in _sys.modules:
            _il.reload(_sys.modules["audit_pack"])
        from audit_pack import (
            gmail_scan_to_xlsx, scan_to_xlsx, scored_to_xlsx,
            worklist_to_xlsx, promote_to_xlsx, triage_to_xlsx,
            tracker_to_xlsx,
        )
    except Exception as e:
        st.caption(f"Downloads unavailable: {e}")
        return

    def _latest(glob, exclude=()):
        files = sorted(OUT_DIR.glob(glob), key=lambda p: p.stat().st_mtime,
                       reverse=True)
        for f in files:
            if not any(x in f.name for x in exclude):
                return f
        return None

    if stage == "inputs":
        render_artifact_download(
            "🛰 Scrape", _latest("scan_*.json",
                                 exclude=("_scored", "scan_gmail_", "scan_checkpoint")),
            scan_to_xlsx, "vc_scan")
        render_artifact_download(
            "📬 Gmail", _latest("scan_gmail_*.json"),
            gmail_scan_to_xlsx, "vc_gmail")
    elif stage == "worklist":
        _wl = OUT_DIR / "worklist.json"
        render_artifact_download(
            "📋 Worklist pool", _wl if _wl.exists() else None,
            worklist_to_xlsx, "vc_worklist")
    elif stage == "triage":
        # Triage-centric export: Passed / Dropped (with rule reasons) /
        # Suppressed sheets — distinct from the verdict-led scored export.
        # Prefer worklist_triage.json (written by the free 🎯 Run triage
        # button — fresh, reflects current rules/suppressions) over
        # worklist_scored.json (the LLM-scored snapshot which can be days
        # stale and was previously surfacing as "Triage (passed/dropped)
        # · 7d ago" even right after a triage run). Fall back only when
        # the user hasn't run the standalone triage yet.
        _tr = OUT_DIR / "worklist_triage.json"
        _sc = OUT_DIR / "worklist_scored.json"
        _triage_src = _tr if _tr.exists() else (_sc if _sc.exists() else None)
        render_artifact_download(
            "🎯 Triage (passed/dropped)", _triage_src,
            triage_to_xlsx, "vc_triage")
    elif stage == "scored":
        _sc = OUT_DIR / "worklist_scored.json"
        render_artifact_download(
            "🤖 Scored + triage drops", _sc if _sc.exists() else None,
            scored_to_xlsx, f"vc_scored_{stage}")
    elif stage == "promote":
        render_artifact_download(
            "📤 Promote report", _latest("promote_report_*.json"),
            promote_to_xlsx, "vc_promote")
    elif stage == "tracker":
        render_artifact_download(
            "🗂 Tracker (sheet per status)",
            TRACKER if Path(TRACKER).exists() else None,
            tracker_to_xlsx, "vc_tracker")


@st.cache_data(ttl=60, show_spinner=False)
def _worklist_hidden_by_mutes(wl_mtime: float, supp_mtime: float) -> tuple[int, int]:
    """(hidden_rows, active_mutes) — how many worklist rows an active mute
    would suppress, and how many mutes are active (doc §370).

    Cached on (worklist mtime, suppressions mtime) so the 1,400-row scan
    runs at most once per change, not every rerun. Returns (0, 0) on any
    error or when no mutes are active (the dormant default)."""
    try:
        from automation import suppressions as _supp  # noqa: WPS433
        state = _supp.load_active()
        n_mutes = len(state.get("sectors", []) or []) + len(state.get("companies", []) or [])
        if not n_mutes:
            return (0, 0)
        wl = json.loads((OUT_DIR / "worklist.json").read_text(encoding="utf-8"))
        hidden = 0
        for row in wl.get("results", []) or []:
            suppressed, _ = _supp.is_suppressed(row, snapshot=state)
            if suppressed:
                hidden += 1
        return (hidden, n_mutes)
    except Exception:
        return (0, 0)


def _vc_promote_apply_panel(busy: bool) -> None:
    """Preview→commit step for ⑤ Auto-promote.

    The banner's `Promote N` CTA (and the run card's promote button) launch a
    DRY-RUN preview — `run_pipeline.py --skip-scrape --skip-score`, which
    writes a `promote_report_*.json` with `mode: dry_run` and the full
    would-add list under `promoted[]` but does NOT touch the tracker. This
    panel surfaces that preview and gives the missing second step: an explicit
    [✅ Apply N to tracker] button that shells `auto_promote.py --commit`.

    Renders nothing when there's no recent (<6h) dry-run preview — keeps the
    card quiet until the user has actually previewed.
    """
    files = sorted(OUT_DIR.glob("promote_report_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return
    latest = files[0]
    try:
        rep = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return
    if rep.get("mode") != "dry_run":
        # Last action was a commit (or single-URL run) — nothing to apply.
        return
    age_h = _file_age_hours(latest)
    if age_h is not None and age_h > 6:
        return  # stale preview; user should re-preview before committing
    would_add = (rep.get("summary") or {}).get("added", 0)
    rows = rep.get("promoted") or rep.get("new_entries") or []

    with st.container(border=True):
        if not would_add:
            st.caption(
                f"✅ Promote preview ({_humanize_age_h(age_h)}): nothing new "
                "to add — every above-threshold role is already in the tracker."
            )
            return
        st.markdown(f"**📋 Preview ready — {would_add} role(s) would be added**")
        # Compact peek at the top would-add rows so the commit isn't blind.
        _peek = [
            {"score": r.get("score"), "company": r.get("company"),
             "title": r.get("title"), "sector": r.get("sector")}
            for r in rows[:8]
        ]
        if _peek:
            st.dataframe(pd.DataFrame(_peek), hide_index=True, width="stretch",
                         height=min(240, 40 + 36 * len(_peek)))
            if len(rows) > len(_peek):
                st.caption(f"…and {len(rows) - len(_peek)} more.")
        # Apply only enables after a preview launched THIS session (doc §167) —
        # a stale on-disk dry-run report alone is not enough to invite a commit.
        _armed = bool(st.session_state.get("_promote_preview_armed"))
        _ac1, _ac2 = st.columns([2, 1])
        with _ac1:
            if not _armed:
                st.caption("▶️ Run a Promote **preview** above to enable Apply.")
            if st.button(f"✅ Apply {would_add} to tracker", type="primary",
                         width="stretch", disabled=(busy or not _armed),
                         key="_vc_promote_apply",
                         help="Commit these roles to the tracker "
                              "(auto_promote.py --commit). A .bak is written "
                              "first, so it's reversible."):
                try:
                    rec = scan_runner.start_run("promote", [
                        sys.executable,
                        str(ROOT / "automation" / "auto_promote.py"),
                        "--commit",
                        "--min-score", str(rep.get("min_score", 7)),
                    ] + (["--include-watch"] if rep.get("include_watch") else []))
                    st.session_state["_last_launch"] = {
                        "run_id": rec.run_id, "label": "Promote (commit)",
                    }
                    # Arm the success-feedback overlay (doc §90) — the banner
                    # shows "✅ Promoted N" for ~10 min after this commit.
                    st.session_state["_promote_feedback"] = {
                        "count": int(would_add),
                        "ts": datetime.now().isoformat(timespec="seconds"),
                    }
                    # Disarm — the next commit needs a fresh preview.
                    st.session_state["_promote_preview_armed"] = False
                    st.toast(f"📋 Committing {would_add} role(s) to the tracker…",
                             icon="✅")
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Couldn't launch commit: {e}")
        with _ac2:
            st.caption(f"Preview from {_humanize_age_h(age_h)} · "
                       f"min-score {rep.get('min_score', 7)}")


def _vc_audit_pack_download() -> None:
    """Combined multi-sheet audit pack — the 'grab everything' export the
    UX critic flagged as lost when downloads moved onto per-stage cards.
    Restored here in the footer. Lazy two-click build."""
    try:
        import sys as _sys
        _ad = str(ROOT / "automation")
        if _ad not in _sys.path:
            _sys.path.insert(0, _ad)
        from audit_pack import build_audit_pack as _build_pack
    except Exception as e:
        st.caption(f"Audit pack unavailable: {e}")
        return
    _scan = sorted(
        (p for p in OUT_DIR.glob("scan_*.json")
         if "_scored" not in p.name and "scan_gmail_" not in p.name
         and "scan_checkpoint" not in p.name),
        key=lambda p: p.stat().st_mtime, reverse=True)
    _stamp = "latest"
    if _scan:
        _parts = _scan[0].stem.split("_")
        _stamp = _parts[1] if len(_parts) > 1 else "latest"
    st.caption(
        "One Excel workbook with every stage as a sheet: raw scrape, "
        "title/geo drops, gmail, worklist, merges, stage-1 drops, scored, "
        "promote skips."
    )
    if st.button("📦 Build full audit pack (xlsx)", key="_vc_build_pack"):
        with st.spinner("Building multi-sheet xlsx…"):
            st.session_state["_vc_pack_bytes"] = _build_pack(_stamp)
    if st.session_state.get("_vc_pack_bytes"):
        st.download_button(
            "⬇ Download audit_pack.xlsx",
            data=st.session_state["_vc_pack_bytes"],
            file_name=f"audit_pack_{_stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="_vc_dl_pack",
        )


def save_tracker(d: dict):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TRACKER.with_suffix(f".bak.{stamp}.json")
    if TRACKER.exists():
        bak.write_text(TRACKER.read_text(encoding="utf-8"), encoding="utf-8")
    # Atomic write under portalocker lock — protects against concurrent
    # writers (auto_promote CLI, score_url CLI) and against truncation if
    # the process dies mid-write.
    try:
        from safe_json import write_json as _sj_write
        _sj_write(TRACKER, d)
    except ImportError:
        TRACKER.write_text(json.dumps(d, indent=2), encoding="utf-8")
    # Invalidate ONLY the tracker cache. `st.cache_data.clear()` would also
    # nuke the 1h _ai_draft cache and 2min _load_inbox_signals cache.
    load_tracker.clear()


def save_crm(d: dict):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = CRM.with_suffix(f".bak.{stamp}.json")
    if CRM.exists():
        bak.write_text(CRM.read_text(encoding="utf-8"), encoding="utf-8")
    # Atomic write under portalocker lock — protects against concurrent
    # writers and against truncation if the process dies mid-write.
    try:
        from safe_json import write_json as _sj_write
        _sj_write(CRM, d)
    except ImportError:
        CRM.write_text(json.dumps(d, indent=2), encoding="utf-8")
    load_crm.clear()


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


FOLLOWUP_TERMINAL_STATUSES = {
    "Rejected", "Offer", "Hired", "Withdrawn", "Expired", "Declined",
}


def followup_buckets(jobs: list[dict], today_date: date | None = None) -> dict:
    """Partition jobs into overdue/due-today/due-this-week/upcoming/idle buckets.

    A job is in the follow-up loop if:
      - it has date_applied
      - its status is not terminal (not Rejected/Offer/Hired/Withdrawn/Expired)
      - it has followup_schedule.next_due set

    Returns:
      {"overdue": [(days_overdue, job), ...],
       "due_today": [job, ...],
       "due_this_week": [(days_until, job), ...],
       "upcoming": [(days_until, job), ...],
       "no_schedule": [job, ...]   # applied but no next_due — likely needs first follow-up}
    """
    today_date = today_date or date.today()
    buckets = {
        "overdue": [],
        "due_today": [],
        "due_this_week": [],
        "upcoming": [],
        "no_schedule": [],
    }
    # Archived rows must not nag follow-ups — an archived Applied role
    # otherwise shows as overdue/due-today and inflates the badge (doc §340).
    # apply_followup_gate(job)==True means "skip follow-ups" (archived OR
    # terminal). Imported locally to match the pattern used elsewhere in
    # this module (tracker_ops isn't a module-scope import).
    from automation import tracker_ops as _tops_fb  # noqa: WPS433
    for j in jobs:
        if _tops_fb.apply_followup_gate(j):
            continue
        if not j.get("date_applied"):
            continue
        # FOLLOWUP_TERMINAL_STATUSES is a superset of tracker_ops.TERMINAL_STATUSES
        # (it also includes "Declined"), so keep this check after the gate.
        if j.get("status") in FOLLOWUP_TERMINAL_STATUSES:
            continue
        sched = j.get("followup_schedule") or {}
        next_due = parse_date(sched.get("next_due"))
        if not next_due:
            buckets["no_schedule"].append(j)
            continue
        delta = (next_due - today_date).days
        if delta < 0:
            buckets["overdue"].append((-delta, j))
        elif delta == 0:
            buckets["due_today"].append(j)
        elif delta <= 7:
            buckets["due_this_week"].append((delta, j))
        else:
            buckets["upcoming"].append((delta, j))
    buckets["overdue"].sort(key=lambda t: -t[0])  # most overdue first
    buckets["due_this_week"].sort(key=lambda t: t[0])
    buckets["upcoming"].sort(key=lambda t: t[0])
    return buckets


def advance_followup(job: dict, today_date: date | None = None) -> None:
    """Advance a job's next_due one cadence step. Mutates the job in place.
    Called when the user logs a follow-up, so the next nudge lands on the
    right day. When the cadence is exhausted, clears next_due (no more nudges)."""
    today_date = today_date or date.today()
    sched = job.setdefault("followup_schedule", {"cadence_days": [3, 10, 21]})
    cadence = sched.get("cadence_days") or [3, 10, 21]
    applied = parse_date(job.get("date_applied"))
    if not applied:
        return
    # Find the next cadence step after today
    for days in cadence:
        candidate = applied + timedelta(days=days)
        if candidate > today_date:
            sched["next_due"] = candidate.isoformat()
            return
    # Cadence exhausted — stop nudging
    sched["next_due"] = None


def seed_followup(job: dict, applied_on: date | None = None) -> None:
    """Seed followup_schedule.next_due when a role first becomes Applied."""
    applied_on = applied_on or date.today()
    sched = job.setdefault("followup_schedule", {"cadence_days": [3, 10, 21]})
    cadence = sched.get("cadence_days") or [3, 10, 21]
    if cadence:
        sched["next_due"] = (applied_on + timedelta(days=cadence[0])).isoformat()
    job["date_applied"] = applied_on.isoformat()


@st.cache_data(ttl=120)
def _load_inbox_signals(days: int):
    """Inbox signals fetch — module-scope so the @cache_data decorator survives
    page reruns. Defined inside the Dashboard block previously, which created
    a fresh function identity on every render and defeated the 2-min cache."""
    sys.path.insert(0, str(ROOT / "automation"))
    import gmail_reader as gr
    msgs = gr.fetch_inbox_signals(days=days, limit=50)
    return [
        {"uid": m.uid, "date": m.date, "kind": m.kind,
         "sender": m.sender or m.sender_email,
         "sender_email": m.sender_email,
         "subject": m.subject, "snippet": m.snippet}
        for m in msgs
    ]


_SESSION_STATE_PATH = Path.home() / ".applyagent" / "session.json"


def read_last_visit() -> datetime | None:
    """Read last-visit timestamp from `~/.applyagent/session.json`. None on
    first visit / corrupted file. Used to render the 'since you last looked'
    strip on the Dashboard."""
    try:
        raw = _SESSION_STATE_PATH.read_text(encoding="utf-8")
        ts = json.loads(raw).get("last_visit_at")
        return datetime.fromisoformat(ts) if ts else None
    except Exception:
        return None


def write_last_visit() -> None:
    """Stamp now() into the session file. Called once per Dashboard render
    AFTER the strip has rendered, so the next visit's delta is bounded by
    THIS visit's load time."""
    try:
        _SESSION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_STATE_PATH.write_text(
            json.dumps({"last_visit_at": datetime.now().isoformat()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def compute_next_best_action(
    jobs: list[dict],
    crm_recruiters: list[dict],
    proposals_path: Path,
) -> dict | None:
    """Pick the single highest-priority action across all surfaces.

    Returns a dict {kind, score, label, sublabel, page, ...payload} or None
    if nothing qualifies. Lane multiplier privileges the primary lanes per
    LANE_MULTIPLIERS (the single source of truth): ALM 1.5x, VEN/QUANT 1.3x,
    VAL 1.2x, other 1.0x.
    """
    today_d = date.today()
    candidates: list[dict] = []

    # Tier-1 Found roles (top-fit, ALM-primary first) — recommend Tailor.
    for j in jobs:
        if j.get("status") not in ("Found", "Watch"):
            continue
        if j.get("date_applied"):
            continue
        fit = int(j.get("fit_score_numeric") or 0)
        if fit < 7:
            continue
        urgency = (j.get("urgency") or "").lower()
        pv = (j.get("primary_variant") or "").upper()
        lm = lane_mult(j)
        urgency_bonus = 3 if urgency == "high" else 0
        has_draft = bool(_find_tailor_docs(j))
        verb = "View tailor & apply" if has_draft else "Tailor"
        score = (fit * 0.8 + urgency_bonus) * lm
        candidates.append({
            "kind": "tailor_or_apply",
            "score": score,
            "label": f"✍️ {verb} {j.get('company', '?')}",
            "sublabel": f"{j.get('title', '?')} · fit {fit}/10"
                        + (f" · {pv}" if pv else ""),
            "page": "🏠 Today",
            "job": j,
            "_breakdown": {
                "fit": fit,
                "lane": pv or "—",
                "lane_mult": lm,
                "urgency_bonus": urgency_bonus,
            },
        })

    # Most overdue follow-up.
    # Phase 3D: route through tracker_ops.apply_followup_gate so archived
    # rows AND terminal-status rows are both excluded. Archive nags an
    # Applied job → no more follow-up reminders.
    from automation import tracker_ops as _tops_fu  # noqa: WPS433
    most_overdue = None
    most_overdue_days = 0
    for j in jobs:
        if _tops_fu.apply_followup_gate(j):
            continue
        nd = parse_date((j.get("followup_schedule") or {}).get("next_due"))
        if nd and (today_d - nd).days > most_overdue_days:
            most_overdue_days = (today_d - nd).days
            most_overdue = j
    if most_overdue is not None and most_overdue_days >= 1:
        score = min(most_overdue_days, 10) * 1.0
        candidates.append({
            "kind": "followup",
            "score": score,
            "label": f"📨 Follow up with {most_overdue.get('company', '?')}",
            "sublabel": f"{most_overdue_days}d overdue · "
                        f"{most_overdue.get('title', '?')}",
            "page": "🏠 Today",
            "job": most_overdue,
        })

    # Top high-priority uncontacted recruiter.
    for c in crm_recruiters:
        if c.get("priority") != "High":
            continue
        if c.get("status") not in ("Not_Contacted", None):
            continue
        if c.get("last_touchpoint"):
            continue
        candidates.append({
            "kind": "recruiter",
            "score": 5.0,
            "label": f"🤝 Reach out to {c.get('firm', c.get('name', '?'))}",
            "sublabel": (c.get("next_action") or "")[:140],
            "page": "🤝 Network",
            "contact": c,
        })
        break  # only surface ONE

    # Pending high-confidence outcome proposal.
    try:
        if proposals_path.exists():
            props = json.loads(proposals_path.read_text(encoding="utf-8")) or []
            for p in props:
                if p.get("status") != "pending":
                    continue
                conf = float(p.get("confidence") or 0)
                if conf < 0.7:
                    continue
                candidates.append({
                    "kind": "outcome",
                    "score": 4.0 + conf * 2,
                    "label": f"✅ Accept proposal: {p.get('company', '?')} → "
                             f"{p.get('proposed_status', '?')}",
                    "sublabel": (p.get("evidence") or {}).get("summary", "")[:140],
                    "page": "🏠 Today",
                    "proposal": p,
                })
                break
    except Exception:
        pass

    if not candidates:
        return None
    return max(candidates, key=lambda c: c["score"])


@st.cache_data(show_spinner=False, ttl=3600)
def _ai_draft(cache_key: str, prompt: str) -> str:
    """Call Claude Haiku and return text. Returns error string if key missing."""
    try:
        import anthropic as _ant
        _k = api_key.load_key()
        if not _k:
            return "⚠️ API key not configured — add it in the sidebar."
        _client = _ant.Anthropic(api_key=_k)
        _msg = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        return _msg.content[0].text.strip()
    except Exception as _e:
        return f"⚠️ Draft failed: {_e}"


def _email_draft_prompt(job: dict, touch_num: int = 1) -> str:
    """Build an email-draft prompt from a tracker job dict."""
    co       = job.get("company", "the company")
    title    = job.get("title", "the role")
    applied  = job.get("date_applied", "recently")
    osfi     = job.get("osfi_hook", "")
    fit      = (job.get("fit_notes") or "")[:300]
    kw       = ", ".join((job.get("keywords") or [])[:6])
    rec_name = (job.get("contact") or {}).get("recruiter_name") or ""
    greeting = f"Hi {rec_name}," if rec_name else "Hi,"

    ordinal = {1: "first", 2: "second", 3: "third"}.get(touch_num, f"{touch_num}th")
    return f"""You are writing a {ordinal} follow-up email for Saber Ayatollahi (CFA, dual MSc, 7+ years ALM/IRRBB/Moody's Analytics).

Role: {title} at {co}
Applied: {applied}
Key skills: {kw}
OSFI regulatory angle: {osfi}
Fit summary: {fit}

Write a concise, confident follow-up email (120–160 words).
- Open with {greeting}
- Reference the specific role
- Lead with one concrete value-add (IRRBB, OSFI B-12, ALM modelling, or vendor-platform expertise)
- End with a clear, non-pushy CTA
- Tone: professional, direct, not sycophantic
- Output ONLY the email body — no subject line, no sign-off name"""


def _interview_prep_prompt(job: dict) -> str:
    """Build an interview prep prompt from a tracker job dict."""
    co    = job.get("company", "the company")
    title = job.get("title", "the role")
    sec   = job.get("sector", "financial services")
    osfi  = job.get("osfi_hook", "")
    fit   = (job.get("fit_notes") or "")[:400]
    kw    = ", ".join((job.get("keywords") or [])[:8])
    level = job.get("level", "Director")
    return f"""Generate interview prep notes for Saber Ayatollahi interviewing for:
Role: {level} — {title} at {co} ({sec})
Keywords: {kw}
OSFI/regulatory angle: {osfi}
Fit context: {fit}

Produce a structured prep brief in markdown with these exact sections:
## Technical Questions (5 likely questions with 1-line answer starters)
## Behavioural Questions (3 questions with STAR talking-point bullets)
## Key Selling Points (3 compelling angles specific to this role)
## Questions to Ask Them (2 smart questions that signal domain depth)

Be specific to the role — reference IRRBB/ALM/OSFI where relevant."""


def _find_tailor_docs(job: dict) -> list:
    """Return list of tailored doc Paths for this job (resume/CL markdown files).

    Checks outputs/tailored/ first (current location, see jd_tailor.py),
    then outputs/ root for legacy files written before the May 2026 split.
    """
    jid = job.get("id", "")
    # Mirror jd_tailor.py's filename slug EXACTLY (safe_company / safe_role =
    # re.sub(r"[^a-zA-Z0-9]+", "_", …)). The old patterns only replaced spaces
    # and kept punctuation that jd_tailor strips — so a role like "Senior
    # Director, Total Portfolio Risk" → file "…_Senior_Director_Total_…" never
    # matched (comma kept in the pattern, dropped in the file) and the drawer
    # wrongly reported "No tailor doc found yet" despite the draft existing.
    _safe_co = re.sub(r"[^a-zA-Z0-9]+", "_", job.get("company") or "").strip("_")
    _safe_role = re.sub(r"[^a-zA-Z0-9]+", "_", job.get("title") or "")[:60].strip("_")
    pat1 = f"*_{jid.replace('-', '_')}*.md"
    pat2 = f"{_safe_co}_{_safe_role}*.md"
    skip = {"scan_", "delta_", "brief_", "promote_", "SCAN_", "scorer_", "weekly_"}
    found: list = []
    for _root in (OUT_DIR / "tailored", OUT_DIR):
        if _root.exists():
            found.extend(_root.glob(pat1))
            found.extend(_root.glob(pat2))
    return sorted(
        {p for p in found if not any(p.name.startswith(s) for s in skip)
         and "_prompt." not in p.name},
        key=lambda p: p.stat().st_mtime, reverse=True,
    )


def _resume_tier() -> str:
    """The session-wide cost/quality tier for resume_agent (set via the
    selector in the Kanban inspector). Default 'balanced' = Opus draft +
    Sonnet validity check (~$0.60), vs 'max' Opus-everything (~$1.30)."""
    return st.session_state.get("_resume_tier", "balanced")


def _find_application_folder(job: dict):
    """Find applications/<date>_<company>_<role>/ for this job — the polished
    resume_agent / resume_render deliverable. Matches resume_render's folder
    slug exactly: drop apostrophes, then re.sub(r'[^A-Za-z0-9]+','-').strip."""
    base = ROOT / "applications"
    if not base.exists():
        return None

    def _slug(s: str) -> str:
        s = (s or "").replace("'", "").replace("’", "")
        return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")

    co, role = _slug(job.get("company")), _slug(job.get("title"))
    if not co or not role:
        return None
    target = f"{co}_{role}".lower()
    for d in sorted(base.glob("*/"), key=lambda p: p.stat().st_mtime,
                    reverse=True):
        if d.is_dir() and d.name.lower().endswith(target):
            return d
    return None


def render_tailor_action_row(job: dict, key_prefix: str,
                              tracker_data: dict, tracker_path):
    """Render the 3-button action strip for a job: Tailor · Open · Apply.

    Behaviour:
      - 🔗 Open posting: link button to job["url"].
      - ✨ Tailor: spawns jd_tailor.py in background. Stores (job_id, run_id)
        in session_state so subsequent rerenders can detect completion and
        surface the drawer below the row.
      - ✅ Mark applied: stamps date_applied=today, status=Applied, and
        writes the tracker. Closes the loop without leaving the page.

    The drawer (in-page tailor preview + copy buttons) is rendered by
    render_tailor_drawer() — which the caller invokes once per page after
    the action rows so multiple Tailor clicks queue up correctly.
    """
    job_id = job.get("id", "")
    url = job.get("url", "")
    has_draft = bool(_find_application_folder(job))  # polished deliverable?

    btn_url, btn_tailor, btn_apply = st.columns(3)
    with btn_url:
        if url:
            st.link_button("🔗 Open posting", url, width='stretch')
        else:
            st.button("🔗 (no URL)", disabled=True, width='stretch',
                       key=f"{key_prefix}_nourl_{job_id}")
    with btn_tailor:
        _tailor_label = "📄 View resume" if has_draft else "✨ Tailor resume"
        if st.button(_tailor_label, width='stretch',
                      key=f"{key_prefix}_tailor_{job_id}",
                      help="Generate the tailored resume + cover letter + "
                           "interview brief for this role — the agentic "
                           "pipeline (resume_agent.py, ~1–2 min, ~$0.40 on "
                           "Opus). The polished .docx appears below."):
            if not has_draft:
                # The ONE resume path: spawn the agentic generator (produces
                # the polished applications/<job>/ .docx + cover + brief).
                _cmd = [sys.executable,
                        str(ROOT / "automation" / "resume_agent.py"),
                        "--job-id", job_id, "--tier", _resume_tier()]
                _rec = scan_runner.start_run(f"resume_{job_id}", _cmd)
                st.session_state["_active_tailor_job_id"] = job_id
                st.session_state["_active_tailor_run_id"] = _rec.run_id
                st.toast(f"📄 Generating resume for {job.get('company', '')}…",
                         icon="🚀")
            else:
                # Deliverable exists — surface it in the drawer.
                st.session_state["_active_tailor_job_id"] = job_id
            st.rerun()
    with btn_apply:
        _applied = bool(job.get("date_applied"))
        if st.button("✅ Applied" if not _applied else "✅ (already)",
                      width='stretch',
                      type="primary" if (has_draft and not _applied) else "secondary",
                      disabled=_applied,
                      key=f"{key_prefix}_apply_{job_id}",
                      help="Stamp date_applied=today, status=Applied. "
                           "Closes the loop without leaving the page."):
            # Lost-update fix: don't write the stale cached `tracker_data`
            # dict (it clobbers concurrent edits from auto_promote / other
            # tabs). Re-read + mutate under the shared lock instead.
            from safe_json import mutate_json as _mj  # noqa: WPS433

            def _apply_one(t):
                for _tj in t.get("jobs", []):
                    if _tj.get("id") == job_id:
                        _tj["status"] = "Applied"
                        seed_followup(_tj, applied_on=date.today())
                        break
                return t

            _mj(tracker_path, _apply_one, default={"jobs": [], "meta": {}})
            load_tracker.clear()
            st.toast(f"✅ Marked {job.get('company', '')} as applied",
                      icon="🎯")
            st.rerun()


def render_tailor_drawer(jobs_list: list, tracker_data: dict, tracker_path):
    """If session_state has an active tailor target, render the drawer
    below the page's action rows. Reads the tailor run state via
    scan_runner; once finished AND a tailor doc exists, swaps from
    'in progress' to 'preview + copy' mode.

    Closes when user clicks 'Done' / 'Mark applied' / dismisses.
    """
    job_id = st.session_state.get("_active_tailor_job_id")
    if not job_id:
        return
    job = next((j for j in jobs_list if j.get("id") == job_id), None)
    if not job:
        # Job was removed from tracker — clear the drawer
        st.session_state.pop("_active_tailor_job_id", None)
        st.session_state.pop("_active_tailor_run_id", None)
        return

    folder = _find_application_folder(job)
    run_id = st.session_state.get("_active_tailor_run_id")

    # Job-id-scoped key suffix so the drawer can be re-entered for a
    # different role without Streamlit complaining about duplicate keys
    # (which would crash if two drawers ever rendered in the same run).
    _kk = job_id.replace("-", "_") if job_id else "unknown"
    with st.container(border=True):
        _hc1, _hc2 = st.columns([5, 1])
        _hc1.markdown(f"### ✨ Tailor — {job.get('company', '?')} · "
                       f"{(job.get('title') or '?')[:80]}")
        with _hc2:
            if st.button("✕ Close", width='stretch',
                          key=f"tailor_drawer_close_{_kk}",
                          help="Close the drawer. Tailor output stays "
                               "on disk for next time."):
                st.session_state.pop("_active_tailor_job_id", None)
                st.session_state.pop("_active_tailor_run_id", None)
                st.rerun()

        # Status check: if run_id is known and run is still running, show
        # the live log tail. Otherwise look for the doc on disk.
        if run_id and not folder:
            _status_path = scan_runner.RUNS_DIR / f"{run_id}.json"
            if _status_path.exists():
                _rec = scan_runner.refresh_state(_status_path)
                if _rec.get("state") == "running":
                    st.info("⏳ Resume generation is still running "
                            "(~1–2 min) — drawer auto-refreshes when ready.",
                            icon="🤖")
                    _log = scan_runner.tail_log(_rec.get("log_path", ""), 4000)
                    if _log:
                        st.code(_log[-2000:], language="text")
                    return
                if _rec.get("state") == "failed":
                    st.error("❌ Tailor run failed. See log:")
                    _log = scan_runner.tail_log(_rec.get("log_path", ""), 4000)
                    if _log:
                        st.code(_log[-2000:], language="text")
                    return

        if not folder:
            st.warning(
                "No resume generated yet. If a run just started, give it "
                "~1–2 min and the drawer refreshes. Otherwise hit "
                "✨ Tailor resume on the row to generate one.",
                icon="⏳",
            )
            return

        # Drawer content: the polished deliverable (resume .docx + cover +
        # interview brief) for this role — downloads, previews, apply actions.
        _r_docx = next((p for p in folder.glob("*.docx")
                        if not p.name.endswith("_cover.docx")), None)
        _r_pdf = next((p for p in folder.glob("*.pdf")
                       if not p.name.endswith("_cover.pdf")), None)
        _c_docx = next(iter(folder.glob("*_cover.docx")), None)
        _c_pdf = next(iter(folder.glob("*_cover.pdf")), None)
        _cover = next(iter(folder.glob("*_cover.md")), None)
        _brief = next(iter(folder.glob("*_interview_brief.md")), None)
        _valid = next(iter(folder.glob("*_validity_report.md")), None)
        st.caption(
            f"📂 `applications/{folder.name}/` · "
            f"{datetime.fromtimestamp(folder.stat().st_mtime).strftime('%b %d %H:%M')}"
        )

        _da, _db, _dc = st.columns([2, 2, 1])
        with _da:
            _url = job.get("url", "")
            if _url:
                st.link_button("🔗 Open application URL", _url,
                                width='stretch', type="primary")
        with _db:
            if not job.get("date_applied"):
                if st.button("✅ Mark applied",
                              width='stretch', type="primary",
                              key=f"drawer_apply_btn_{_kk}"):
                    # Lost-update fix: re-read + mutate under the shared lock
                    # rather than writing the stale cached `tracker_data`.
                    from safe_json import mutate_json as _mj  # noqa: WPS433

                    def _apply_one(t):
                        for _tj in t.get("jobs", []):
                            if _tj.get("id") == job_id:
                                _tj["status"] = "Applied"
                                seed_followup(_tj, applied_on=date.today())
                                break
                        return t

                    _mj(tracker_path, _apply_one,
                        default={"jobs": [], "meta": {}})
                    load_tracker.clear()
                    st.session_state.pop("_active_tailor_job_id", None)
                    st.session_state.pop("_active_tailor_run_id", None)
                    st.toast(f"✅ {job.get('company', '?')} marked applied",
                              icon="🎯")
                    st.rerun()
            else:
                st.caption(
                    f"Already applied {job.get('date_applied')}"
                )
        with _dc:
            if st.button("📄 Re-generate", width='stretch',
                          key=f"drawer_regen_{_kk}",
                          help="Re-run the agentic generator (overwrites the "
                               "current deliverable for this role)."):
                _cmd = [sys.executable,
                        str(ROOT / "automation" / "resume_agent.py"),
                        "--job-id", job_id, "--tier", _resume_tier()]
                _rec = scan_runner.start_run(f"resume_{job_id}", _cmd)
                st.session_state["_active_tailor_run_id"] = _rec.run_id
                st.toast("📄 Re-generating…", icon="🚀")
                st.rerun()

        _dq1, _dq2, _dq3, _dq4 = st.columns(4)
        if _r_docx:
            with _dq1, open(_r_docx, "rb") as _f:
                st.download_button("⬇ Resume .docx", _f.read(),
                                   file_name=_r_docx.name, width='stretch',
                                   key=f"drawer_dl_rdocx_{_kk}")
        if _r_pdf:
            with _dq2, open(_r_pdf, "rb") as _f:
                st.download_button("⬇ Resume .pdf", _f.read(),
                                   file_name=_r_pdf.name, width='stretch',
                                   key=f"drawer_dl_rpdf_{_kk}")
        if _c_docx:
            with _dq3, open(_c_docx, "rb") as _f:
                st.download_button("⬇ Cover .docx", _f.read(),
                                   file_name=_c_docx.name, width='stretch',
                                   key=f"drawer_dl_cdocx_{_kk}")
        if _c_pdf:
            with _dq4, open(_c_pdf, "rb") as _f:
                st.download_button("⬇ Cover .pdf", _f.read(),
                                   file_name=_c_pdf.name, width='stretch',
                                   key=f"drawer_dl_cpdf_{_kk}")
        if not (_r_pdf or _c_pdf):
            st.caption("ℹ️ PDFs not generated (needs MS Word or libreoffice). "
                       ".docx is the editable master — export PDF from Word.")

        if _cover:
            with st.expander("✉️ Cover letter preview", expanded=False):
                st.markdown(_cover.read_text(encoding="utf-8"))
        if _brief:
            with st.expander("🎤 Interview brief", expanded=False):
                st.markdown(_brief.read_text(encoding="utf-8"))
        if _valid:
            with st.expander("✅ Validity report — what was checked & changed",
                             expanded=False):
                st.markdown(_valid.read_text(encoding="utf-8"))


def run_inline_agent(slot, label, *, on_finish=None,
                     running_msg="Working… the UI stays responsive."):
    """Launch `cmd` in the BACKGROUND (scan_runner, detached) and render its
    output inline once it finishes — without freezing the Streamlit thread.

    Replaces the old blocking `subprocess.run(...)` pattern for the ad-hoc
    admin actions (score-single-URL, weekly report, jd_tailor). The run id is
    stashed in session_state under `_inline_run_{slot}`.

    Self-refresh: while the run is live, this calls st_autorefresh() with a
    slot-scoped key so the page re-enters every ~2.5s until the run settles —
    regardless of which page hosts the button. We do NOT rely on the page-wide
    autorefresh at the top of the script: on Streamlit ≥1.33 that's disabled
    in favour of the live-panel fragment, and the Admin page (weekly_report,
    jd_tailor) has no live panel at all, so without this self-refresh those
    results would never auto-appear. When st_autorefresh is unavailable (shim),
    we degrade to a manual 🔄 hint.

    Call this UNCONDITIONALLY on every render (not just on the button click):
    it no-ops when there's no run for `slot`, shows a live log tail while
    running, and renders the final output (via `on_finish(log_text, rec)` if
    given, else a plain code block) when finished.

    `on_finish` receives the full merged stdout+stderr log text and the run
    record dict; it owns all success rendering for that slot.
    """
    _key = f"_inline_run_{slot}"
    run_id = st.session_state.get(_key)
    if not run_id:
        return
    status_path = scan_runner.RUNS_DIR / f"{run_id}.json"
    if not status_path.exists():
        # Run record vanished (cleared outputs, etc.) — drop the slot.
        st.session_state.pop(_key, None)
        return
    rec = scan_runner.refresh_state(status_path)
    state = rec.get("state")
    log_text = scan_runner.tail_log(rec.get("log_path", ""), 50_000)
    if state == "running":
        st.info(f"⏳ {running_msg}", icon="🤖")
        if log_text:
            st.code(log_text[-2000:], language="text")
        # Drive our own refresh loop — see docstring for why the page-wide one
        # can't be relied on here. Slot-scoped key so two inline agents don't
        # share a counter.
        if _HAVE_AUTOREFRESH:
            st_autorefresh(interval=2500, key=f"_inline_refresh_{slot}")
        else:
            st.caption("Hit 🔄 Reload page in the sidebar to check progress.")
        return
    # Settled (finished | failed | stopped) — render once, then clear so a
    # later rerun doesn't keep re-showing a stale result.
    if state == "failed":
        st.error(f"❌ {label} failed (exit {rec.get('returncode')}).")
        if log_text:
            st.code(log_text[-3000:], language="text")
    elif on_finish is not None:
        on_finish(log_text, rec)
    else:
        st.code(log_text[-4000:] if log_text else "(no output)", language="text")
    st.session_state.pop(_key, None)


def start_inline_agent(slot, label, cmd):
    """Launch `cmd` detached and register it for run_inline_agent(slot)."""
    rec = scan_runner.start_run(label, cmd)
    st.session_state[f"_inline_run_{slot}"] = rec.run_id
    return rec


def _extract_pretty_json(text):
    """Pull a top-level `json.dumps(indent=2)` object out of a mixed log.

    score_url.py --json-only prints pretty-printed JSON to stdout while
    diagnostics go to stderr; start_run merges both streams into one log, so
    we can't just json.loads() the whole thing. A naive brace-counter breaks
    when a free-text field (summary, reasons — LLM output) contains a literal
    `{` or `}`. Instead we exploit pretty-print layout: with indent=2 the
    OUTER braces are the only ones at column 0 of a physical line (in-string
    newlines are escaped to `\\n`, so no string content ever starts a line).
    Grab from the first line that is exactly "{" through the next line that
    starts with "}" and parse that slice. Returns the dict, or None.
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if start is None:
            if ln.rstrip() == "{":
                start = i
        elif ln.startswith("}"):
            candidate = "\n".join(lines[start:i + 1])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                start = None  # not valid — keep scanning for another block
    return None


CRM_STALE_DAYS = 14  # past this, contacts get flagged as "nudge-worthy"
CRM_DEAD_DAYS = 35   # past this, contacts get flagged as "probably cold"
CRM_TERMINAL_STATUSES = {"Do_Not_Contact", "Past_Rep", "On_Hold"}


def outreach_digest(crm: dict, today_date: date | None = None) -> dict:
    """Score each CRM contact by staleness + priority. Returns:
      {"never_contacted": [contacts],
       "active":          [(days_since, contact)],
       "stale":           [(days_since, contact)],
       "cold":            [(days_since, contact)],
       "weekly_sent":     count sent in the last 7 days}
    """
    today_date = today_date or date.today()
    week_ago = today_date - timedelta(days=7)
    out = {"never_contacted": [], "active": [], "stale": [], "cold": [],
           "weekly_sent": 0}

    # Combine recruiters + alumni as "contacts" — treat uniformly
    contacts = []
    for r in crm.get("recruiters", []):
        contacts.append({**r, "_kind": "recruiter"})
    for a in crm.get("alumni_warm_intros", []):
        contacts.append({**a, "_kind": "alumni"})

    for c in contacts:
        if c.get("status") in CRM_TERMINAL_STATUSES:
            continue
        last = parse_date(c.get("last_touchpoint"))
        if last is None:
            out["never_contacted"].append(c)
            continue
        if last >= week_ago:
            out["weekly_sent"] += 1
        days = (today_date - last).days
        if days <= CRM_STALE_DAYS:
            out["active"].append((days, c))
        elif days <= CRM_DEAD_DAYS:
            out["stale"].append((days, c))
        else:
            out["cold"].append((days, c))

    # Count this-week touchpoints from outreach_log too (structured log)
    for entry in crm.get("outreach_log") or []:
        d = parse_date(entry.get("date"))
        if d and d >= week_ago:
            out["weekly_sent"] += 1

    # Sort by priority (High > Medium > Low), then days-since desc for stale
    prio_rank = {"High": 0, "Medium": 1, "Low": 2}
    out["never_contacted"].sort(key=lambda c: prio_rank.get(c.get("priority"), 3))
    out["active"].sort(key=lambda t: -t[0])
    out["stale"].sort(key=lambda t: -t[0])
    out["cold"].sort(key=lambda t: -t[0])
    return out


def render_template(body: str, contact: dict) -> str:
    """Substitute {{placeholder}} variables in a CRM outreach template."""
    out = body
    subs = {
        "{{name}}": (contact.get("contacts") or [{}])[0].get("name", "") if contact.get("_kind") == "recruiter" else contact.get("name", ""),
        "{{firm}}": contact.get("firm", "") or contact.get("company_targeted", ""),
        "{{coverage}}": contact.get("coverage", "") or contact.get("notes", ""),
        "{{next_action}}": contact.get("next_action", ""),
    }
    for k, v in subs.items():
        out = out.replace(k, str(v or ""))
    return out


_CRM_STOPWORDS = {"bank", "financial", "canadian", "canada", "global", "group",
                    "capital", "management", "investments", "pension", "plan",
                    "corp", "inc", "ltd", "company", "the", "and"}


_GTA_AREAS = [
    ("Toronto", ("toronto", "north york", "scarborough", "etobicoke", "east york",
                  "york, on", "downtown")),
    ("Mississauga", ("mississauga",)),
    ("Markham", ("markham", "unionville")),
    ("Vaughan", ("vaughan", "concord", "woodbridge", "thornhill")),
    ("Brampton", ("brampton",)),
    ("Oakville", ("oakville",)),
    ("Burlington", ("burlington",)),
    ("Milton", ("milton",)),
    ("Richmond Hill", ("richmond hill",)),
    ("Durham", ("pickering", "ajax", "whitby", "oshawa")),
    ("York Region", ("aurora", "newmarket", "stouffville", "king city")),
    ("Waterloo/Kitchener", ("waterloo", "kitchener", "cambridge")),
    ("Remote Canada", ("remote - canada", "canada - remote", "remote canada",
                        "remote, canada")),
    ("Ottawa", ("ottawa",)),
    ("Montreal", ("montreal", "montréal")),
]


def gta_area_for(location: str | None) -> str:
    """Classify a location string into a GTA area bucket. Returns '—' if unknown.
    Used for Kanban column + filter so Saber can slice newly-unblocked
    non-Toronto GTA roles (Mississauga, Markham etc.)."""
    if not location:
        return "—"
    loc = str(location).lower()
    for label, tokens in _GTA_AREAS:
        if any(tok in loc for tok in tokens):
            return label
    # Last resort — anything with "on" or "ontario" is likely GTA-adjacent
    if "ontario" in loc or ", on" in loc or " on," in loc or loc.endswith(", on"):
        return "Other Ontario"
    return "—"


def crm_contacts_at_company(crm: dict, company: str) -> list[dict]:
    """Match CRM recruiters + alumni entries to a given company name.
    Bidirectional token-overlap: 'Scotiabank' matches 'Scotia' (prefix) and
    'Scotia' matches 'Scotiabank'. Covers abbreviations + full legal names."""
    if not company:
        return []
    co_tokens = [t for t in re.split(r"[^a-z0-9]+", company.lower())
                 if len(t) >= 4 and t not in _CRM_STOPWORDS]
    if not co_tokens:
        return []

    def _match(hay: str) -> bool:
        hay_tokens = [h for h in re.split(r"[^a-z0-9]+", hay.lower()) if len(h) >= 4]
        for co_tok in co_tokens:
            for h in hay_tokens:
                # Bidirectional prefix match — 'scotia' ⇔ 'scotiabank'
                if co_tok == h or co_tok.startswith(h) or h.startswith(co_tok):
                    return True
        return False

    matches = []
    for rec in (crm or {}).get("recruiters", []):
        hay = (rec.get("firm", "") + " " + rec.get("coverage", "") + " "
               + rec.get("notes", ""))
        if _match(hay):
            matches.append({**rec, "_kind": "recruiter"})
    for al in (crm or {}).get("alumni_warm_intros", []):
        hay = (al.get("company_targeted", "") + " "
               + al.get("current_firm", "") + " "
               + al.get("notes", ""))
        if _match(hay):
            matches.append({**al, "_kind": "alumni"})
    return matches


def fmt_dt(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def human_elapsed(started_iso: str | None, end_iso: str | None = None) -> str:
    if not started_iso:
        return "—"
    try:
        start = datetime.fromisoformat(started_iso)
    except Exception:
        return "—"
    end = datetime.fromisoformat(end_iso) if end_iso else datetime.now()
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def hours_since_posted(posted_date: str | None) -> float | None:
    """Return hours elapsed since posted_date. None if unparseable.
    Accepts 'YYYY-MM-DD' (treated as UTC midnight) or any ISO8601 string.

    Both sides of the subtraction are kept tz-aware. Earlier this naively
    stripped tz and compared to local-naive datetime.now() — on a Toronto
    laptop that shifted every elapsed-hours value by 4-5 hours, breaking
    the 48-hour urgent-role threshold."""
    if not posted_date:
        return None
    s = str(posted_date).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None
    # Date-only or naive ISO — treat as UTC. Don't silently coerce to local;
    # job-board timestamps are almost always UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def freshness_badge(posted_date: str | None, found_at: str | None) -> str:
    """Return a short badge combining posted/found freshness.
    Emoji indicates 'how hot is this role right now':
      🔥  posted in last 48h
      🟢  posted in last 7d
      🟡  posted 8-21d ago
      ⚪  >21d or unknown
    """
    label_post = ""
    label_found = ""
    now = date.today()
    if posted_date:
        try:
            d = datetime.fromisoformat(str(posted_date).replace("Z", "")).date()
            days = (now - d).days
            if days <= 2:
                label_post = f"🔥 posted {days}d ago"
            elif days <= 7:
                label_post = f"🟢 posted {days}d ago"
            elif days <= 21:
                label_post = f"🟡 posted {days}d ago"
            else:
                label_post = f"⚪ posted {days}d ago"
        except Exception:
            pass
    if found_at:
        try:
            d = datetime.fromisoformat(str(found_at)).date()
            days = (now - d).days
            label_found = "found today" if days == 0 else f"found {days}d ago"
        except Exception:
            pass
    parts = [p for p in (label_post, label_found) if p]
    return " · ".join(parts) if parts else "—"


def load_morning_brief() -> dict | None:
    """Read the most recent brief_YYYYMMDD.json. Returns None if missing."""
    files = sorted(OUT_DIR.glob("brief_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def load_scorer_progress() -> dict | None:
    """Read outputs/fit_scorer_progress.json if present. Returns None if missing.

    A progress file with state='running' but an `updated_at` older than
    ~5 minutes is treated as STALE — that usually means the scorer process
    was killed (terminal closed, crash, OOM) without calling progress_end().
    Stale files get rewritten to state='stale' so the banner clears and
    future dashboards don't keep showing a phantom 'Scoring in progress'.
    """
    p = OUT_DIR / "fit_scorer_progress.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Freshness guard. Only matters when state is "running" — finished/failed
    # states are permanent records.
    if data.get("state") == "running":
        updated = data.get("updated_at") or data.get("started_at")
        stale = False
        if not updated:
            stale = True
        else:
            try:
                # Stored as ISO with trailing 'Z'; strip it for fromisoformat.
                u = updated.rstrip("Z")
                dt = datetime.fromisoformat(u)
                # updated_at is UTC; compare in UTC.
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                if (now_utc - dt).total_seconds() > 300:
                    stale = True
            except Exception:
                stale = True

        if stale:
            # Also verify the producer PID (if we have one) isn't alive.
            # The progress file doesn't carry a PID directly, but scan_runner
            # tracks active runs. If there are NO running fit_scorer runs,
            # the progress file is definitively orphaned.
            try:
                _active = [r for r in scan_runner.active_runs()
                            if "fit_scorer" in (r.get("label") or "")]
            except Exception:
                _active = []
            if not _active:
                data["state"] = "stale"
                data["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
    return data


def _fmt_eta(secs: float | None) -> str:
    if not secs or secs <= 0:
        return "—"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def _render_scorer_status(container=None, scorer_running: bool = False) -> None:
    """Always-visible operational summary of the LAST scoring run — the
    'how did scoring go' table for the ② Score page's ④ Scoring card.

    Distinct from `render_scorer_progress` (which is the LIVE in-flight panel,
    only shown while state=='running'). This reads the persisted
    `fit_scorer_progress.json` (counters survive past the run) + the latest
    `*_scored.json` (stage counts, scored_at, fatal api_error) and shows:
    total input · triaged · scored · cached(free) · new(paid) · errors ·
    model · last-run age, plus a fatal-error warning and a Logs expander.

    Sources are all on-disk; degrades to a single caption when nothing has run.
    """
    tgt = container if container is not None else st

    # While a run is live the LIVE panel above owns the numbers — don't show a
    # stale post-run snapshot underneath it.
    if scorer_running:
        tgt.caption("🟡 Scoring in progress — live counts in the panel above.")
        return

    prog = load_scorer_progress() or {}
    # Latest scored artifact (worklist_scored.json or scan_*_scored.json).
    _scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
    sc = {}
    scored_name = None
    if _scored_files:
        scored_name = _scored_files[0].name
        try:
            sc = json.loads(_scored_files[0].read_text(encoding="utf-8"))
        except Exception:
            sc = {}

    if not prog and not sc:
        tgt.caption("No scoring run yet — run the scorer from the launch card.")
        return

    total_input = sc.get("total_input")
    triaged = sc.get("stage1_passed")
    scored = sc.get("stage2_scored", prog.get("current"))
    cached = prog.get("cache_hits")
    cost = prog.get("cost") or {}
    new_paid = cost.get("llm_calls")
    if new_paid is None and scored is not None and cached is not None:
        new_paid = max(scored - cached, 0)
    errors = prog.get("errors")

    # Model: prefer the model(s) actually used this run (per_model in the cost
    # block), else the configured constant. Strip the date suffix for display.
    model = None
    per_model = cost.get("per_model") or {}
    if per_model:
        model = max(per_model, key=lambda m: (per_model[m] or {}).get("calls", 0))
    if not model:
        try:
            from fit_scorer import MODEL as _fs_model  # type: ignore
            model = _fs_model
        except Exception:
            model = None
    model_disp = None
    if model:
        # claude-haiku-4-5-20251001 -> haiku-4-5
        m = model.replace("claude-", "")
        m = "-".join(part for part in m.split("-") if not part.isdigit() or len(part) < 5)
        model_disp = m

    # Last-run age from scored_at (ISO, possibly trailing 'Z').
    last_age_h = None
    _sat = sc.get("scored_at")
    if _sat:
        try:
            _dt = datetime.fromisoformat(_sat.rstrip("Z"))
            last_age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - _dt).total_seconds() / 3600.0
        except Exception:
            last_age_h = None

    def _v(x):
        return f"{x:,}" if isinstance(x, int) else (x if x is not None else "—")

    tgt.markdown("**📊 Last scoring run**")
    _r1 = tgt.columns(4)
    _r1[0].metric("Input", _v(total_input))
    _r1[1].metric("Triaged", _v(triaged))
    _r1[2].metric("Scored", _v(scored))
    _r1[3].metric("Errors", _v(errors))
    _r2 = tgt.columns(4)
    _r2[0].metric("Cached (free)", _v(cached))
    _r2[1].metric("New (paid)", _v(new_paid))
    _r2[2].metric("Model", model_disp or "—")
    _r2[3].metric("Last run", _humanize_age_h(last_age_h))

    if sc.get("api_error"):
        tgt.warning(f"⚠️ Last run hit a fatal API error: {sc['api_error']}", icon="⚠️")

    # Logs: tail the most recent score/pipeline run.
    with tgt.expander("📜 Scoring logs (latest run)", expanded=False):
        try:
            _runs = scan_runner.list_runs(limit=20)
            _score_run = next(
                (r for r in _runs
                 if any(k in (r.get("label") or "").lower()
                        for k in ("score", "pipeline", "fit_scorer"))),
                None,
            )
            if _score_run and _score_run.get("log_path"):
                st.caption(f"`{_score_run.get('label', '?')}` · "
                           f"{_score_run.get('state', '?')} · "
                           f"{human_elapsed(_score_run.get('started_at'), _score_run.get('finished_at'))}")
                _tail = scan_runner.tail_log(_score_run["log_path"], max_bytes=8000)
                st.code(_tail or "(empty log)", language="text")
            else:
                st.caption("No score/pipeline run log found.")
        except Exception as _e:  # noqa: BLE001
            st.caption(f"Logs unavailable: {_e}")


def render_scorer_progress(container=None, title: str = "🤖 Scoring in progress"):
    """Render a live progress bar + ETA + recent candidates table for the fit scorer.

    Only renders when state=='running' (live). Finished/failed/stale progress
    files are skipped so the dashboard doesn't falsely claim scoring is in
    progress when the scraper (or nothing at all) is running.
    """
    prog = load_scorer_progress()
    if not prog:
        return False
    state = prog.get("state", "idle")
    if state != "running":
        return False
    target = container or st
    cur = prog.get("current", 0)
    total = prog.get("total", 0) or 1
    frac = min(1.0, cur / total)

    with target.container(border=True):
        st.markdown(f"### {title}")
        cost = prog.get("cost") or {}
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Progress", f"{cur}/{total}", f"{frac*100:.0f}%")
        c2.metric("Elapsed", _fmt_eta(prog.get("elapsed_sec")))
        c3.metric("ETA", _fmt_eta(prog.get("eta_sec")))
        c4.metric("Cache hits", prog.get("cache_hits", 0))
        c5.metric("Est. cost (USD)",
                  f"${cost.get('estimated_cost_usd', 0):.3f}" if cost else "—",
                  f"{cost.get('llm_calls', 0)} calls" if cost else None)
        st.progress(frac, text=f"Scored {cur} of {total} candidates · scan=`{prog.get('scan')}`")

        # Verdict breakdown so far
        vc = prog.get("verdict_counts") or {}
        if vc:
            apply_n = vc.get("apply_now", 0)
            tailor_n = vc.get("tailor_and_apply", 0)
            watch_n = vc.get("watch", 0)
            skip_n = vc.get("skip", 0)
            err_n = vc.get("error", 0) + prog.get("errors", 0)
            bc1, bc2, bc3, bc4, bc5 = st.columns(5)
            bc1.metric("apply_now", apply_n)
            bc2.metric("tailor_and_apply", tailor_n)
            bc3.metric("watch", watch_n)
            bc4.metric("skip", skip_n)
            bc5.metric("errors", err_n, delta_color="inverse")

        # Best-so-far vs most-recent tabs. The "recent" stream during a real
        # run is overwhelmingly skips (the firehose feeding the scorer) — so
        # showing it on its own falsely suggests the run is producing nothing.
        # The Best-so-far tab reads worklist_scored.json mid-flight (it's
        # written incrementally) and shows the top 5 by fit_score, which is
        # what the user actually wants while watching the bar fill.
        recent = prog.get("recent") or []
        _best_rows: list[dict] = []
        try:
            _wls_p = OUT_DIR / "worklist_scored.json"
            if _wls_p.exists():
                _wls_data = json.loads(_wls_p.read_text(encoding="utf-8"))
                _scored_only = [
                    r for r in (_wls_data.get("results") or [])
                    if isinstance(r.get("fit"), dict)
                    and r.get("fit", {}).get("fit_score") is not None
                ]
                _scored_only.sort(
                    key=lambda r: r.get("fit", {}).get("fit_score") or 0,
                    reverse=True,
                )
                for r in _scored_only[:5]:
                    f = r.get("fit") or {}
                    _best_rows.append({
                        "company": r.get("company", ""),
                        "title": (r.get("title") or "")[:80],
                        "verdict": f.get("fit_verdict", ""),
                        "score": f.get("fit_score", ""),
                        "cache": "💾" if r.get("from_cache") else "🌐",
                    })
        except Exception:
            _best_rows = []

        if _best_rows or recent:
            _t_best, _t_recent = st.tabs(["⭐ Best so far", "🕐 Most recent"])
            with _t_best:
                if _best_rows:
                    st.caption("**Top 5 by fit_score** (live, from "
                               "worklist_scored.json)")
                    st.dataframe(
                        pd.DataFrame(_best_rows),
                        hide_index=True, width='stretch',
                        height=min(40 + 36 * len(_best_rows), 300),
                    )
                else:
                    st.caption("No scored rows yet — first batch lands shortly.")
            with _t_recent:
                if recent:
                    st.caption("**Most recent candidates** (newest last)")
                    rows = []
                    for r in recent:
                        rows.append({
                            "company": r.get("company", ""),
                            "title": r.get("title", ""),
                            "verdict": r.get("verdict", ""),
                            "score": r.get("score", ""),
                            "cache": "💾" if r.get("from_cache") else "🌐",
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True,
                                 width='stretch',
                                 height=min(40 + 36 * len(rows), 300))
                else:
                    st.caption("No recent candidates streamed yet.")

        # Per-model cost breakdown
        per_model = (cost or {}).get("per_model") or {}
        if per_model:
            with st.expander(f"💰 Token/cost breakdown ({cost.get('llm_calls', 0)} LLM calls, "
                             f"${cost.get('estimated_cost_usd', 0):.4f} est)"):
                rows = []
                for model, m in per_model.items():
                    rows.append({
                        "model": model,
                        "calls": m.get("calls", 0),
                        "input_tokens": m.get("in_tokens", 0),
                        "output_tokens": m.get("out_tokens", 0),
                        "est_cost_usd": round(m.get("cost_usd", 0), 4),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
                st.caption(
                    f"Cache reads: {cost.get('cache_read_tokens', 0):,} tokens · "
                    f"Cache writes: {cost.get('cache_create_tokens', 0):,} tokens. "
                    f"Pricing from Anthropic public rates — invoice is authoritative."
                )

        # Live log tail. The structured progress JSON shows metrics but the
        # user wants to see actual stdout — preflight messages, cost-guard
        # heartbeats, "scored 140/657" lines. Two paths to the log file:
        #   1. scan_runner has an active pipeline/fit_scorer run → use its
        #      registered log_path (the canonical case).
        #   2. The producer was launched outside scan_runner (e.g., manual
        #      relaunch from a shell with API key sourced) → fall back to
        #      the most recently modified .log in outputs/runs/. While the
        #      scorer is actively writing progress, that log file's mtime
        #      is also being touched, so "newest log within 2 min" is a
        #      reliable proxy.
        _log_path: str | None = None
        _log_label = ""
        try:
            _active_pipe_run = next(
                (r for r in scan_runner.active_runs()
                 if "pipeline" in (r.get("label") or "")
                 or "fit_scorer" in (r.get("label") or "")),
                None,
            )
        except Exception:
            _active_pipe_run = None
        if _active_pipe_run and _active_pipe_run.get("log_path"):
            _log_path = _active_pipe_run["log_path"]
            _log_label = "scan_runner"
        else:
            try:
                _runs_dir = OUT_DIR / "runs"
                _candidates = sorted(
                    _runs_dir.glob("*.log"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if _candidates:
                    _newest = _candidates[0]
                    _age_s = datetime.now().timestamp() - _newest.stat().st_mtime
                    if _age_s < 120:
                        _log_path = str(_newest)
                        _log_label = "fallback (newest *.log)"
            except Exception:
                pass

        if _log_path:
            with st.expander("📜 Live log tail (last ~30 lines)", expanded=True):
                _log_text = scan_runner.tail_log(_log_path, max_bytes=8000)
                _lines = _log_text.splitlines()[-30:] if _log_text else []
                if _lines:
                    st.code("\n".join(_lines), language="text")
                else:
                    st.caption("(no log output yet)")
                st.caption(
                    f"📁 `{_log_path}` · {_log_label} · refreshes every 3s"
                )
        else:
            with st.expander("📜 Live log tail", expanded=False):
                st.caption(
                    "(no active pipeline run registered with scan_runner "
                    "and no recent .log file in outputs/runs/)"
                )

        status_caption = {
            "running": f"🟡 Running · updated {prog.get('updated_at', '—')}",
            "finished": f"🟢 Finished at {prog.get('finished_at', '—')}",
            "failed": f"🔴 Failed at {prog.get('finished_at', '—')}",
        }.get(state, f"State: {state}")
        st.caption(status_caption)
    return state == "running"


def _resolve_pipeline_staleness(data: dict, path: Path) -> dict:
    """Rewrite a pipeline status that claims `state=running` but is obviously
    orphaned. Mirror of fit_scorer_progress.json's stale-detection logic.

    A pipeline is stale when:
      - state is 'running'
      - AND file hasn't been touched in >10 minutes (pipelines heartbeat
        via _write_status after every stage transition)
      - AND no scan_runner job whose label contains 'pipeline' is alive

    When all three are true, the producer is dead — the process either
    crashed before hitting the try/finally guard, was kill-treed, or the
    machine was rebooted. We flip state to 'stale' in-place so the UI
    stops showing a phantom 'pipeline running' banner forever."""
    if data.get("state") != "running":
        return data
    try:
        age_s = datetime.now().timestamp() - path.stat().st_mtime
    except Exception:
        return data
    if age_s < 600:  # <10 min: still plausibly alive, don't touch
        return data
    try:
        alive = any("pipeline" in (r.get("label") or "")
                     for r in scan_runner.active_runs())
    except Exception:
        alive = False
    if alive:
        return data
    # Orphan. Rewrite the file.
    data["state"] = "stale"
    data["finished_at"] = datetime.now().isoformat(timespec="seconds")
    data["stale_reason"] = (
        f"No active pipeline subprocess and status file idle for "
        f"{int(age_s/60)} minutes."
    )
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    return data


def latest_pipeline_status() -> dict | None:
    if not PIPELINE_DIR.exists():
        return None
    files = sorted(PIPELINE_DIR.glob("pipeline_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None
    return _resolve_pipeline_staleness(data, files[0])


def render_gmail_trash_panel(container=None,
                              fresh_window_s: int = 3600) -> bool:
    """Render the 'Gmail fetch result' panel for a recent scan_gmail_*.json.

    Surfaces three things in one place:
      1. Harvest diagnostics (rows parsed, alerts seen, parse misses)
      2. Score-Gmail-rows-now CTA (so the user can act on freshly-pulled rows
         without bouncing to the Pipeline tab and re-typing the filename)
      3. Trash cleanup (move source emails to Gmail Trash) — only after rows
         have been parsed; only on un-trashed UIDs.

    Scoping rule (avoid stale prompts): only auto-render when the source
    scan was created within `fresh_window_s` seconds (default 1h). Older
    un-trashed scans are silently skipped — they're available from
    Admin/Pipeline manage views.

    Returns True if it rendered (UI shifted), False otherwise.
    """
    target = container or st
    files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return False
    latest = files[0]
    age_s = datetime.now().timestamp() - latest.stat().st_mtime
    if age_s > fresh_window_s:
        return False
    try:
        env = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return False

    rows = env.get("results") or []
    n_rows = len(rows)
    diag = env.get("harvest_diagnostics") or {}
    alerts = env.get("gmail_alerts") or {}
    # Trash the BROADER processed set (every alert we parsed + made a
    # keep/drop decision on, incl. all-US ones whose every job was
    # geo-dropped). Falls back to contributing_uids for envelopes written
    # before processed_uids existed. _contributing_uids kept for the
    # "produced matches vs all-filtered" caption below.
    _contributing_uids = alerts.get("contributing_uids") or []
    uids = alerts.get("processed_uids") or _contributing_uids
    _uids_filtered_only = max(len(uids) - len(_contributing_uids), 0)

    # Has the worklist been scored AFTER this Gmail fetch landed?
    # Old logic checked for a dedicated scan_gmail_<stamp>_scored.json,
    # but post-worklist-redesign, scoring writes worklist_scored.json
    # (the contract pool — what auto_promote and Today's queue read).
    # If worklist_scored.json's mtime > this Gmail scan's mtime, the
    # 6 new Gmail rows have ridden along into the scored pool.
    worklist_scored_path = OUT_DIR / "worklist_scored.json"
    if worklist_scored_path.exists():
        already_scored = (
            worklist_scored_path.stat().st_mtime > latest.stat().st_mtime
        )
    else:
        already_scored = False

    age_min = int(age_s / 60)
    age_label = f"{age_min}m ago" if age_min < 60 else f"{age_min // 60}h ago"

    with target.container(border=True):
        # ── HEADER ───────────────────────────────────────────────────────
        st.markdown(
            f"#### 📬 Gmail fetch · `{latest.name}` · {age_label}"
        )

        # ── DIAGNOSTICS ROW ──────────────────────────────────────────────
        if diag:
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Alerts seen",
                       diag.get("linkedin_alerts_seen", "—"),
                       help=f"LinkedIn alert emails matched within "
                            f"{diag.get('days_window', '?')}-day window")
            d2.metric("Digests parsed",
                       diag.get("digests_with_rows", "—"),
                       delta=(f"-{diag['digests_without_rows']} miss"
                              if diag.get("digests_without_rows", 0) else None),
                       delta_color="inverse",
                       help="Alerts that yielded ≥1 job row. 'Miss' = "
                            "digest matched but parser extracted nothing.")
            d3.metric("Rows parsed",
                       # Envelope key is `rows_parsed` (len of raw_rows before
                       # geo/dedup). The old `rows_after_parse` lookup never
                       # matched, so this silently showed n_rows (KEPT, often
                       # 0 for all-US fetches) — making a 18-row all-US fetch
                       # read "Rows parsed: 0". Fall back old→new→n_rows.
                       diag.get("rows_parsed",
                                diag.get("rows_after_parse", n_rows)),
                       help="Total job rows extracted before geo filter / dedup")
            # Build the 'New rows' delta from all three drop sources so
            # the user sees exactly where the funnel is leaking.
            _drop_parts = []
            if diag.get("rows_dropped_tracker_dedup", 0):
                _drop_parts.append(f"{diag['rows_dropped_tracker_dedup']} tracker")
            if diag.get("rows_dropped_scan_url", 0):
                _drop_parts.append(f"{diag['rows_dropped_scan_url']} scan-URL")
            if diag.get("rows_dropped_scan_ct", 0):
                _drop_parts.append(f"{diag['rows_dropped_scan_ct']} scan-co/title")
            _delta_str = f"-{' / '.join(_drop_parts)}" if _drop_parts else None
            _src = diag.get("scan_dedup_sources") or {}
            _help = (
                "After dropping rows already in tracker AND rows already "
                "present in the latest web scan + recent Gmail scans."
            )
            if _src:
                _help += (
                    f" Cross-scan index: "
                    f"{_src.get('rows_indexed', 0)} row(s) from "
                    f"{_src.get('web_scan', 0)} web scan + "
                    f"{_src.get('gmail_scans', 0)} prior Gmail scan(s)."
                )
            d4.metric("New rows",
                       n_rows,
                       delta=_delta_str,
                       delta_color="inverse",
                       help=_help)
        else:
            st.caption(f"📊 {n_rows} row(s) extracted")

        # ── ZERO-ROW DIAGNOSTIC ──────────────────────────────────────────
        if n_rows == 0:
            if diag.get("linkedin_alerts_seen", 0) == 0:
                st.info(
                    "🔍 **No LinkedIn alert emails found** in the search window. "
                    "Either no alerts arrived in this period, or your "
                    "subscription isn't active. Verify by visiting Gmail "
                    "and searching `from:jobalerts-noreply@linkedin.com`.",
                    icon="📭",
                )
            elif diag.get("digests_without_rows", 0) > 0:
                st.warning(
                    f"⚠️ **Parser miss** — {diag['linkedin_alerts_seen']} "
                    "LinkedIn alert(s) arrived but the parser extracted "
                    "**0 job rows** from them. Likely a digest layout we "
                    "don't handle yet. Check `automation/gmail_diagnose.py` "
                    "or open one of the alerts in Gmail to see what changed.",
                    icon="🐛",
                )
            else:
                tracker_drops = diag.get("rows_dropped_tracker_dedup", 0)
                scan_url_drops = diag.get("rows_dropped_scan_url", 0)
                scan_ct_drops = diag.get("rows_dropped_scan_ct", 0)
                total_drops = tracker_drops + scan_url_drops + scan_ct_drops
                if total_drops:
                    parts = []
                    if tracker_drops:
                        parts.append(f"{tracker_drops} in tracker")
                    if scan_url_drops:
                        parts.append(f"{scan_url_drops} URL match w/ recent scans")
                    if scan_ct_drops:
                        parts.append(f"{scan_ct_drops} (company,title) match w/ recent scans")
                    st.info(
                        f"All {total_drops} parsed row(s) were already known "
                        f"({', '.join(parts)}). Nothing new to score.",
                        icon="✅",
                    )
            # GEO-DROP / all-US case: alerts WERE parsed, but every job was
            # outside the GTA (e.g. Charlotte, NYC). None of the branches above
            # match (alerts_seen>0, digests_without_rows=0, dedup drops=0), so
            # historically this fell straight to `return True` with no message
            # and — the real bug — no delete option. processed_uids now carries
            # these all-US alert UIDs, so surface a diagnostic AND offer to
            # trash them (self-contained here; the main path's preview/score
            # UI below assumes kept rows exist).
            _geo_dropped = diag.get("rows_dropped_location", 0)
            if _geo_dropped:
                _ex = diag.get("dropped_location_examples") or []
                st.info(
                    f"📍 {diag.get('linkedin_alerts_seen', 0)} alert(s) seen — "
                    f"all {_geo_dropped} job(s) were outside the GTA"
                    + (f" (e.g. {', '.join(_ex[:3])})" if _ex else "")
                    + ". Nothing new to score, but you can clear these "
                    "alerts below.",
                    icon="📍",
                )
            if uids and not alerts.get("deleted"):
                st.markdown("**Clean up:**")
                _zc1, _zc2 = st.columns(2)
                with _zc1:
                    _zero_trash = st.button(
                        f"🗑 Move {len(uids)} alert(s) to Trash",
                        width='stretch', key=f"gmail_trash_zero_{latest.stem}",
                        help="Moves these alert emails to [Gmail]/Trash "
                             "(reversible, auto-purges after 30 days). These "
                             "are all-US alerts that produced no GTA match.",
                    )
                with _zc2:
                    _zero_hide = st.button(
                        "🙈 Hide", width='stretch',
                        key=f"gmail_trash_zero_hide_{latest.stem}",
                        help="Dismiss without deleting; next fetch resets.",
                    )
                if _zero_trash:
                    try:
                        sys.path.insert(0, str(ROOT / "automation"))
                        import gmail_reader as _gr  # type: ignore
                        with st.spinner(f"Moving {len(uids)} alert(s) to Trash…"):
                            res = _gr.delete_messages(uids)
                    except Exception as e:
                        st.error(f"Delete failed before IMAP call: {e}")
                        return True
                    env.setdefault("gmail_alerts", {})
                    env["gmail_alerts"]["deleted"] = True
                    env["gmail_alerts"]["deleted_at"] = \
                        datetime.now().isoformat(timespec="seconds")
                    env["gmail_alerts"]["delete_result"] = {
                        "moved": res.moved, "failed": res.failed,
                        "errors": list(res.errors or [])[:10]}
                    try:
                        latest.write_text(json.dumps(env, indent=2,
                                          ensure_ascii=False), encoding="utf-8")
                    except Exception as e:
                        st.warning(f"Trash succeeded but persisting failed: {e}")
                    if res.failed == 0:
                        st.success(f"✅ Moved {res.moved} alert(s) to Gmail "
                                   "Trash. They'll auto-purge after 30 days.")
                    else:
                        st.warning(f"Moved {res.moved}, failed {res.failed}. "
                                   f"Errors: {res.errors[:3]}")
                    st.rerun()
                if _zero_hide:
                    env.setdefault("gmail_alerts", {})
                    env["gmail_alerts"]["deleted"] = True
                    env["gmail_alerts"]["delete_result"] = {
                        "moved": 0, "failed": 0,
                        "errors": ["User dismissed without deleting."]}
                    env["gmail_alerts"]["deleted_at"] = \
                        datetime.now().isoformat(timespec="seconds")
                    latest.write_text(json.dumps(env, indent=2,
                                      ensure_ascii=False), encoding="utf-8")
                    st.rerun()
            elif alerts.get("deleted"):
                dr = alerts.get("delete_result") or {}
                st.caption(f"✅ {dr.get('moved', 0)} alert(s) already moved "
                           "to Trash.")
            return True

        # ── ROW PREVIEW ──────────────────────────────────────────────────
        with st.expander(
            f"🔍 Preview the {n_rows} parsed row(s)",
            expanded=False,
        ):
            try:
                preview_df = pd.DataFrame([
                    {
                        "company": r.get("company", "")[:40],
                        "title": r.get("title", "")[:80],
                        "location": r.get("location", "")[:30],
                        "posted": r.get("posted_date", ""),
                        "url": r.get("link", ""),
                    } for r in rows[:200]
                ])
                st.dataframe(
                    preview_df, hide_index=True, width='stretch',
                    column_config={"url": st.column_config.LinkColumn("open")},
                    height=min(420, 60 + 36 * len(preview_df)),
                )
                if n_rows > 200:
                    st.caption(f"+{n_rows - 200} more row(s) in `{latest.name}`")
            except Exception as e:
                st.caption(f"(preview unavailable: {e})")

        # ── DOWNLOADS ────────────────────────────────────────────────────
        # Inline JSON + xlsx for the freshly-pulled scan_gmail file. Saves a
        # round-trip to Pipeline ▸ History when the user just wants to see
        # the rows in Excel.
        try:
            import sys as _sys
            import importlib as _il
            _ad_p = str(ROOT / "automation")
            if _ad_p not in _sys.path:
                _sys.path.insert(0, _ad_p)
            # Force reload so a stale-cached audit_pack picks up new builders.
            if "audit_pack" in _sys.modules:
                _il.reload(_sys.modules["audit_pack"])
            from audit_pack import gmail_scan_to_xlsx as _gmail_to_xlsx
            render_artifact_download(
                "📥 Download these rows", latest, _gmail_to_xlsx,
                f"gmail_panel_{latest.stem}",
            )
        except Exception as _e:
            st.caption(f"(downloads unavailable: {_e})")

        # ── ACTIONS ──────────────────────────────────────────────────────
        # Three buttons: Score now (primary, only if not yet scored & key set),
        # Move-to-Trash (secondary, only if uids and not already deleted),
        # Hide (tertiary, dismiss without deleting).
        st.markdown("**Next steps:**")
        b1, b2, b3 = st.columns(3)

        # — Score now —
        # Honors the worklist contract: scores worklist.json (the deduped
        # union of latest scrape + recent Gmail), NOT the isolated
        # scan_gmail_<stamp>.json. The 6 fresh Gmail rows ride along
        # with the rest of the pool; cached rows hit the fit_cache and
        # re-score for ~free. Verdicts land in worklist_scored.json,
        # which auto_promote + the Today's queue actually read.
        # The previous behavior wrote a dead-end scan_gmail_*_scored.json
        # nobody downstream cared about.
        with b1:
            _key_ok = api_key.is_key_valid()
            # Block re-scoring if a scorer/pipeline is already running —
            # otherwise the user can launch a duplicate process.
            _can_score = _key_ok and not already_scored and not any_work_active
            score_label = (
                f"🤖 Score worklist (+{n_rows} new)"
                if not already_scored else "✅ Worklist already scored"
            )
            if st.button(
                score_label,
                type="primary" if _can_score else "secondary",
                width='stretch',
                disabled=not _can_score,
                key=f"gmail_score_{latest.stem}",
                help=(
                    f"Score the full worklist (latest scrape + Gmail). "
                    f"Cached rows reuse prior scores for free; the {n_rows} "
                    "new Gmail rows ride along. Verdicts land in "
                    "worklist_scored.json — that's the file auto_promote "
                    "and your Today's queue read."
                    if _can_score else
                    "Worklist scored after this Gmail fetch landed — "
                    "the new rows are in worklist_scored.json. "
                    "Check the Pipeline page for verdicts."
                    if already_scored else
                    "Another job is running — wait for it to finish."
                    if any_work_active else
                    "Needs Anthropic API key — set it in the sidebar."
                ),
            ):
                # Spawn fit_scorer with NO --scan so it auto-picks
                # worklist.json (the contract). Same as clicking the
                # main 🤖 Score worklist button on the Pipeline page.
                rec = scan_runner.start_run(
                    "pipeline",
                    [
                        sys.executable,
                        str(ROOT / "automation" / "run_pipeline.py"),
                        "--skip-scrape", "--skip-promote",
                        "--score-concurrency", "6",
                    ],
                )
                st.session_state["_last_launch"] = {
                    "run_id": rec.run_id,
                    "label": f"Score worklist (+{n_rows} new Gmail)",
                }
                st.toast(
                    f"🤖 Scoring worklist — {n_rows} new Gmail rows ride along…",
                    icon="🚀",
                )
                st.rerun()

        # — Trash —
        with b2:
            if alerts.get("deleted"):
                dr = alerts.get("delete_result") or {}
                st.button(
                    f"✅ {dr.get('moved', 0)} moved to Trash",
                    width='stretch', disabled=True,
                    key=f"gmail_trash_done_{latest.stem}",
                )
                do_delete = False
            elif uids:
                _trash_help = (
                    "Opens a read-write IMAP session and moves the listed "
                    "UIDs to [Gmail]/Trash. Reversible from Gmail UI; "
                    "auto-purges after 30 days."
                )
                if _uids_filtered_only:
                    _trash_help += (
                        f" Includes {_uids_filtered_only} all-US / "
                        "geo-filtered alert(s) that produced no Toronto "
                        "matches — they're spent, so they get cleaned up too."
                    )
                do_delete = st.button(
                    f"🗑 Move {len(uids)} alert(s) to Trash",
                    width='stretch',
                    key=f"gmail_trash_{latest.stem}",
                    help=_trash_help,
                )
                if _uids_filtered_only:
                    st.caption(
                        f"Incl. {_uids_filtered_only} all-US/filtered alert(s) "
                        "(no Toronto match) + "
                        f"{len(_contributing_uids)} that produced matches."
                    )
            else:
                st.button("🗑 (no UIDs to delete)",
                           width='stretch', disabled=True,
                           key=f"gmail_trash_none_{latest.stem}")
                do_delete = False

        # — Hide —
        with b3:
            if not alerts.get("deleted") and uids:
                if st.button(
                    "🙈 Hide cleanup prompt",
                    width='stretch',
                    key=f"gmail_trash_hide_{latest.stem}",
                    help="Mark this scan as 'don't ask again' without "
                         "deleting any mail. The next Gmail fetch resets.",
                ):
                    env.setdefault("gmail_alerts", {})
                    env["gmail_alerts"]["deleted"] = True
                    env["gmail_alerts"]["delete_result"] = {
                        "moved": 0, "failed": 0,
                        "errors": ["User dismissed without deleting."],
                    }
                    env["gmail_alerts"]["deleted_at"] = (
                        datetime.now().isoformat(timespec="seconds")
                    )
                    latest.write_text(
                        json.dumps(env, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    st.rerun()

        # ── DELETE EXECUTION ─────────────────────────────────────────────
        if 'do_delete' in locals() and do_delete:
            try:
                sys.path.insert(0, str(ROOT / "automation"))
                import gmail_reader as _gr  # type: ignore
                with st.spinner(f"Moving {len(uids)} alert(s) to Trash…"):
                    res = _gr.delete_messages(uids)
            except Exception as e:
                st.error(f"Delete failed before IMAP call: {e}")
                return True
            env.setdefault("gmail_alerts", {})
            env["gmail_alerts"]["deleted"] = True
            env["gmail_alerts"]["deleted_at"] = (
                datetime.now().isoformat(timespec="seconds")
            )
            env["gmail_alerts"]["delete_result"] = {
                "moved": res.moved,
                "failed": res.failed,
                "errors": list(res.errors or [])[:10],
            }
            try:
                latest.write_text(
                    json.dumps(env, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                st.warning(f"Trash succeeded but persisting result failed: {e}")
            if res.failed == 0:
                st.success(
                    f"✅ Moved {res.moved} alert(s) to Gmail Trash. "
                    "They'll auto-purge after 30 days."
                )
            else:
                st.warning(
                    f"Moved {res.moved}, failed {res.failed}. "
                    f"Errors: {res.errors[:3]}"
                )
            st.rerun()

    return True


def list_pipelines(limit: int = 20) -> list[dict]:
    if not PIPELINE_DIR.exists():
        return []
    # The glob also matches the `pipeline_<id>_suppressions.json` snapshots
    # that run_pipeline._snapshot_suppressions writes into the same dir —
    # those are {version,sectors,companies}, NOT run records (no pipeline_id /
    # state), so they pollute the history table and crash the `p["pipeline_id"]`
    # selectbox. Exclude them; also skip any file missing pipeline_id so a
    # future sidecar can't reintroduce the crash.
    files = sorted(
        (p for p in PIPELINE_DIR.glob("pipeline_*.json")
         if not p.name.endswith("_suppressions.json")),
        key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not data.get("pipeline_id"):
                continue
            out.append(_resolve_pipeline_staleness(data, p))
        except Exception:
            continue
    return out


sys.path.insert(0, str(ROOT / "automation"))
import worklist  # noqa: E402


def latest_scan() -> Path | None:
    """Scorer/funnel input: working set -> scrape source -> newest scan."""
    return worklist.effective_scan()


def latest_scored() -> Path | None:
    files = sorted(OUT_DIR.glob("*_scored.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


st.set_page_config(
    page_title="ApplyAgent — Saber's Job Search",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""<style>
/* Typography hierarchy. h2 (st.header) is intentionally omitted — no page
   currently uses it; if you reintroduce st.header somewhere, add a rule. */
[data-testid="stAppViewContainer"] h1 { font-size: 1.5rem; margin-bottom: 0.3rem; }
[data-testid="stAppViewContainer"] h3 { font-size: 1.05rem; margin-bottom: 0.15rem; }
[data-testid="stAppViewContainer"] h4 { font-size: 0.95rem; margin-bottom: 0.1rem; font-weight: 600; }
/* Tighter vertical spacing */
[data-testid="stMetric"] { padding: 0.3rem 0 !important; }
/* Sidebar tighter */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { margin-bottom: 0.2rem; }
[data-testid="stSidebar"] hr { margin: 0.4rem 0; }
[data-testid="stSidebar"] [data-testid="stExpander"] { margin-bottom: 0.3rem; }
</style>""", unsafe_allow_html=True)

# Density polish: when a panel is healthy, defer to a one-line caption at the
# bottom of the sidebar (see compact-status footer below). Render the full
# card here only when something needs the user's attention.
if api_key.is_key_valid():
    _api_compact = True
else:
    api_key.render_sidebar()
    _api_compact = False

if gmail_ui.is_connected():
    _gmail_compact = True
else:
    gmail_ui.render_sidebar()
    _gmail_compact = False

try:
    _ledger = cost_ledger.load()
    _lt_tot = _ledger.get("totals", {})
    _lt_cost = _lt_tot.get("estimated_cost_usd", 0.0) or 0.0
    _lt_calls = _lt_tot.get("llm_calls", 0) or 0
    _lt_in = _lt_tot.get("input_tokens", 0) or 0
    _lt_out = _lt_tot.get("output_tokens", 0) or 0
    _lt_tokens = _lt_in + _lt_out
    _daily = _ledger.get("daily", {}) or {}
    _today_key = datetime.now().strftime("%Y-%m-%d")
    # cost_ledger writes daily entries with key `cost_usd` (not `estimated_cost_usd`).
    # totals uses `estimated_cost_usd`. Don't unify these casually — the on-disk
    # schema is the source of truth.
    _today_cost = float((_daily.get(_today_key) or {}).get("cost_usd", 0.0))
    _week_cost = 0.0
    for _i in range(7):
        _k = (datetime.now() - timedelta(days=_i)).strftime("%Y-%m-%d")
        _week_cost += float((_daily.get(_k) or {}).get("cost_usd", 0.0))
    if _today_cost >= 10.0:
        _today_emoji = "🔴"
    elif _today_cost >= 5.0:
        _today_emoji = "🟡"
    else:
        _today_emoji = "🟢"
except Exception:
    _lt_cost = _lt_calls = _lt_tokens = 0
    _today_cost = _week_cost = 0.0
    _today_emoji = "🟢"

_err_last_hour = _err_last_day = 0
if error_log is not None:
    try:
        _err_last_hour = error_log.count_recent(since_minutes=60)
        _err_last_day = error_log.count_recent(since_minutes=60 * 24)
    except Exception:
        pass
_err_caption = ""
if _err_last_hour >= 5:
    _err_caption = f"🔴 {_err_last_hour} error(s) last hour · {_err_last_day} 24h — see Admin"
elif _err_last_hour > 0:
    _err_caption = f"⚠️ {_err_last_hour} last hour · {_err_last_day} 24h — see Admin"
elif _err_last_day > 0:
    _err_caption = f"ℹ️ {_err_last_day} error(s) in last 24h — see Admin"

st.sidebar.markdown("---")

_crm_early = load_crm()
_crm_early_all = (_crm_early.get("recruiters") or []) + (_crm_early.get("alumni_warm_intros") or [])
_crm_badge_count = sum(
    1 for c in _crm_early_all
    if c.get("priority") == "High"
    and c.get("status") in ("Not_Contacted",)
    and not c.get("last_touchpoint")
)

# Top-level groups + their children. Each child label maps to the EXACT
# page-name string the if/elif router downstream expects — that way the
# 12 page bodies don't need to change, and external session_state writes
# (e.g. AppTest harness) using the old name still resolve correctly.
_NAV_GROUPS = {
    "🏠 Today": [
        ("Dashboard",   "🏠 Dashboard"),
        ("Replies",     "📥 Outcome Inbox"),
        ("Review",      "📬 Review Queue"),
        ("Follow-ups",  "🔔 Follow-ups"),
    ],
    "🎯 Pipeline": [
        ("Refresh",     "🎯 Pipeline · Refresh"),   # ① Inputs + ② Worklist
        ("Score",       "🎯 Pipeline · Score"),     # ③ Triage + ④ Scoring
        ("Promote",     "🎯 Pipeline · Promote"),   # ⑤ Auto-promote + ⑥ Tracker
        ("History",     "📜 Scan History"),         # run-log of every scan/score/run
    ],
    "📋 Roles": [
        ("Tracker",     "📋 Jobs Kanban"),
    ],
    "🤝 Network": [
        ("",            "🤝 Recruiter CRM"),
    ],
    "⚙️ System": [
        ("Admin",       "⚙️ Admin"),
        ("Analytics",   "📊 Analytics"),
        ("Weekly Plan", "📅 Weekly Plan"),
        ("Content",     "📝 Content & Memory"),
    ],
}
# Map every old page-name back to its new (group, child) so a directly-set
# session_state still routes correctly. AppTest does this; users who had
# a deep nav state from the previous nav layout do too.
_LEGACY_PAGE_TO_GROUP = {
    child_page: (group, child_label)
    for group, items in _NAV_GROUPS.items()
    for (child_label, child_page) in items
}
# v3.2: the former single "🎯 Pipeline" page split into 3 sub-pages. A saved
# nav state (or AppTest / external write) using the old string resolves to the
# ① Refresh view so old deep-links and existing tests keep working.
_LEGACY_PAGE_TO_GROUP["🎯 Pipeline"] = ("🎯 Pipeline", "Refresh")


# Backwards-compat: if the user (or the AppTest harness) wrote one of
# the 12 OLD page names directly into _applyagent_nav, translate that
# into the new (group, child) so the radio defaults match. Without
# this, an old name silently falls through to the first group and the
# user lands somewhere unexpected.
_nav_state = st.session_state.get("_applyagent_nav")
if _nav_state in _LEGACY_PAGE_TO_GROUP:
    _legacy_group, _legacy_child = _LEGACY_PAGE_TO_GROUP[_nav_state]
    st.session_state["_applyagent_nav"] = _legacy_group
    # A genuine OLD child page-name (e.g. "📥 Outcome Inbox" → Replies)
    # unambiguously dictates its child, so force it — otherwise a stale
    # sub-pick left over from a previous visit to that group wins and the
    # deep-link lands on the wrong page. The ONLY exception is the bare
    # "🎯 Pipeline" SELF-alias (key == group): it has no inherent child, so an
    # explicit pick (a banner CTA's pending view, or a saved Score/Promote
    # selection) must survive rather than being reset to Refresh every rerun.
    _is_self_alias = (_nav_state == _legacy_group)
    if _legacy_child and not (
        _is_self_alias and st.session_state.get(f"_nav_sub_{_legacy_group}")
    ):
        st.session_state[f"_nav_sub_{_legacy_group}"] = _legacy_child

# Deferred nav jump (v3.2). Streamlit drops a write to a widget's key made
# AFTER that widget is instantiated in the same run. A banner CTA fired from
# the Pipeline page runs after the Pipeline sub-radio has already rendered, so
# it can't switch the sub-page directly. Instead it stashes the target in the
# non-widget key `_pipe_pending_view`; we transfer it to the sub-radio key HERE
# — before the radios instantiate — then clear it. (Cross-GROUP jumps already
# work because the destination group's sub-radio hasn't rendered yet; this
# covers the within-Pipeline case the banner needs.)
_pending_view = st.session_state.pop("_pipe_pending_view", None)
if _pending_view in ("Refresh", "Score", "Promote", "History"):
    st.session_state["_applyagent_nav"] = "🎯 Pipeline"
    st.session_state["_nav_sub_🎯 Pipeline"] = _pending_view

# Same deferred-jump pattern, but for the MAIN nav GROUP. A button rendered
# AFTER the sidebar radio (the ⑥ Tracker card's "→ Jobs Kanban", the
# dashboard's Next-Best-Action jumps, "→ Open Scan History", etc.) cannot
# write _applyagent_nav directly — Streamlit raises StreamlitAPIException
# once the radio with that key is instantiated. Those handlers stash the
# target group in the non-widget key `_pending_main_nav`; we transfer it to
# the radio key HERE, before the radio instantiates, then it's cleared by
# the pop. (Companion sub-page writes go to _nav_sub_<group>, which is safe
# from the handler because that group's sub-radio isn't on screen yet.)
_pending_main_nav = st.session_state.pop("_pending_main_nav", None)
if _pending_main_nav in _NAV_GROUPS:
    st.session_state["_applyagent_nav"] = _pending_main_nav

_nav_pick = st.sidebar.radio(
    "Navigate",
    list(_NAV_GROUPS.keys()),
    index=0,                                    # default: 🏠 Today
    label_visibility="collapsed",
    key="_applyagent_nav",
)

# Sub-radio for groups with multiple children. Single-child groups skip
# the sub-radio and resolve directly. The sub key is per-group so each
# group preserves its own "last visited" subpage when you flip groups.
_children = _NAV_GROUPS.get(_nav_pick, [])
if len(_children) <= 1:
    page = _children[0][1] if _children else "🏠 Dashboard"
else:
    _sub_labels = [c[0] for c in _children]
    _sub_key = f"_nav_sub_{_nav_pick}"
    _sub_pick = st.sidebar.radio(
        f"{_nav_pick} sections",
        _sub_labels,
        index=0,
        label_visibility="collapsed",
        key=_sub_key,
    )
    page = next((c[1] for c in _children if c[0] == _sub_pick),
                _children[0][1])

# Expose the resolved page key so the AppTest harness can assert that nav
# resolved to the EXPECTED route (not just that *some* page rendered). Without
# this, a wrong-sub-page bug (e.g. Score requested but Refresh rendered) would
# still render fine and pass a structural-only check. Cheap, side-effect-free.
st.session_state["_resolved_page"] = page

# ── Sidebar urgency strip ──────────────────────────────────────────────
# Surfaces the most time-sensitive action counts so they're visible from
# any page without navigating to CRM.
if _crm_badge_count > 0:
    st.sidebar.markdown(
        f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
        f"background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);"
        f"border-radius:6px;font-size:12px;color:#f87171;line-height:1.4'>"
        f"🤝 <strong>{_crm_badge_count}</strong> high-priority recruiter"
        f"{'s' if _crm_badge_count != 1 else ''} awaiting outreach</div>",
        unsafe_allow_html=True,
    )

# Follow-up due badge (overdue + due today)
try:
    _fu_jobs_early = load_tracker().get("jobs", [])
    _fu_buckets_early = followup_buckets(_fu_jobs_early)
    _fu_badge_count = len(_fu_buckets_early["overdue"]) + len(_fu_buckets_early["due_today"])
    if _fu_badge_count > 0:
        st.sidebar.markdown(
            f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
            f"background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);"
            f"border-radius:6px;font-size:12px;color:#fbbf24;line-height:1.4'>"
            f"🔔 <strong>{_fu_badge_count}</strong> follow-up"
            f"{'s' if _fu_badge_count != 1 else ''} due — check Follow-ups</div>",
            unsafe_allow_html=True,
        )
except Exception:
    _fu_badge_count = 0

# Scan-freshness pill — silent if 0-1d, yellow at 2-6d, red at ≥7d. Without
# this, a 10-day-old scan looks the same as one minutes old; the campaign is
# 70 days, so multi-day staleness genuinely matters.
try:
    _scan_path = latest_scan()
    if _scan_path and _scan_path.exists():
        _scan_age_days = int(
            (datetime.now().timestamp() - _scan_path.stat().st_mtime) // 86400
        )
        if _scan_age_days >= 7:
            st.sidebar.markdown(
                f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
                f"background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);"
                f"border-radius:6px;font-size:12px;color:#f87171;line-height:1.4'>"
                f"🛰 Web scan <strong>{_scan_age_days}d</strong> stale — refresh</div>",
                unsafe_allow_html=True,
            )
        elif _scan_age_days >= 2:
            st.sidebar.markdown(
                f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
                f"background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);"
                f"border-radius:6px;font-size:12px;color:#fbbf24;line-height:1.4'>"
                f"🛰 Web scan <strong>{_scan_age_days}d</strong> old</div>",
                unsafe_allow_html=True,
            )
except Exception:
    pass

# Active-runs badge in sidebar
active_runs = scan_runner.active_runs()
pipe = latest_pipeline_status()
pipeline_running = pipe and pipe.get("state") == "running"

# Scorer progress is live if the progress file is <60s old and state=running.
# We check this before deciding to auto-refresh so an idle page doesn't ping
# the filesystem every 5s unnecessarily.
def _scorer_progress_live() -> bool:
    try:
        p = OUT_DIR / "fit_scorer_progress.json"
        if not p.exists():
            return False
        age = (datetime.now().timestamp() - p.stat().st_mtime)
        if age > 60:
            return False
        state = json.loads(p.read_text(encoding="utf-8")).get("state")
        return state == "running"
    except Exception:
        return False


scorer_running = _scorer_progress_live()
any_work_active = bool(active_runs or pipeline_running or scorer_running)

# @st.fragment — available in Streamlit ≥1.33. When present, the live
# pipeline panel re-runs itself every 3s without flashing the entire page.
# When absent, we fall back to the existing st_autorefresh approach.
_HAS_FRAGMENT = hasattr(st, "fragment")

# Auto-refresh: poll every 5s ONLY when something is actively running. An
# idle dashboard stays idle (no rerun thrash, no battery drain). The user
# can also hit 🔄 Refresh manually — see sidebar below. `key` is distinct
# per page so Streamlit doesn't treat them as one counter.
# Only use the page-wide autorefresh when @st.fragment isn't available.
# With fragments, only the live-output widget rerenders every 3s — the
# rest of the page stays perfectly still while a job runs.
if any_work_active and _HAVE_AUTOREFRESH and not _HAS_FRAGMENT:
    st_autorefresh(interval=5000, key=f"_autorefresh_{page}")

if any_work_active:
    st.sidebar.markdown("---")
    st.sidebar.caption("**Active**")
    if pipeline_running:
        st.sidebar.caption(
            f"Pipeline `{pipe['pipeline_id']}` · {human_elapsed(pipe.get('started_at'))}"
        )
    if scorer_running:
        st.sidebar.caption("Scorer running")
    for r in active_runs:
        st.sidebar.caption(
            f"{r['label']} · {human_elapsed(r['started_at'])} · pid {r['pid']}"
        )
if st.sidebar.button("🔄 Reload page", key="sidebar_refresh_now",
                      width='stretch',
                      help="Clear Streamlit caches and re-read tracker, CRM, "
                           "progress, and run state from disk. "
                           "Does NOT launch a scrape or any background job."):
    st.cache_data.clear()
    st.rerun()

# Compact spend + error line. The `\$` escapes are LOAD-BEARING — Streamlit
# hands runs of `$...$` in markdown to KaTeX, which crashes on emoji
# ("No character metrics for '🔴' in style 'Main-Regular'"). Don't unescape.
st.sidebar.markdown("---")
st.sidebar.caption(
    f"{_today_emoji} today **\\${_today_cost:.2f}** · "
    f"**\\${_lt_cost:.2f}** lifetime · {_lt_calls:,} calls"
)
if _err_caption:
    st.sidebar.caption(_err_caption)

# Compact API + Gmail status footer. When the API key + Gmail are both
# healthy, we deferred the full cards (top of sidebar) — surface them here
# as one-line captions so the user still has at-a-glance confirmation.
if _api_compact or _gmail_compact:
    st.sidebar.markdown("---")
    if _api_compact:
        api_key.render_compact_status()
    if _gmail_compact:
        gmail_ui.render_compact_status()

tr = load_tracker()
crm = load_crm()
jobs = tr.get("jobs", [])
jobs_df = pd.DataFrame(jobs) if jobs else pd.DataFrame()


# ============================================================================
# Live pipeline monitor — must be defined BEFORE the if/elif page chain so
# it can be optionally wrapped with @st.fragment (Streamlit ≥1.33), which
# makes only this widget rerender every 3s instead of the entire page.
# Falls back gracefully to a plain function (+ global autorefresh) if older.
# ============================================================================
def _pipeline_live_panel_inner():
    """Core render logic — called by both fragment and non-fragment variants."""
    _live_runs = scan_runner.active_runs()
    _live_pipeline = latest_pipeline_status()
    _live_pipeline_running = _live_pipeline and _live_pipeline.get("state") == "running"

    # Detect transition from "running" → "idle". When a background job finishes,
    # the fragment keeps polling for one more cycle and sees nothing active.
    # At that point, trigger a full-page rerun so the rest of the page (which
    # rendered with stale data) re-reads from disk.
    _was_active = st.session_state.get("_live_panel_was_active", False)
    _is_active = bool(_live_runs or _live_pipeline_running)
    st.session_state["_live_panel_was_active"] = _is_active
    if _was_active and not _is_active:
        st.rerun()

    render_scorer_progress()

    # Also show recently-failed runs so fast crashes are visible to the user
    _recent_failed = None
    if not _live_runs:
        _all_recent = scan_runner.list_runs(limit=3)
        for _rr in _all_recent:
            if _rr.get("state") == "failed":
                _fin = _rr.get("finished_at", "")
                if _fin:
                    try:
                        _age = (datetime.now() -
                                datetime.fromisoformat(_fin)).total_seconds()
                        if _age < 60:
                            _recent_failed = _rr
                            break
                    except Exception:
                        pass

    if _recent_failed:
        st.markdown("---")
        with st.container(border=True):
            st.markdown(f"#### ❌ `{_recent_failed['label']}` failed")
            _log_text = scan_runner.tail_log(_recent_failed.get("log_path", "")) or ""
            if _log_text:
                st.code(_log_text, language="text", height=300)
            else:
                st.warning("No log output captured.")
            st.caption(f"Run ID: `{_recent_failed['run_id']}`")

    if _live_pipeline_running or _live_runs:
        st.markdown("---")
        _current = next(
            (r for r in _live_runs if r.get("label", "").startswith("pipeline")),
            _live_runs[0] if _live_runs else None,
        )
        if _current:
            with st.container(border=True):
                _lh1, _lh2, _lh3 = st.columns([4, 2, 1])
                _lh1.markdown(
                    f"#### 📡 Live · `{_current['label']}` · pid {_current['pid']}"
                )
                _lh2.metric("Running", human_elapsed(_current["started_at"]))
                if _lh3.button("⏹ Stop", key="frag_stop_pipe",
                               help="Send stop signal — process exits after current step"):
                    scan_runner.stop_run(_current["run_id"])
                    st.warning(
                        "⏹ Stop signal sent — process will exit after the current step."
                    )
                _log_text = scan_runner.tail_log(_current["log_path"]) or ""
                # Surface current stage from log
                _stage_match = None
                for _ll in reversed((_log_text or "").splitlines()):
                    if any(tag in _ll for tag in ("[0/3]", "[1/3]", "[2/3]", "[3/3]")):
                        _stage_match = _ll.strip()
                        break
                if _stage_match:
                    st.caption(f"⚙️ {_stage_match}")
                st.code(
                    _log_text if _log_text else "⏳ Starting — waiting for first output…",
                    language="text",
                    height=400,
                )
                _refresh_note = (
                    "↻ live (every 3s — no page flash)"
                    if _HAS_FRAGMENT else "↻ auto-refreshes every 5s"
                )
                st.caption(
                    f"Run ID: `{_current['run_id']}` · {_refresh_note} · "
                    f"log: `{Path(_current['log_path']).name}`"
                )


if _HAS_FRAGMENT:
    @st.fragment(run_every=3)
    def _pipeline_live_panel():
        """Fragment version: only this widget rerenders every 3s — no page flash."""
        _pipeline_live_panel_inner()
else:
    def _pipeline_live_panel():
        """Fallback: plain function, page-wide autorefresh handles timing."""
        _pipeline_live_panel_inner()


# ============================================================================
# 🏠 DASHBOARD
# ============================================================================
if page == "🏠 Dashboard":
    meta = tr.get("meta", {})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    targets = meta.get("weekly_kpi_targets", {})

    _now = datetime.now()
    _greet = ("Good morning" if _now.hour < 12
              else "Good afternoon" if _now.hour < 17 else "Good evening")

    # Pull brief data early for the stat row (load_morning_brief is cached)
    _brief_now = load_morning_brief()
    _brief_entries_top = (_brief_now.get("top") or []) if _brief_now else []
    _brief_date_raw_top = (_brief_now.get("brief_date", "") if _brief_now else "")
    _brief_is_today = False
    if _brief_date_raw_top:
        try:
            _brief_is_today = (
                datetime.strptime(_brief_date_raw_top, "%Y%m%d").date() == date.today()
            )
        except ValueError:
            pass
    _new_matches_today = len(_brief_entries_top) if _brief_is_today else 0
    _top_score_val = None
    _top_score_tip = "No brief today — run nightly refresh"
    if _brief_entries_top:
        try:
            _top_score_val = int(
                _brief_entries_top[0].get("fit", {}).get("fit_score", 0) or 0
            )
            _top_company = _brief_entries_top[0].get("company", "?")
            _top_title = _brief_entries_top[0].get("title", "?")
            _top_score_tip = f"{_top_company} — {_top_title}"
        except (TypeError, ValueError):
            pass

    _applied_this_week = sum(
        1 for j in jobs
        if j.get("date_applied") and parse_date(j.get("date_applied")) is not None
        and parse_date(j.get("date_applied")) >= week_start
    )

    # Last brief timestamp
    _brief_files_top = sorted(
        OUT_DIR.glob("brief_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    _brief_ts_str = ""
    if _brief_files_top:
        _bts = datetime.fromtimestamp(_brief_files_top[0].stat().st_mtime)
        _brief_ts_str = f"Brief refreshed {_bts.strftime('%b %d at %I:%M %p')}"

    # Greeting row
    st.markdown(f"## {_greet}, Saber 👋")
    st.caption(
        f"{today.strftime('%A, %B %d')} · {_brief_ts_str}"
        if _brief_ts_str else today.strftime('%A, %B %d')
    )

    # ── Next Best Action hero ────────────────────────────────────────────
    # ONE thing across all surfaces — picks the single highest-priority item
    # so the answer to "what should I do right now" is decided pre-click.
    # Lane multiplier privileges ALM-primary per feedback_positioning.md.
    _nba_recs = (crm.get("recruiters") or []) + (crm.get("alumni_warm_intros") or [])
    _nba = compute_next_best_action(jobs, _nba_recs, OUT_DIR / "outcome_proposals.json")
    if _nba:
        with st.container(border=True):
            _nba_c1, _nba_c2 = st.columns([5, 2])
            with _nba_c1:
                st.markdown(
                    f"<div style='font-size:0.78em;opacity:0.75;letter-spacing:0.04em;"
                    f"text-transform:uppercase;font-weight:600;color:#6366f1'>"
                    f"NEXT BEST ACTION</div>"
                    f"<div style='font-size:1.15em;font-weight:600;margin:2px 0 4px 0'>"
                    f"{_nba['label']}</div>"
                    f"<div style='font-size:0.85em;opacity:0.75'>{_nba['sublabel']}</div>",
                    unsafe_allow_html=True,
                )
            with _nba_c2:
                _nba_kind = _nba.get("kind")
                if _nba_kind == "tailor_or_apply" and _nba.get("job"):
                    render_tailor_action_row(
                        _nba["job"], key_prefix="nba",
                        tracker_data=tr, tracker_path=TRACKER,
                    )
                elif _nba_kind == "followup" and _nba.get("job"):
                    if st.button("📨 Open Follow-ups", key="nba_followup_btn",
                                  width='stretch', type="primary"):
                        st.session_state["_pending_main_nav"] = "🏠 Today"
                        st.session_state["_nav_sub_🏠 Today"] = "Follow-ups"
                        st.rerun()
                elif _nba_kind == "recruiter":
                    if st.button("🤝 Open Network", key="nba_recruiter_btn",
                                  width='stretch', type="primary"):
                        st.session_state["_pending_main_nav"] = "🤝 Network"
                        st.rerun()
                elif _nba_kind == "outcome":
                    if st.button("✅ Open Replies", key="nba_outcome_btn",
                                  width='stretch', type="primary"):
                        st.session_state["_pending_main_nav"] = "🏠 Today"
                        st.session_state["_nav_sub_🏠 Today"] = "Replies"
                        st.rerun()
            # Explainability line — score breakdown in one glance
            _bk = _nba.get("_breakdown")
            if _bk:
                st.caption(
                    f"Score {_nba['score']:.1f} · fit {_bk['fit']} · "
                    f"{_bk['lane']} {_bk['lane_mult']}× · "
                    f"urgency +{_bk['urgency_bonus']}"
                )
            else:
                st.caption(f"Score {_nba['score']:.1f} · {_nba.get('kind', '')}")

    # ── Since-you-last-looked strip ───────────────────────────────────────
    # Persist last_visit_at to ~/.applyagent/session.json. On render: count
    # changes since that timestamp across 4 axes (new Founds, recruiter
    # responses, new follow-up overdues, new Gmail outcome proposals) and
    # render a compact line. First-visit ever: silent.
    _last_visit = read_last_visit()
    if _last_visit is not None and (datetime.now() - _last_visit).total_seconds() >= 1800:
        # Only render if ≥30min since last visit — otherwise it's just a refresh.
        _slv_new_found = 0
        _slv_new_overdue = 0
        _slv_new_responses = 0
        _slv_proposals = 0
        for _j in jobs:
            _df = parse_date(_j.get("date_found"))
            if _df and datetime.combine(_df, datetime.min.time()) >= _last_visit:
                if int(_j.get("fit_score_numeric") or 0) >= 4:
                    _slv_new_found += 1
            for _o in (_j.get("outreach_log") or []):
                _od = parse_date(_o.get("date"))
                if (_od and datetime.combine(_od, datetime.min.time()) >= _last_visit
                        and _o.get("type") == "response"):
                    _slv_new_responses += 1
            _next_due = parse_date((_j.get("followup_schedule") or {}).get("next_due"))
            if _next_due and _last_visit.date() <= _next_due < today:
                # next_due crossed into "overdue" territory in this window
                _slv_new_overdue += 1
        try:
            _slv_props_path = OUT_DIR / "outcome_proposals.json"
            if _slv_props_path.exists():
                _slv_props = json.loads(_slv_props_path.read_text(encoding="utf-8"))
                _slv_proposals = sum(
                    1 for p in (_slv_props or [])
                    if (p.get("evidence") or {}).get("checked_at", "") >= _last_visit.isoformat()
                )
        except Exception:
            pass
        _slv_parts = []
        if _slv_new_found:    _slv_parts.append(f"**{_slv_new_found}** new Found")
        if _slv_new_responses: _slv_parts.append(f"**{_slv_new_responses}** recruiter response{'s' if _slv_new_responses != 1 else ''}")
        if _slv_new_overdue:  _slv_parts.append(f"**{_slv_new_overdue}** follow-up{'s' if _slv_new_overdue != 1 else ''} now overdue")
        if _slv_proposals:    _slv_parts.append(f"**{_slv_proposals}** outcome proposal{'s' if _slv_proposals != 1 else ''}")
        if _slv_parts:
            _hrs = (datetime.now() - _last_visit).total_seconds() / 3600
            _ago = f"{int(_hrs)}h" if _hrs >= 1 else f"{int(_hrs * 60)}m"
            st.info(
                f"📌 Since you last looked ({_ago} ago) · " + " · ".join(_slv_parts),
                icon="✨",
            )
    write_last_visit()

    # Stat row
    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
    _sc1.metric(
        "New matches today",
        _new_matches_today,
        help=("Top picks from today's morning brief."
              if _brief_is_today else "Run nightly refresh to get today's picks."),
    )
    _sc2.metric("Applied this week", _applied_this_week)
    _sc3.metric(
        "Top score",
        f"{_top_score_val}/10" if _top_score_val else "—",
        help=_top_score_tip,
    )
    _sc4.metric(
        "CRM: outreach due",
        _crm_badge_count,
        delta="high priority" if _crm_badge_count > 0 else None,
        delta_color="inverse" if _crm_badge_count > 0 else "normal",
        help="High-priority recruiters not yet contacted. Go to 🤝 Recruiter CRM.",
    )

    # ── Pipeline-health pill ──
    # Compact funnel visualization: "Found 28 → Applied 0 → Interview 0 → Offer 0"
    # Amber warning if no jobs have progressed past Watch; green otherwise.
    _funnel_stages = [
        ("Found", "Found"),
        ("Watch", "Watch"),
        ("Applied", "Applied"),
        ("Interview", ("Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite")),
        ("Offer", ("Offer",)),
    ]
    _funnel_counts = {}
    for label, match in _funnel_stages:
        if isinstance(match, tuple):
            _funnel_counts[label] = sum(
                1 for j in jobs if j.get("status") in match
            )
        else:
            _funnel_counts[label] = sum(
                1 for j in jobs if j.get("status") == match
            )
    _funnel_active = _funnel_counts["Applied"] + _funnel_counts["Interview"]
    _funnel_color = _C_GREEN if _funnel_active > 0 else _C_AMBER
    _funnel_parts = []
    for label, _ in _funnel_stages:
        n = _funnel_counts[label]
        weight = "700" if n > 0 else "400"
        opacity = "1" if n > 0 else "0.5"
        _funnel_parts.append(
            f"<span style='font-weight:{weight};opacity:{opacity}'>"
            f"{label} {n}</span>"
        )
    _funnel_html = " → ".join(_funnel_parts)
    _funnel_icon = "✅" if _funnel_active > 0 else "⚠️"
    st.markdown(
        f"<div style='padding:6px 12px;background:{_funnel_color}0d;"
        f"border:1px solid {_funnel_color}33;border-radius:6px;"
        f"font-size:0.82em;margin-bottom:12px'>"
        f"{_funnel_icon} <b>Pipeline:</b> {_funnel_html}</div>",
        unsafe_allow_html=True,
    )

    # ── Today's queue ──
    _APPLY_STATUSES = {"Found", "Watch", "Tailoring"}
    _NO_FOLLOWUP_STATUSES = {"Rejected", "Withdrawn", "Offer", "Expired"}
    _today_apply_now = []
    _today_followups = []
    for _j in jobs:
        # Phase 3D: archive removes a job from EVERY active surface,
        # including Today's queue. The Kanban inspector's Restore button
        # is the user-facing path back.
        if _j.get("archived", False):
            continue
        _st = _j.get("status", "")
        _fitn = int(_j.get("fit_score_numeric") or 0)
        # Apply-now: ready-to-apply roles, must have fit ≥6 to surface
        if _st in _APPLY_STATUSES and _fitn >= 6 and not _j.get("date_applied"):
            _today_apply_now.append(_j)
        # Follow-up: applied + past next_due, or applied 3+ days ago with
        # no logged outreach since
        if _st not in _NO_FOLLOWUP_STATUSES:
            _next_due_str = (_j.get("followup_schedule") or {}).get("next_due")
            _next_due = parse_date(_next_due_str)
            _date_app = parse_date(_j.get("date_applied"))
            _is_due = bool(_next_due and _next_due <= today)
            _olog = _j.get("outreach_log") or []
            _last_touch = max(
                (parse_date(o.get("date")) for o in _olog if parse_date(o.get("date"))),
                default=None,
            )
            _stale_apply = (
                _date_app and (today - _date_app).days >= 3
                and (not _last_touch or (today - _last_touch).days >= 3)
            )
            if _is_due or _stale_apply:
                _j["_followup_reason"] = (
                    "due " + str((today - _next_due).days) + "d ago"
                    if _is_due else f"applied {(today - _date_app).days}d ago"
                )
                _today_followups.append(_j)

    # Sort each bucket by urgency / staleness, lane-weighted
    _today_apply_now.sort(
        key=lambda j: (
            0 if (j.get("urgency") or "").lower() == "high" else 1,
            -int(j.get("fit_score_numeric") or 0) * lane_mult(j),
        )
    )
    _today_followups.sort(
        key=lambda j: (parse_date(j.get("date_applied")) or today),
    )

    # CRM reach-outs (already computed above as _crm_early_all but
    # filter to high-priority + not contacted)
    _today_reach_out = [
        c for c in _crm_early_all
        if c.get("priority") == "High"
        and c.get("status") == "Not_Contacted"
        and not c.get("last_touchpoint")
    ][:5]

    _total_today = (
        len(_today_apply_now[:5])
        + len(_today_followups[:5])
        + len(_today_reach_out)
    )
    if _total_today:
        with st.container(border=True):
            st.markdown(f"### 🎯 Today's queue · **{_total_today} action"
                         f"{'s' if _total_today != 1 else ''}**")
            st.caption("Ranked by urgency. One-click actions below each role.")

            if _today_apply_now:
                st.markdown(
                    f"#### 🟢 Apply now · {min(len(_today_apply_now), 5)}"
                    + (f" of {len(_today_apply_now)}"
                       if len(_today_apply_now) > 5 else "")
                )
                # Brief-by-url lookup: if a queue entry matches today's brief
                # entry, surface the brief's verdict-color pill so the merged
                # card has both the verdict AND the action rows.
                _brief_by_url = {}
                if _brief_is_today and _brief_entries_top:
                    for _br in _brief_entries_top:
                        _u = _br.get("link") or ""
                        if _u:
                            _brief_by_url[_u] = _br
                _VERDICT_LABEL = {"apply_now": "✅ Apply now",
                                  "tailor_and_apply": "✍️ Tailor & apply",
                                  "watch": "👀 Watch"}
                for _j in _today_apply_now[:5]:
                    _co = _j.get("company", "?")
                    _ti = _j.get("title", "?")[:80]
                    _fit = int(_j.get("fit_score_numeric") or 0)
                    _urg = _j.get("urgency", "")
                    _crm_n = len(crm_contacts_at_company(crm, _co))
                    _has_t = bool(_find_tailor_docs(_j))
                    _br_match = _brief_by_url.get(_j.get("url", ""))
                    _verdict = (_br_match.get("fit", {}).get("fit_verdict")
                                if _br_match else None)
                    _vcolor = VERDICT_COLORS.get(_verdict or "", "")
                    _vlabel = _VERDICT_LABEL.get(_verdict or "", "")
                    _badges = []
                    _tq_pv = (_j.get("primary_variant") or "").upper()
                    if _tq_pv in LANE_MULTIPLIERS:
                        _badges.append(
                            f"<span style='color:{LANE_COLORS.get(_tq_pv, _C_INDIGO)};"
                            f"font-weight:700'>{_tq_pv}</span>"
                        )
                    if _vlabel and _vcolor:
                        _badges.append(
                            f"<span style='color:{_vcolor};font-weight:600'>"
                            f"{_vlabel}</span>"
                        )
                    if _urg == "High":
                        _badges.append("🔴 urgent")
                    if _crm_n:
                        _badges.append(f"🤝{_crm_n}")
                    if _has_t:
                        _badges.append("📄 tailored")
                    _badge_str = "  ·  ".join(_badges) if _badges else ""
                    st.markdown(
                        f"**{_co}** — {_ti}  ·  fit **{_fit}/10**  "
                        f"{('· ' + _badge_str) if _badge_str else ''}",
                        unsafe_allow_html=True,
                    )
                    _tq_bridge = extract_bridge(_j)
                    if _tq_bridge:
                        st.caption(f"\U0001f517 {_tq_bridge}")
                    render_tailor_action_row(
                        _j, key_prefix="today_q", tracker_data=tr,
                        tracker_path=TRACKER,
                    )

            if _today_followups:
                st.markdown(
                    f"#### 🟡 Follow up · {min(len(_today_followups), 5)}"
                    + (f" of {len(_today_followups)}"
                       if len(_today_followups) > 5 else "")
                )
                for _j in _today_followups[:5]:
                    _co = _j.get("company", "?")
                    _ti = _j.get("title", "?")[:80]
                    _reason = _j.get("_followup_reason", "")
                    _tq_log = _j.get("outreach_log") or []
                    _tq_touch_n = len(_tq_log)
                    _tq_cadence = (_j.get("followup_schedule") or {}).get("cadence_days") or [3, 10, 21]
                    _tq_ctx = f"touch {_tq_touch_n} of [{','.join(str(d) for d in _tq_cadence)}]d"
                    if _tq_log:
                        _tq_last_d = parse_date(_tq_log[-1].get("date"))
                        if _tq_last_d:
                            _tq_ctx += f" · last {(today - _tq_last_d).days}d ago"
                    st.markdown(
                        f"**{_co}** — {_ti}  ·  _{_reason}_"
                    )
                    st.caption(_tq_ctx)

            if _today_reach_out:
                st.markdown(f"#### 🤝 Reach out · {len(_today_reach_out)}")
                for _crec in _today_reach_out:
                    _name = _crec.get("firm") or _crec.get("name") or "?"
                    _action = _crec.get("next_action") or "—"
                    st.markdown(
                        f"**{_name}** — {(_crec.get('firm_type') or '').replace('_',' ')}  ·  "
                        f"_next action: {_action[:140]}_"
                    )
                st.caption(
                    "→ Navigate to 🤝 Recruiter CRM to log outreach."
                )

        # Tailor drawer — opens whenever a queue/Kanban Tailor button was
        # clicked. Stays open across reruns until user dismisses or marks
        # applied. Inline (not a modal) so the page state isn't lost.
        render_tailor_drawer(jobs, tr, TRACKER)
        st.markdown("")  # tiny breather before campaign progress

    # ── Quick actions ──
    _dash_key_ok = api_key.is_key_valid()
    _dash_gmail_ok = gmail_ui.is_connected()
    _dash_can_run_llm = _dash_key_ok and not pipeline_running
    _last = st.session_state.get("_last_launch")
    if _last:
        _banner_run = next((r for r in active_runs if r["run_id"] == _last["run_id"]), None)
        if _banner_run:
            _bc = st.container()
            with _bc:
                st.info(
                    f"🟡 **{_last['label']}** is running — pid {_banner_run['pid']} · "
                    f"{human_elapsed(_banner_run['started_at'])} elapsed. "
                    f"Go to **🎯 Pipeline** to see live output and stop it.",
                    icon="🚀",
                )
        else:
            # Run finished — clear the banner
            del st.session_state["_last_launch"]

    # Blocker banners — surface BEFORE Quick Actions so the user knows why
    # buttons are disabled instead of clicking and getting silence. Mirrors
    # the Pipeline page's gold-standard `st.error` block (line ~4450).
    if not _dash_key_ok:
        st.error(
            "**🔑 API key missing or invalid** — scoring, nightly refresh, "
            "and tailor all require a working Anthropic key. "
            "Open the **sidebar → Manage Anthropic API key** expander, "
            "paste your `sk-ant-...` key, and hit Save & validate. "
            "Scraping and Gmail fetch work without a key.",
            icon="🔑",
        )
    if not _dash_gmail_ok:
        st.info(
            "**📬 Gmail not connected** — Pull Gmail alerts and Outcome Inbox "
            "need a Gmail OAuth/app-password setup. "
            "Open the **sidebar → Gmail** section to connect.",
            icon="📬",
        )
    if any_work_active and active_runs:
        _aw_run = active_runs[0]
        st.warning(
            f"⏳ **{_aw_run.get('label', 'job')}** is running "
            f"({human_elapsed(_aw_run.get('started_at'))}) — "
            "launch buttons are disabled until it finishes. "
            "Go to **🎯 Pipeline** to view live output or stop it.",
            icon="⚠️",
        )

    with st.container(border=True):
        st.markdown("#### ⚡ Quick actions")
        qa1, qa2, qa3, qa4, qa5 = st.columns([2, 2, 2, 2, 2])
        _dash_scrape_age_h = _web_scan_age_hours()
        _dash_scrape_fresh = _dash_scrape_age_h is not None and _dash_scrape_age_h < 24
        _counts = _target_counts()
        with qa1:
            _help_core = (f"Scrape the {_counts['core']} core targets (no expansion "
                          "list). ~15-30 min. Writes scan_<date>.json only; no LLM "
                          "call until you score. No API key needed.")
            if st.button(f"🛰 Core scrape ({_counts['core']})", width='stretch',
                          disabled=bool(pipeline_running or any_work_active) or _dash_scrape_fresh,
                          help=_help_core, key="dash_qa_core"):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable,
                    str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "core",
                    "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Core scrape"}
                st.toast("🛰 Core scrape launched!", icon="🚀")
                st.rerun()
            _help_full = (f"Scrape ALL {_counts['full']} targets — the {_counts['core']} "
                          f"core companies plus the {_counts['expansion']}-company expansion "
                          "list (mid banks, insurers, hedge funds, fintechs, regulators). "
                          "~20-40 min. Writes scan_<date>.json only; no LLM call until "
                          "you score. No API key needed.")
            if st.button(f"🌐 Full scrape ({_counts['full']})", width='stretch',
                          disabled=bool(pipeline_running or any_work_active) or _dash_scrape_fresh,
                          help=_help_full, key="dash_qa_full"):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable,
                    str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "full",
                    "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Full scrape"}
                st.toast("🌐 Full scrape launched!", icon="🚀")
                st.rerun()
            if _dash_scrape_fresh:
                st.caption(f"🟢 Scan is {_dash_scrape_age_h:.0f}h old")
        with qa2:
            _dash_gmail_age_h = _latest_glob_age_hours("scan_gmail_*.json")
            _dash_gmail_fresh = _dash_gmail_age_h is not None and _dash_gmail_age_h < 1
            _help_gmail = (
                "Pull LinkedIn/Indeed job alert emails from the last 14 "
                "days. ~10-30s. Doesn't call the API. Produces "
                "scan_gmail_<stamp>.json that you can score or promote."
            )
            if _dash_gmail_fresh:
                _help_gmail += (f" ⚠️ Last fetch {_dash_gmail_age_h*60:.0f}m ago — "
                                "likely no new mail.")
            if st.button("📬 Pull Gmail alerts", width='stretch',
                          disabled=(not _dash_gmail_ok) or bool(any_work_active),
                          help=_help_gmail, key="dash_qa_gmail"):
                rec = scan_runner.start_run("gmail_fetch", [
                    sys.executable,
                    str(ROOT / "automation" / "gmail_fetch.py"),
                    "--days", "30",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Gmail fetch"}
                st.toast("📬 Gmail fetch launched!", icon="🚀")
                st.rerun()
            if not _dash_gmail_ok:
                st.caption("🔌 Connect Gmail in the sidebar.")
            elif _dash_gmail_fresh:
                st.caption(f"⚠️ Fetched {_dash_gmail_age_h*60:.0f}m ago")
        with qa3:
            _dash_brief_today = _today_brief_exists()
            _help_nightly = ("Scrape + find new roles since last scan + "
                              "score only those + emit top-3 brief. "
                              "Cheap (~$0.03), ~25 min. Needs API key.")
            if _dash_scrape_fresh:
                _help_nightly += (f" ⚠️ Scan is only {_dash_scrape_age_h:.0f}h old — "
                                   "scrape step will likely find nothing new.")
            if _dash_brief_today:
                _help_nightly += " ⚠️ Today's brief already exists — will overwrite."
            if st.button("🌅 Nightly refresh", width='stretch',
                          disabled=(not _dash_can_run_llm) or bool(any_work_active),
                          help=_help_nightly, key="dash_qa_nightly"):
                nightly_cmd_list = [sys.executable, str(ROOT / "automation" / "nightly_refresh.py")]
                rec = scan_runner.start_run("nightly_refresh", nightly_cmd_list)
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Nightly refresh"}
                st.toast("🌅 Nightly refresh launched!", icon="🚀")
                st.rerun()
            if not _dash_key_ok:
                st.caption("🔑 Set API key in the sidebar.")
            elif _dash_scrape_fresh:
                st.caption(f"⚠️ Scan {_dash_scrape_age_h:.0f}h old — scrape will be a no-op")
            elif _dash_brief_today:
                st.caption("⚠️ Today's brief exists — will overwrite")
        with qa4:
            _help_pipe = ("Go to the 🎯 Pipeline page to configure and launch "
                          "a full end-to-end run (choose scrape strategy, "
                          "sector/company filter, scorer concurrency, etc.)")
            st.markdown(
                "<div style='padding-top:6px'></div>", unsafe_allow_html=True)
            st.caption(_help_pipe)
        with qa5:
            # At-a-glance data freshness so the user can gauge whether they
            # even NEED to re-scrape. Mirrors the Pipeline-page header but
            # compacted to a single cell.
            # jd_scraper writes scan_YYYYMMDD.json; earlier runs sometimes
            # produced scan_v4.json. Glob both, exclude scored/gmail/checkpoint.
            _ds_web = sorted([f for f in OUT_DIR.glob("scan_*.json")
                                if "_scored" not in f.name
                                and "scan_gmail_" not in f.name
                                and "scan_checkpoint" not in f.name],
                              key=lambda p: p.stat().st_mtime, reverse=True)
            _ds_gm = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                             key=lambda p: p.stat().st_mtime, reverse=True)

            def _age(p):
                if not p:
                    return "—"
                age = datetime.now().timestamp() - p.stat().st_mtime
                if age < 3600:
                    return f"{int(age/60)}m ago"
                if age < 86400:
                    return f"{int(age/3600)}h ago"
                return f"{int(age/86400)}d ago"

            st.markdown(f"**Web scan:** {_age(_ds_web[0] if _ds_web else None)}")
            st.markdown(f"**Gmail pull:** {_age(_ds_gm[0] if _ds_gm else None)}")
    st.markdown("")

    # Gmail trash panel: only renders if the most recent scan_gmail_*.json
    # has UIDs that haven't been moved to Trash yet. Lives right under
    # Quick Actions so a freshly-pulled scan surfaces the cleanup prompt
    # at the natural next-step location.
    render_gmail_trash_panel()

    # Latest outputs — JSON + xlsx download per artifact (scrape, gmail,
    # worklist pool, scored, promote). Surfaced on Dashboard so the user
    # doesn't have to bounce to Pipeline ▸ History.
    render_latest_outputs_row(key_prefix="dash")

    _pipeline_live_panel()

    _sp = load_scorer_progress()
    _scorer_live = bool(_sp and _sp.get("state") == "running")
    if _scorer_live:
        cur = _sp.get("current", 0); tot = _sp.get("total", 0) or 1
        frac = min(1.0, cur / tot)
        st.progress(
            frac,
            text=(
                f"🤖 Scoring {cur}/{tot} · "
                f"elapsed {_fmt_eta(_sp.get('elapsed_sec'))} · "
                f"ETA {_fmt_eta(_sp.get('eta_sec'))} · "
                f"apply_now={(_sp.get('verdict_counts') or {}).get('apply_now', 0)}"
            ),
        )
    elif pipeline_running:
        st.info(
            f"🎯 Pipeline `{pipe['pipeline_id']}` running · "
            f"elapsed {human_elapsed(pipe['started_at'])} — "
            f"jump to Pipeline to watch stages.",
            icon="⚡",
        )
    elif pipe and pipe.get("state") == "finished":
        st.caption(
            f"✅ Last pipeline `{pipe['pipeline_id']}` "
            f"finished {fmt_dt(pipe.get('finished_at'))} · "
            f"Inspect tab on Pipeline for results."
        )

    if not _brief_is_today:
        # No today brief — clear call to action
        _brief_age_msg = ""
        if _brief_now and _brief_date_raw_top:
            try:
                _bd = datetime.strptime(_brief_date_raw_top, "%Y%m%d").date()
                _days_old = (date.today() - _bd).days
                _brief_age_msg = f" (last brief: {_days_old}d ago)"
            except ValueError:
                pass
        elif not _brief_now:
            _brief_age_msg = " — no brief on file yet"
        st.info(
            f"No brief for today{_brief_age_msg}. "
            "Hit **🌅 Nightly refresh** above to generate today's picks.",
            icon="🌅",
        )
        st.markdown("---")

    _camp_start_str = meta.get("campaign_start", "2026-05-03")
    _camp_end_str   = meta.get("campaign_end", "2026-07-12")
    try:
        _camp_start = datetime.strptime(_camp_start_str, "%Y-%m-%d").date()
        _camp_end   = datetime.strptime(_camp_end_str,   "%Y-%m-%d").date()
        _camp_total = max((_camp_end - _camp_start).days, 1)
        _camp_done  = max(min((today - _camp_start).days, _camp_total), 0)
        _camp_pct   = int(_camp_done / _camp_total * 100)
        _camp_left  = max((_camp_end - today).days, 0)
    except Exception:
        _camp_pct = 0; _camp_left = 0

    # Pipeline funnel — quick glance at jobs in each active stage
    _stage_counts = {}
    _ACTIVE_STAGES = ["Tailoring", "Applied", "Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite", "Offer"]
    for _j in jobs:
        _s = _j.get("status", "")
        if _s in _ACTIVE_STAGES:
            _stage_counts[_s] = _stage_counts.get(_s, 0) + 1

    _cprog_col, _funnel_col = st.columns([1, 1], gap="large")
    with _cprog_col:
        with st.container(border=True):
            st.markdown("##### 📅 Campaign Progress")
            st.progress(_camp_pct / 100, text=f"{_camp_pct}% · {_camp_left} days remaining")
            st.caption(
                f"{_camp_start_str} → {_camp_end_str}  ·  "
                f"Week {(_camp_done // 7) + 1} of {(_camp_total // 7) + 1}"
            )
    with _funnel_col:
        with st.container(border=True):
            st.markdown("##### 🔽 Active Pipeline")
            if _stage_counts:
                _stage_labels = {
                    "Tailoring": "✍️ Tailoring",
                    "Applied": "📤 Applied",
                    "Recruiter_Screen": "📞 Recruiter",
                    "Phone_Screen": "📱 Phone Screen",
                    "Take_Home": "💻 Take-Home",
                    "Onsite": "🏢 Onsite",
                    "Offer": "🎉 Offer",
                }
                _funnel_parts = []
                for _st_key in _ACTIVE_STAGES:
                    if _st_key in _stage_counts:
                        _funnel_parts.append(
                            f"**{_stage_labels.get(_st_key, _st_key)}** {_stage_counts[_st_key]}"
                        )
                st.markdown("  ·  ".join(_funnel_parts))
            else:
                st.caption("No jobs in active stages yet — apply to get started.")

    # ── 7-day activity strip — lane-split ────────────────────────────────────
    # Stack the daily applied bar by lane so a glance shows the week's lane mix.
    # Each PRIMARY lane (ALM / Validation / Vendor / Quant — see LANE_LABELS) is
    # shown distinctly; CON / unmapped / no-variant fall to "Other". (Previously
    # this mislabeled VAL as "Vendor" and hid VEN/QUANT entirely.)
    import altair as _alt_strip
    _act_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    _LANE_STRIP_ORDER = ["ALM", "Validation", "Vendor", "Quant", "Other"]
    _LANE_STRIP_COLOR = {"ALM": _C_INDIGO, "Validation": _C_BLUE,
                         "Vendor": _C_AMBER, "Quant": _C_GREEN, "Other": _C_SLATE}

    def _lane_label(pv) -> str:
        return LANE_LABELS.get((pv or "").upper(), "Other")

    _act_applied: dict[tuple, int] = {(d, lane): 0 for d in _act_days
                                      for lane in _LANE_STRIP_ORDER}
    _act_outreach = {d: 0 for d in _act_days}
    for _aj in jobs:
        _ad = parse_date(_aj.get("date_applied"))
        if _ad and _ad in _act_outreach:
            _act_applied[(_ad, _lane_label(_aj.get("primary_variant")))] += 1
        for _ol in (_aj.get("outreach_log") or []):
            _od = parse_date(_ol.get("date"))
            if _od and _od in _act_outreach:
                _act_outreach[_od] += 1
    with st.container(border=True):
        _total_app = sum(_act_applied.values())
        _total_out = sum(_act_outreach.values())
        st.markdown(f"##### 📆 Last 7 days — **{_total_app}** applied · "
                    f"**{_total_out}** outreach")
        _strip_df = pd.DataFrame([
            {"day": _dd.strftime("%a %d"), "lane": _lane, "n": _act_applied[(_dd, _lane)],
             "order": _LANE_STRIP_ORDER.index(_lane)}
            for _dd in _act_days for _lane in _LANE_STRIP_ORDER
        ])
        _strip_chart = (
            _alt_strip.Chart(_strip_df)
            .mark_bar()
            .encode(
                x=_alt_strip.X("day:N", title=None, sort=None),
                y=_alt_strip.Y("n:Q", title="Applied", stack="zero"),
                color=_alt_strip.Color("lane:N", title="Lane",
                    scale=_alt_strip.Scale(
                        domain=_LANE_STRIP_ORDER,
                        range=[_LANE_STRIP_COLOR[l] for l in _LANE_STRIP_ORDER])),
                order=_alt_strip.Order("order:Q", sort="ascending"),
                tooltip=["day:N", "lane:N", "n:Q"],
            )
            .properties(height=140)
        )
        st.altair_chart(_strip_chart, use_container_width=True)
        st.caption(" · ".join(
            f"**{_dd.strftime('%a')}** {sum(_act_applied[(_dd, l)] for l in _LANE_STRIP_ORDER)}a / {_act_outreach[_dd]}o"
            for _dd in _act_days
        ))

    st.markdown("---")

    # ── Attention queue ──
    def _tailor_safe_dash(s: str, cap: int | None = None) -> str:
        out = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
        return out[:cap] if cap else out

    def _tailor_draft_exists(company: str, title: str) -> bool:
        sc = _tailor_safe_dash(company, None)
        sr = _tailor_safe_dash(title, 60)
        if not sc or not sr:
            return False
        matches = list(OUT_DIR.glob(f"{sc}_{sr}_*.md"))
        return any(not p.name.endswith("_prompt.md") for p in matches)

    # All five "needs attention" buckets exclude archived rows — an archived
    # Tier-1/high-score Found row must not nag the user (doc §339), matching
    # the Phase-3D honored-archive loop elsewhere on this page.
    def _att_active(j) -> bool:
        return (j.get("status") in ("Found", "Watch")
                and not j.get("archived", False))

    tier1_no_draft = [
        j for j in jobs
        if j.get("tier") == 1
        and _att_active(j)
        and not _tailor_draft_exists(j.get("company", ""), j.get("title", ""))
    ]

    # Bucket 2 — Tier-1 Found with CRM contact at the same company
    tier1_warm_intro = []
    for j in jobs:
        if j.get("tier") != 1 or not _att_active(j):
            continue
        contacts = crm_contacts_at_company(crm, j.get("company", ""))
        if contacts:
            tier1_warm_intro.append((j, contacts))

    # Bucket 3 — High-scored (≥7) with missing JD signal
    # Use fit_notes length as a proxy when _jd_len isn't persisted
    high_score_thin_jd = [
        j for j in jobs
        if int(j.get("fit_score_numeric") or 0) >= 7
        and _att_active(j)
        and len(j.get("fit_notes", "") or "") < 80
    ]

    # Bucket 4 — Scoring errors (fit_score_numeric=0 on Found/Watch)
    scoring_errors = [
        j for j in jobs
        if int(j.get("fit_score_numeric") or 0) == 0
        and _att_active(j)
        and j.get("tier", 4) <= 2  # only flag top-tier broken entries
    ]

    # Bucket 5 — Missing primary_variant (pre-variant-upgrade entries)
    missing_variant = [
        j for j in jobs
        if _att_active(j)
        and j.get("tier", 4) == 1
        and not j.get("primary_variant")
    ]

    attention_total = (len(tier1_no_draft) + len(tier1_warm_intro)
                        + len(high_score_thin_jd) + len(scoring_errors)
                        + len(missing_variant))

    if attention_total:
        st.subheader(f"🎯 Needs your attention ({attention_total})")
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        ac1.metric("📄 Need draft", len(tier1_no_draft),
                   help="Tier-1 roles in Found/Watch without a jd_tailor output yet.")
        ac2.metric("⚡ Warm intro", len(tier1_warm_intro),
                   help="Tier-1 roles at companies where you have CRM contacts — "
                        "reach out before applying cold.")
        ac3.metric("⚠ Thin JD", len(high_score_thin_jd),
                   help="High-scored roles (≥7) where scoring had little JD text. "
                        "Consider rescoring or verifying the JD live.")
        ac4.metric("🔧 Rescore", len(scoring_errors),
                   help="Top-tier tracker entries with fit_score_numeric=0 — "
                        "scoring errored. Rerun fit_scorer.")
        ac5.metric("📌 Missing variant", len(missing_variant),
                   help="Tier-1 roles from before the resume-variants feature. "
                        "Rescore to populate primary_variant.")

        # Tier-1 needing draft — most actionable
        if tier1_no_draft:
            with st.expander(f"📄 Tier-1 needing draft ({len(tier1_no_draft)}) — "
                              "tailor runs cost ~$0.15 each", expanded=False):
                tdf = pd.DataFrame([{
                    "id": j.get("id", ""),
                    "company": j.get("company", ""),
                    "title": j.get("title", "")[:70],
                    "variant": j.get("primary_variant", "—"),
                    "fit": j.get("fit_score_numeric", 0),
                    "url": j.get("url", ""),
                } for j in tier1_no_draft[:20]])
                st.dataframe(tdf, hide_index=True, width='stretch',
                              column_config={"url": st.column_config.LinkColumn("open")})
                _td_key = api_key.is_key_valid()
                td_pick = st.selectbox("Tailor which role?",
                                        [j.get("id") for j in tier1_no_draft],
                                        key="attention_tailor_pick")
                if st.button("✏️ Run tailor now", key="attention_tailor_btn",
                              disabled=not _td_key,
                              width='content'):
                    cmd = [sys.executable,
                           str(ROOT / "automation" / "resume_agent.py"),
                           "--job-id", td_pick, "--tier", _resume_tier()]
                    rec = scan_runner.start_run(f"resume_{td_pick}", cmd)
                    st.success(f"Tailor started (`{rec.run_id}`). "
                               "Draft will land in outputs/ in ~60s.")

        # Warm-intro opportunities
        if tier1_warm_intro:
            with st.expander(f"⚡ Warm-intro opportunities ({len(tier1_warm_intro)}) — "
                              "70% of Director hiring is referral-driven",
                              expanded=False):
                for j, contacts in tier1_warm_intro[:10]:
                    with st.container(border=True):
                        cols = st.columns([3, 1])
                        cols[0].markdown(
                            f"**{j.get('company', '')}** — {j.get('title', '')}"
                            f"  \n_Tier {j.get('tier', '?')} · fit {j.get('fit_score_numeric', 0)}/10"
                            f" · variant {j.get('primary_variant') or '—'}_"
                        )
                        contact_lines = []
                        for c in contacts[:3]:
                            if c["_kind"] == "recruiter":
                                contact_lines.append(
                                    f"  • **{c.get('firm', '?')}** ({c.get('firm_type', '')}) "
                                    f"— last touch: {c.get('last_touchpoint', 'never')}"
                                )
                            else:
                                contact_lines.append(
                                    f"  • **{c.get('name', '?')}** at "
                                    f"{c.get('current_firm', '?')} "
                                    f"— {c.get('relationship', '')}"
                                )
                        cols[0].markdown("\n".join(contact_lines))
                        cols[1].link_button("🔗 Open JD", j.get("url", ""),
                                             width='stretch')

        # Other buckets — combined, lower priority
        other_n = len(high_score_thin_jd) + len(scoring_errors) + len(missing_variant)
        if other_n:
            with st.expander(f"⚙ Scoring / data issues ({other_n})"):
                if high_score_thin_jd:
                    st.markdown(f"**⚠ Thin JD** ({len(high_score_thin_jd)}) — "
                                "these were scored on title/short text; consider rescoring:")
                    thin_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "fit": j.get("fit_score_numeric", 0),
                        "url": j.get("url", ""),
                    } for j in high_score_thin_jd[:10]])
                    st.dataframe(thin_df, hide_index=True, width='stretch',
                                  column_config={"url": st.column_config.LinkColumn()})
                if scoring_errors:
                    st.markdown(f"**🔧 Scoring errors** ({len(scoring_errors)}) — "
                                "fit_score_numeric=0 (LLM call failed or cache poisoned):")
                    err_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "url": j.get("url", ""),
                    } for j in scoring_errors[:10]])
                    st.dataframe(err_df, hide_index=True, width='stretch',
                                  column_config={"url": st.column_config.LinkColumn()})
                if missing_variant:
                    st.markdown(f"**📌 Missing variant** ({len(missing_variant)}) — "
                                "pre-variant-upgrade; rescore to populate:")
                    mv_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "tier": j.get("tier"),
                    } for j in missing_variant[:10]])
                    st.dataframe(mv_df, hide_index=True, width='stretch')

        st.markdown("---")

    # ── Pipeline health ──
    scan_p = latest_scan()
    scored_p = latest_scored()
    scan_age_days = None
    scored_age_days = None
    scan_zero_cos: list[str] = []
    scan_total_results: int | None = None
    scan_total_companies: int | None = None
    scored_verdicts: dict = {}
    scored_errors = 0
    if scan_p:
        try:
            scan_age_days = (datetime.now() - datetime.fromtimestamp(
                scan_p.stat().st_mtime)).days
            d = json.loads(scan_p.read_text(encoding="utf-8"))
            scan_total_results = len(d.get("results", []))
            scan_total_companies = d.get("companies_scanned")
            scan_zero_cos = (d.get("diagnostics") or {}).get("zero_result_companies") or []
        except Exception:
            pass
    if scored_p:
        try:
            scored_age_days = (datetime.now() - datetime.fromtimestamp(
                scored_p.stat().st_mtime)).days
            sd = json.loads(scored_p.read_text(encoding="utf-8"))
            for r in sd.get("results", []):
                v = (r.get("fit") or {}).get("fit_verdict", "?")
                scored_verdicts[v] = scored_verdicts.get(v, 0) + 1
            scored_errors = scored_verdicts.get("error", 0)
        except Exception:
            pass

    health_issues = []
    if scan_age_days is None:
        health_issues.append("⚫ No scan on file — run the pipeline.")
    elif scan_age_days >= 7:
        health_issues.append(f"🔴 Scan is **{scan_age_days}d old** — run nightly refresh.")
    elif scan_age_days >= 2:
        health_issues.append(f"🟡 Scan is {scan_age_days}d old — consider refreshing.")
    if scored_errors >= 10:
        health_issues.append(
            f"🔴 **{scored_errors} scoring errors** in the latest run — "
            "check API key / credits."
        )
    zero_frac = (len(scan_zero_cos) / scan_total_companies) if scan_total_companies else 0
    if zero_frac > 0.3:
        health_issues.append(
            f"🟡 {len(scan_zero_cos)}/{scan_total_companies} companies "
            f"returned 0 candidates ({zero_frac:.0%}) — some ATS adapters "
            "may be down."
        )

    if health_issues:
        st.subheader("📊 Pipeline health")
        hc1, hc2, hc3, hc4 = st.columns(4)
        hc1.metric("Scan age",
                   f"{scan_age_days}d" if scan_age_days is not None else "—",
                   delta=None if scan_age_days is None else (
                       "fresh" if scan_age_days == 0 else f"-{scan_age_days}d"
                   ))
        hc2.metric("Scored age",
                   f"{scored_age_days}d" if scored_age_days is not None else "—")
        hc3.metric("Scan roles", scan_total_results or "—",
                   help=f"{scan_total_companies or '—'} companies scanned")
        hc4.metric("Zero-result cos", len(scan_zero_cos),
                   delta=None if not scan_zero_cos else f"of {scan_total_companies}",
                   delta_color="inverse")
        for issue in health_issues:
            if "🔴" in issue:
                st.error(issue, icon="⚠️")
            elif "🟡" in issue:
                st.warning(issue, icon="📊")
            else:
                st.info(issue, icon="📊")
        if scan_zero_cos:
            with st.expander(
                f"⚠ {len(scan_zero_cos)} companies returned 0 candidates"
            ):
                try:
                    diag = json.loads(scan_p.read_text(encoding="utf-8"))\
                                .get("diagnostics") or {}
                    per_co = {pc["name"]: pc for pc in (diag.get("per_company") or [])}
                except Exception:
                    per_co = {}
                rows = []
                for name in scan_zero_cos:
                    pc = per_co.get(name, {})
                    rows.append({
                        "company": name,
                        "sector": pc.get("sector", "?"),
                        "has_workday": "✓" if pc.get("has_workday_config") else "",
                        "has_greenhouse": "✓" if pc.get("has_greenhouse_config") else "",
                        "has_phenom": "✓" if pc.get("has_phenom_config") else "",
                        "has_sf": "✓" if pc.get("has_successfactors_config") else "",
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                              width='stretch', height=min(400, 40 + 30 * len(rows)))
        st.markdown("---")



    brief = load_morning_brief()
    if brief:
        brief_date_raw = brief.get("brief_date", "")
        try:
            brief_date_parsed = datetime.strptime(brief_date_raw, "%Y%m%d").date()
        except ValueError:
            brief_date_parsed = None
        top = brief.get("top") or []
        is_stale = brief_date_parsed and (date.today() - brief_date_parsed).days >= 1

        if is_stale:
            # Stale: collapsed expander so it doesn't crowd the page
            _days_old = (date.today() - brief_date_parsed).days if brief_date_parsed else "?"
            _brief_outer = st.expander(
                f"🌅 Fresh matches · {_days_old}d old — run nightly refresh to update"
                f" ({len(top)} match(es))",
                expanded=False,
            )
        else:
            # Today's brief: top picks preview (above) already shows today's
            # entries in compact form, so skip the full rendering here.
            # Only show if there's content NOT already covered by top picks.
            if _brief_is_today and _brief_entries_top:
                # Top picks already rendered above — just add a brief summary line
                _brief_outer = None
            else:
                st.markdown("#### 🌅 Today's fresh matches")
                _brief_outer = st.container()
    else:
        _brief_outer = None

    if brief and _brief_outer is not None:
      with _brief_outer:
        if is_stale:
            st.caption(
                f"⚠ Brief is from `{brief_date_raw}` — run Nightly refresh to update."
            )

        # Distinguish API-failure from genuinely quiet day
        error_count = brief.get("error_count", 0)
        sample_errors = brief.get("sample_errors") or []
        total_scored = brief.get("scored", 0) or 0
        mostly_errors = error_count > 0 and error_count >= max(1, total_scored * 0.5)
        if mostly_errors:
            st.error(
                f"⛔ Brief may be incomplete — {error_count}/{total_scored} roles "
                f"errored during scoring (likely API/credit issue). "
                f"Fix your Anthropic key in the sidebar and re-run the nightly "
                f"refresh.\n\n"
                + ("\n".join(f"• {e[:180]}" for e in sample_errors) if sample_errors else ""),
                icon="🔑",
            )

        if not top:
            if mostly_errors:
                pass  # already showed the error banner
            else:
                st.info(
                    f"No fresh matches in today's delta "
                    f"(triaged {brief.get('triaged', '?')}, scored {brief.get('scored', '?')}, "
                    f"0 actionable). No API errors — this is a genuinely quiet day."
                )
        else:
            st.caption(
                f"Ranked from **{brief.get('total_new', 0)} jobs new since yesterday**. "
                f"Apply to the top 1-2 today."
            )
            for i, r in enumerate(top, 1):
                f = r.get("fit") or {}
                verdict = f.get("fit_verdict", "?")
                badge = "🟢" if verdict == "apply_now" else "🟡"
                fb = freshness_badge(r.get("posted_date"), r.get("found_at"))
                with st.container(border=True):
                    cols = st.columns([6, 1])
                    # Freshness now sits in the header line — first thing you see.
                    header = (
                        f"### {badge} {i}. [{f.get('fit_score', '?')}/10 · "
                        f"Tier {f.get('tier', '?')}] {r.get('company', '')} — "
                        f"{r.get('title', '')}"
                    )
                    if fb and fb != "—":
                        header += f"  \n<span style='font-size:0.85em; opacity:0.9'>{fb}</span>"
                        cols[0].markdown(header, unsafe_allow_html=True)
                    else:
                        cols[0].markdown(header)
                    variants = f.get("applicable_resume_variants") or []
                    variants_str = " · ".join(variants) if variants else "—"
                    cols[0].caption(
                        f"📄 Lead-with: **{variants_str}** · "
                        f"Sector: {r.get('sector', '')} · "
                        f"Source: {r.get('source', '')}"
                    )
                    cols[0].markdown(f"**{f.get('summary', '')}**")
                    reasons = f.get("top_3_reasons") or []
                    if reasons:
                        with cols[0].expander("Why it fits"):
                            for reason in reasons:
                                st.markdown(f"- {reason}")
                            gaps = f.get("skill_gaps") or []
                            if gaps:
                                st.markdown("**Gaps:** " + "; ".join(gaps))
                    with cols[1]:
                        st.link_button("🔗 Open JD", r.get("link", ""),
                                       width='stretch')
                        # Quick-add to tracker button
                        if st.button("➕ Add to tracker", key=f"brief_add_{i}",
                                     width='stretch'):
                            # Generate a tracker id
                            from uuid import uuid4
                            new_id = f"brief-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:6]}"
                            _v = f.get("applicable_resume_variants") or []
                            # Mirror auto_promote / morning_brief: fit_score is
                            # a High/Medium/Low category so the Kanban filter
                            # works; numeric lives in fit_score_numeric.
                            _num = int(f.get("fit_score") or 0)
                            _cat = "High" if _num >= 8 else ("Medium" if _num >= 6 else "Low")
                            new_entry = {
                                "id": new_id,
                                "company": r.get("company", ""),
                                "title": r.get("title", ""),
                                "sector": r.get("sector", ""),
                                "location": r.get("location", ""),
                                "url": r.get("link", ""),
                                "source": r.get("source", ""),
                                "tier": f.get("tier", 3),
                                "fit_score": _cat,
                                "fit_score_numeric": _num,
                                "fit_verdict": verdict,
                                "fit_notes": f.get("summary", ""),
                                "resume_variants": _v,
                                "primary_variant": _v[0] if _v else "",
                                "status": "Found" if verdict == "apply_now" else "Watch",
                                "urgency": "High" if verdict == "apply_now" else "Medium",
                                "date_found": date.today().isoformat(),
                                "next_action": f.get("top_3_reasons", [""])[0][:160] if f.get("top_3_reasons") else "",
                                "followup_schedule": {"next_due": None,
                                                       "cadence_days": [3, 10, 21]},
                            }
                            # Avoid duplicates. Race fix: append under the
                            # mutate_json lock and dedupe against the CURRENT
                            # on-disk tracker (not the stale page-load `tr`),
                            # so a concurrent promote can't be clobbered.
                            from safe_json import mutate_json as _mj  # noqa: WPS433
                            _added = {"ok": False}

                            def _mut_add(t):
                                t.setdefault("jobs", [])
                                if not any(j.get("url") == r.get("link") for j in t["jobs"]):
                                    t["jobs"].append(new_entry)
                                    _added["ok"] = True
                                return t

                            _mj(TRACKER, _mut_add, default={"jobs": [], "meta": {}})
                            load_tracker.clear()
                            if _added["ok"]:
                                st.success(f"Added {new_id} to tracker.")
                                st.rerun()
                            else:
                                st.warning("Already in tracker.")
        st.markdown("---")

    if gmail_ui.is_connected():
        try:
            inbox = _load_inbox_signals(14)
        except Exception as e:
            inbox = []
            st.caption(f"Gmail load failed: {e}")
        alerts = [x for x in inbox if x["kind"] == "alert"]
        recruiters = [x for x in inbox if x["kind"] == "recruiter"]

        _GENERIC_ATS_HOSTS = {
            "myworkdayjobs.com", "workdayjobs.com", "wd3.myworkdayjobs.com",
            "greenhouse.io", "lever.co", "icims.com", "successfactors.com",
            "linkedin.com",
        }
        from urllib.parse import urlparse

        def _registrable(host: str) -> str:
            parts = (host or "").lower().split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return host or ""

        tracker_index: list[dict] = []  # {"job": j, "domains": set, "tokens": set}
        for j in jobs:
            domains: set[str] = set()
            url = j.get("url") or ""
            if url:
                try:
                    host = urlparse(url).hostname or ""
                    reg = _registrable(host)
                    if reg and reg not in _GENERIC_ATS_HOSTS:
                        domains.add(reg)
                except Exception:
                    pass
            name = (j.get("company") or "").lower()
            tokens = {t for t in re.split(r"[^a-z0-9]+", name)
                      if len(t) >= 4 and t not in {"bank", "financial", "canada",
                                                   "canadian", "group", "capital",
                                                   "global", "asset", "management",
                                                   "investments", "pension", "plan"}}
            tracker_index.append({"job": j, "domains": domains, "tokens": tokens})

        def _match_mail_to_tracker(sender_email: str, subject: str) -> list[dict]:
            """Return tracker jobs plausibly related to this email."""
            se = (sender_email or "").lower()
            subj_l = (subject or "").lower()
            hits: list[dict] = []
            for entry in tracker_index:
                if any(se.endswith("@" + d) or se.endswith("." + d)
                       for d in entry["domains"]):
                    hits.append(entry["job"])
                    continue
                if any(tok in subj_l or tok in se for tok in entry["tokens"]):
                    hits.append(entry["job"])
            return hits

        recruiter_matches = [
            (r, _match_mail_to_tracker(r["sender_email"], r["subject"]))
            for r in recruiters
        ]
        matched_n = sum(1 for _, hits in recruiter_matches if hits)

        applied_matches = [
            (r, [j for j in hits if j.get("status") in (
                "Applied", "Recruiter_Screen", "Phone_Screen",
                "Take_Home", "Onsite")])
            for r, hits in recruiter_matches
        ]
        applied_matches = [(r, hs) for r, hs in applied_matches if hs]
        if applied_matches:
            st.warning(
                f"⚡ **{len(applied_matches)} recruiter email(s) match active "
                "applications** — likely status change. Open Kanban to update.",
                icon="📨",
            )

        _inbox_title = (f"📬 Inbox signals (14d) · "
                         f"{len(recruiters)} recruiter · "
                         f"{matched_n} tracker-match · "
                         f"{len(alerts)} alerts")
        with st.expander(_inbox_title, expanded=bool(applied_matches)):
            ic1, ic2, ic3, ic4 = st.columns(4)
            ic1.metric("Recruiter/ATS", len(recruiters))
            ic2.metric("→ match tracker", matched_n,
                       help="Recruiter emails whose sender domain or "
                            "subject matches a role in your tracker.")
            ic3.metric("Job alerts", len(alerts))
            ic4.metric("Total", len(inbox))

            st.markdown("**Recent recruiter mail (likely status changes)**")
            if not recruiters:
                st.caption("Nothing from recruiters in the last 14d.")
            else:
                rec_rows = []
                for r, hits in recruiter_matches[:30]:
                    match_str = ""
                    if hits:
                        match_str = ", ".join(
                            f"{h.get('id', '?')} [{h.get('status', '?')}]"
                            for h in hits[:3]
                        )
                        if len(hits) > 3:
                            match_str += f" (+{len(hits) - 3} more)"
                    rec_rows.append({
                        "date": r["date"],
                        "from": r["sender"],
                        "subject": r["subject"][:80],
                        "tracker_match": match_str or "—",
                        "snippet": r["snippet"][:120],
                    })
                st.dataframe(pd.DataFrame(rec_rows), hide_index=True,
                              width='stretch')
                st.caption("Tip: rows with a `tracker_match` are likely status-change "
                           "signals — open Kanban and move the role accordingly.")
        st.markdown("---")

    with st.expander("📈 Pipeline chart · apply-this-week queue", expanded=False):
        # Phase 6 P0 fix: empty-tracker (fresh clone, no jobs) crashed here
        # because fd was a no-column DataFrame and set_index('status') raised
        # KeyError. Guard explicitly so new users see a graceful empty state.
        status_counts = (jobs_df["status"].value_counts()
                           if "status" in jobs_df.columns else pd.Series())
        status_order = meta.get("status_enum", list(status_counts.index))
        fd = pd.DataFrame(
            [{"status": s, "count": int(status_counts.get(s, 0))}
             for s in status_order]
        )
        if fd.empty or "status" not in fd.columns:
            st.info("No jobs in tracker yet — promote a scored role from "
                    "🎯 Pipeline to populate the chart.")
        else:
            d1, d2 = st.columns([2, 1])
            with d1:
                st.bar_chart(fd.set_index("status"))
            with d2:
                st.dataframe(fd, hide_index=True, width='stretch')

        st.markdown("**🎯 Apply this week**")
        apply_ids = meta.get("kanban_targets_week1", {}).get("apply_this_week", [])
        apply_rows = (jobs_df[jobs_df["id"].isin(apply_ids)]
                       if "id" in jobs_df.columns else pd.DataFrame())
        if not apply_rows.empty:
            cols = [c for c in ["id", "company", "title", "tier",
                                  "fit_score", "url"]
                    if c in apply_rows.columns]
            st.dataframe(apply_rows[cols], hide_index=True, width='stretch',
                         column_config={"url": st.column_config.LinkColumn()})
        else:
            st.caption("No roles flagged for this week.")


# ============================================================================
# ============================================================================
# 📥 OUTCOME INBOX
# ============================================================================
elif page == "📥 Outcome Inbox":
    st.title("📥 Outcome Inbox")
    st.caption(
        "Pending status-transition proposals from Gmail (recruiter replies) "
        "and URL-liveness checks. Accept individually, accept all "
        "high-confidence in bulk, or reject the noise."
    )

    _OI_PROPOSALS_PATH = OUT_DIR / "outcome_proposals.json"

    try:
        from safe_json import read_json as _oi_read, mutate_json as _oi_mutate
    except ImportError:
        # Fallback to plain read if safe_json missing — file may still be
        # readable but we surrender concurrent-safety. Make that visible.
        st.warning("safe_json not importable — proposals may race with the "
                   "scanner. `pip install portalocker`.", icon="⚠️")
        _oi_read = lambda p, default=None: (
            json.loads(Path(p).read_text(encoding="utf-8"))
            if Path(p).exists() and Path(p).read_text(encoding="utf-8").strip()
            else default
        )
        _oi_mutate = None  # type: ignore

    _oi_proposals = _oi_read(_OI_PROPOSALS_PATH, default=[]) or []
    if not isinstance(_oi_proposals, list):
        _oi_proposals = []

    # --- Last-run header ---
    _oi_h1, _oi_h2, _oi_h3 = st.columns([2, 2, 1])
    with _oi_h1:
        if _OI_PROPOSALS_PATH.exists():
            _oi_age = datetime.now().timestamp() - _OI_PROPOSALS_PATH.stat().st_mtime
            if _oi_age < 60:
                _oi_age_lbl = f"{int(_oi_age)}s ago"
            elif _oi_age < 3600:
                _oi_age_lbl = f"{int(_oi_age / 60)}m ago"
            elif _oi_age < 86400:
                _oi_age_lbl = f"{int(_oi_age / 3600)}h ago"
            else:
                _oi_age_lbl = f"{int(_oi_age / 86400)}d ago"
            st.metric("Pending proposals", len(_oi_proposals),
                      help=f"File: {_OI_PROPOSALS_PATH.name}")
            st.caption(f"Last update: {_oi_age_lbl}")
        else:
            st.metric("Pending proposals", 0)
            st.caption("No file yet — pull latest to create it")

    # --- Pull-latest button (Gmail outcome) ---
    _oi_gmail_ok = gmail_ui.is_connected()
    _oi_key_ok = api_key.is_key_valid()
    _oi_can_run = _oi_gmail_ok and _oi_key_ok
    _oi_age_h = _latest_glob_age_hours("runs/gmail_outcome_*.json")
    _oi_fresh = _oi_age_h is not None and _oi_age_h < 2
    with _oi_h2:
        _oi_help = (
            "Runs `automation/gmail_outcome.py --days 7` in the "
            "background. Pulls recruiter emails, classifies via "
            "Haiku, appends new proposals to this list. "
            "~$0.001 per email; capped at $0.20/run."
        )
        if _oi_fresh:
            _oi_help += (f" ⚠️ Last pull {_oi_age_h:.1f}h ago — "
                         "re-running may produce duplicates.")
        if st.button(
            "📥 Pull latest from Gmail",
            type="primary" if _oi_can_run else "secondary",
            disabled=not _oi_can_run,
            width='stretch',
            help=_oi_help,
        ):
            _oi_cmd = [sys.executable,
                       str(ROOT / "automation" / "gmail_outcome.py"),
                       "--days", "7"]
            _oi_rec = scan_runner.start_run("gmail_outcome", _oi_cmd)
            st.toast("📥 gmail_outcome launched!", icon="🚀")
            st.session_state["_oi_last_launch"] = _oi_rec.run_id
            st.rerun()

        if not _oi_gmail_ok and not _oi_key_ok:
            st.caption("🔌 Connect Gmail + API key in sidebar")
        elif not _oi_gmail_ok:
            st.caption("🔌 Connect Gmail in sidebar")
        elif not _oi_key_ok:
            st.caption("🔑 Set API key in sidebar")
        elif _oi_fresh:
            st.caption(f"⚠️ Pulled {_oi_age_h:.1f}h ago")

    with _oi_h3:
        if st.button("🔄 Refresh", width='stretch',
                      help="Re-read the proposals file. Useful right after "
                           "a Gmail pull or url_check finishes."):
            st.rerun()

    # --- If a recent run was launched, tail its log ---
    _oi_last_run_id = st.session_state.get("_oi_last_launch")
    if _oi_last_run_id:
        _oi_status_path = ROOT / "automation" / "outputs" / "runs" / f"{_oi_last_run_id}.json"
        if _oi_status_path.exists():
            try:
                _oi_rec = scan_runner.refresh_state(_oi_status_path)
                _oi_state = _oi_rec.get("state", "?")
                _oi_state_emoji = {"running": "🟡", "finished": "✅",
                                    "failed": "❌", "stopped": "⏹"}.get(_oi_state, "❓")
                with st.expander(
                    f"{_oi_state_emoji} Recent run `{_oi_last_run_id}` · {_oi_state}",
                    expanded=(_oi_state == "running"),
                ):
                    _oi_log = scan_runner.tail_log(_oi_rec.get("log_path", ""), 6000)
                    st.code(_oi_log or "(no output yet)", language="text")
                    if _oi_state == "running":
                        st.caption("↻ refreshing while running (sidebar handles cadence)")
            except Exception:
                pass

    if not _oi_can_run:
        if not _oi_gmail_ok:
            st.info(
                "**Gmail not configured.** Open the sidebar Gmail panel "
                "and save your address + Google app password. The "
                "tracker stays read-only until then; existing proposals "
                "below remain actionable.",
                icon="📬",
            )

    st.markdown("---")

    # --- Empty state ---
    if not _oi_proposals:
        st.success("Inbox is empty — no pending proposals.", icon="📭")
        st.caption(
            "When `gmail_outcome.py` or `url_check.py` runs, new "
            "transition proposals will appear here. Click **Pull latest** "
            "above to scan Gmail now."
        )
        st.stop()

    # --- Bulk actions ---
    _oi_b1, _oi_b2, _oi_b3 = st.columns([2, 2, 2])
    _oi_high_conf = [
        p for p in _oi_proposals
        if int((p.get("evidence") or {}).get("confidence", 0)) >= 8
    ]
    _oi_low_conf = [
        p for p in _oi_proposals
        if int((p.get("evidence") or {}).get("confidence", 0)) < 6
    ]

    with _oi_b1:
        if st.button(
            f"✅ Accept all ≥8 confidence ({len(_oi_high_conf)})",
            disabled=not _oi_high_conf,
            width='stretch',
            help="Apply every proposal whose evidence.confidence >= 8 to "
                 "the tracker. Each transition is backed up + atomic.",
        ):
            from safe_json import mutate_json as _oi_mut2
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = TRACKER.with_suffix(f".bak.{stamp}.json")
            if TRACKER.exists():
                bak.write_text(TRACKER.read_text(encoding="utf-8"),
                                encoding="utf-8")
            _oi_by_id = {p["job_id"]: p for p in _oi_high_conf if p.get("job_id")}
            _oi_terminal = {"Hired", "Withdrawn", "Declined"}
            _oi_changed: list[str] = []

            def _oi_apply(tracker):
                if not isinstance(tracker, dict) or "jobs" not in tracker:
                    return tracker
                for j in tracker["jobs"]:
                    jid = j.get("id")
                    if jid not in _oi_by_id:
                        continue
                    if j.get("status") in _oi_terminal:
                        continue
                    j["status"] = _oi_by_id[jid]["proposed_status"]
                    j["status_changed_by"] = "outcome_inbox_bulk"
                    j["status_changed_on"] = date.today().isoformat()
                    _oi_changed.append(jid)
                return tracker

            _oi_mut2(TRACKER, _oi_apply, default={"jobs": []})

            # Remove accepted proposals from the file
            _oi_accepted_keys = {(p.get("job_id"),
                                  p.get("proposed_status"),
                                  (p.get("evidence") or {}).get("source", ""),
                                  (p.get("evidence") or {}).get("email_id", ""))
                                 for p in _oi_high_conf}
            _oi_mut2(_OI_PROPOSALS_PATH,
                      lambda cur: [
                          p for p in (cur or [])
                          if (p.get("job_id"), p.get("proposed_status"),
                              (p.get("evidence") or {}).get("source", ""),
                              (p.get("evidence") or {}).get("email_id", ""))
                          not in _oi_accepted_keys
                      ],
                      default=[])
            load_tracker.clear()
            st.toast(f"✅ Accepted {len(_oi_changed)} transition(s)", icon="📨")
            st.rerun()

    with _oi_b2:
        if st.button(
            f"🧹 Clear low-confidence noise ({len(_oi_low_conf)})",
            disabled=not _oi_low_conf,
            width='stretch',
            help="Remove proposals with confidence < 6. Marks them as "
                 "reviewed-and-ignored without touching the tracker.",
        ):
            from safe_json import mutate_json as _oi_mut3
            _oi_keep = [p for p in _oi_proposals
                         if int((p.get("evidence") or {}).get("confidence", 0))
                            >= 6]
            _oi_mut3(_OI_PROPOSALS_PATH, lambda cur: _oi_keep, default=[])
            st.toast(f"🧹 Cleared {len(_oi_low_conf)} low-conf proposal(s)",
                      icon="🧼")
            st.rerun()

    with _oi_b3:
        st.metric("Total pending", len(_oi_proposals),
                  help="Includes ALL sources — Gmail + URL check.")

    st.markdown("---")

    # --- Per-row table with action buttons ---
    # We render rows manually rather than st.dataframe so the action
    # buttons sit inline. Capped at 50 rows for render speed; the
    # bulk-accept covers the rest.
    _oi_rows = list(_oi_proposals)
    # Sort: highest confidence first, then most recent evidence.
    _oi_rows.sort(
        key=lambda p: (
            -int((p.get("evidence") or {}).get("confidence", 0)),
            -(0 if not (p.get("evidence") or {}).get("checked_at")
              else hash((p.get("evidence") or {}).get("checked_at", ""))),
        )
    )
    _oi_visible = _oi_rows[:50]
    if len(_oi_rows) > 50:
        st.caption(f"Showing top 50 of {len(_oi_rows)} — use bulk accept "
                    f"to clear the long tail.")

    # Build a tracker-jobs lookup for company name display
    _oi_jobs = (load_tracker() or {}).get("jobs", []) or []
    _oi_job_by_id = {j.get("id"): j for j in _oi_jobs}

    for _oi_idx, _oi_p in enumerate(_oi_visible):
        _oi_jid = _oi_p.get("job_id", "")
        _oi_ev = _oi_p.get("evidence") or {}
        _oi_src_raw = _oi_ev.get("source", "")
        _oi_src = "📥 Gmail" if "gmail_outcome" in _oi_src_raw else (
            "🔗 URL check" if "url_check" in _oi_src_raw else _oi_src_raw or "?"
        )
        _oi_conf = _oi_ev.get("confidence")
        _oi_cur = _oi_p.get("current_status", "?")
        _oi_prop = _oi_p.get("proposed_status", "?")
        _oi_company = (
            _oi_p.get("company")
            or (_oi_job_by_id.get(_oi_jid) or {}).get("company", "")
            or _oi_ev.get("extracted_company", "?")
        )
        _oi_role = (
            _oi_ev.get("extracted_role")
            or (_oi_job_by_id.get(_oi_jid) or {}).get("title", "")
            or "(unknown role)"
        )
        _oi_when = _oi_ev.get("date") or _oi_ev.get("checked_at", "")[:10] or "—"

        with st.container(border=True):
            _oi_c1, _oi_c2, _oi_c3, _oi_c4 = st.columns([4, 3, 1, 2])
            with _oi_c1:
                st.markdown(f"**{_oi_company}** — _{_oi_role[:80]}_")
                _oi_meta_bits = [_oi_src]
                if _oi_when:
                    _oi_meta_bits.append(_oi_when)
                if _oi_conf is not None:
                    _oi_meta_bits.append(f"conf {_oi_conf}/10")
                if _oi_jid:
                    _oi_meta_bits.append(f"`{_oi_jid}`")
                st.caption(" · ".join(_oi_meta_bits))
                if _oi_ev.get("quote"):
                    st.markdown(
                        f"<div style='font-size:12px;opacity:0.85;"
                        f"padding:6px 10px;border-left:2px solid #6366f1;"
                        f"background:rgba(99,102,241,0.08);"
                        f"border-radius:3px;margin:4px 0'>"
                        f"\"{_oi_ev['quote']}\"</div>",
                        unsafe_allow_html=True,
                    )
                if _oi_ev.get("subject"):
                    st.caption(f"📧 {_oi_ev['subject'][:120]}")
                elif _oi_ev.get("url"):
                    st.caption(f"🔗 {_oi_ev['url'][:120]}")
            with _oi_c2:
                st.markdown(f"**Status** `{_oi_cur}` → `{_oi_prop}`")
                st.caption(_oi_p.get("reason", ""))
            with _oi_c3:
                _oi_acc_key = f"_oi_accept_{_oi_idx}_{_oi_jid}"
                if st.button("✅", key=_oi_acc_key,
                              help="Accept this transition — applies to "
                                   "tracker + removes from inbox",
                              width='stretch'):
                    from safe_json import mutate_json as _oi_mut4
                    if not _oi_jid:
                        st.error("Proposal has no job_id; cannot apply.")
                    else:
                        # Backup tracker before write
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        bak = TRACKER.with_suffix(f".bak.{stamp}.json")
                        if TRACKER.exists():
                            bak.write_text(TRACKER.read_text(encoding="utf-8"),
                                            encoding="utf-8")

                        def _oi_apply_one(tracker):
                            if not isinstance(tracker, dict) or "jobs" not in tracker:
                                return tracker
                            for j in tracker["jobs"]:
                                if j.get("id") != _oi_jid:
                                    continue
                                if j.get("status") in {"Hired", "Withdrawn",
                                                         "Declined"}:
                                    return tracker
                                j["status"] = _oi_prop
                                j["status_changed_by"] = "outcome_inbox"
                                j["status_changed_on"] = date.today().isoformat()
                                break
                            return tracker

                        _oi_mut4(TRACKER, _oi_apply_one, default={"jobs": []})

                        # Remove this proposal from the file
                        _oi_my_key = (_oi_jid, _oi_prop, _oi_src_raw,
                                       _oi_ev.get("email_id", ""))

                        def _oi_drop_one(cur):
                            return [p for p in (cur or [])
                                    if (p.get("job_id"),
                                        p.get("proposed_status"),
                                        (p.get("evidence") or {}).get("source", ""),
                                        (p.get("evidence") or {}).get("email_id", ""))
                                    != _oi_my_key]

                        _oi_mut4(_OI_PROPOSALS_PATH, _oi_drop_one, default=[])
                        load_tracker.clear()
                        st.toast(f"✅ {_oi_company}: {_oi_cur} → {_oi_prop}",
                                  icon="📨")
                        st.rerun()
            with _oi_c4:
                _oi_rej_key = f"_oi_reject_{_oi_idx}_{_oi_jid}"
                if st.button("❌ Reject", key=_oi_rej_key,
                              help="Drop this proposal. Tracker unchanged.",
                              width='stretch'):
                    from safe_json import mutate_json as _oi_mut5
                    _oi_my_key = (_oi_jid, _oi_prop, _oi_src_raw,
                                   _oi_ev.get("email_id", ""))

                    def _oi_drop_one(cur):
                        return [p for p in (cur or [])
                                if (p.get("job_id"),
                                    p.get("proposed_status"),
                                    (p.get("evidence") or {}).get("source", ""),
                                    (p.get("evidence") or {}).get("email_id", ""))
                                != _oi_my_key]

                    _oi_mut5(_OI_PROPOSALS_PATH, _oi_drop_one, default=[])
                    st.toast(f"❌ Rejected {_oi_company}", icon="🗑")
                    st.rerun()

    with st.expander("ℹ️  How this works"):
        st.markdown(
            "- **Sources.** Two scripts append to "
            "`automation/outputs/outcome_proposals.json`:\n"
            "  - `automation/gmail_outcome.py` — classifies recruiter "
            "emails into status transitions.\n"
            "  - `automation/url_check.py` — flags dead URLs as `Expired`.\n"
            "  Both writes are atomic + cross-process safe via `safe_json.mutate_json`.\n"
            "- **Accept.** Applies the proposed status, takes a tracker "
            "backup, then removes the proposal from this list.\n"
            "- **Reject.** Removes the proposal only. Tracker untouched.\n"
            "- **Confidence.** Gmail proposals carry an LLM confidence "
            "1-10. URL-check proposals are deterministic (no number; we "
            "treat them as 8 by convention).\n"
            "- **Auto-commit.** Run `gmail_outcome.py --commit` from the "
            "CLI to auto-apply >=9 confidence non-terminal transitions "
            "(Recruiter_Screen / Phone_Screen / Take_Home / Onsite). "
            "Offers + Rejections always wait for your eyes."
        )


# ============================================================================
# 🎯 PIPELINE  — the agentic flow, end-to-end
# ============================================================================
elif page in ("🎯 Pipeline · Refresh", "🎯 Pipeline · Score",
              "🎯 Pipeline · Promote"):
    # v3.2 — the former single Pipeline page is split into 3 sub-pages
    # (Refresh / Score / Promote) selected by the sidebar sub-radio. The
    # preamble (state computation + banner + shared chrome) is identical for
    # all three; `_pipe_view` selects which 2 stage cards render at the
    # dispatcher below. The legacy "🎯 Pipeline" page string resolves to
    # Refresh via the nav back-compat alias.
    _pipe_view = page.rsplit("·", 1)[-1].strip()  # "Refresh" | "Score" | "Promote"
    # The classic-tabs escape hatch is gone; the vertical card layout is the
    # only layout now, split across the 3 views below.
    _view_titles = {
        "Refresh": "🎯 Pipeline · ① Refresh",
        "Score":   "🎯 Pipeline · ② Score",
        "Promote": "🎯 Pipeline · ③ Promote",
    }
    _view_captions = {
        "Refresh": "Pull jobs in (web scrape + Gmail) and build the worklist. "
                   "Stages ① Inputs + ② Worklist.",
        "Score":   "Triage the pool and score fit with the LLM. "
                   "Stages ③ Triage + ④ Scoring.",
        "Promote": "Promote scored roles into the tracker and act on them. "
                   "Stages ⑤ Auto-promote + ⑥ Tracker.",
    }
    st.title(_view_titles.get(_pipe_view, "🎯 Agentic Pipeline"))
    st.caption(_view_captions.get(_pipe_view, ""))

    # ---------- Banner state machine (priority ladder) ---------
    # The single primary CTA, computed every render from on-disk state per
    # `pipeline_redesign.md` § "Banner state machine". Pure function in
    # `pipeline_state.compute_next_action`; this is the Streamlit wrapper.
    # Severity → Streamlit container affordance (st.error/warning/info/success).
    # Post-suppression promotable count, surfaced from the snapshot so the ⑤
    # card headline can show the same figure the banner computes (doc §282/§314).
    # None = couldn't compute (snapshot failed); the ⑤ card falls back then.
    _promotable_n = None
    try:
        from automation import suppressions as _bn_supp  # noqa: WPS433
        try:
            _bn_state = _bn_supp.load_active()
        except Exception:
            _bn_state = {"sectors": [], "companies": []}
        try:
            _bn_recent = _bn_supp.load_recently_expired(window_days=7)
        except Exception:
            _bn_recent = []
        _bn_active_runs = []
        try:
            _bn_active_runs = scan_runner.active_runs()
        except Exception:
            pass
        _bn_snap = pipeline_state.derive_snapshot(
            out_dir=OUT_DIR,
            fit_cache_dir=OUT_DIR / "fit_cache",
            tracker_path=TRACKER,
            suppressions_state=_bn_state,
            suppressions_recently_expired=_bn_recent,
            api_key_valid=api_key.is_key_valid(),
            gmail_connected=gmail_ui.is_connected(),
            active_runs=_bn_active_runs,
        )
        # Success-feedback decay (doc §90): when a commit landed within the
        # last ~10 min, inject the count + age into the snapshot so the chip
        # set surfaces "✅ Promoted N" on top of the next CTA. The commit
        # paths record _promote_feedback = {"count", "ts"} in session_state;
        # we translate that to the snapshot fields the pure function reads.
        _pf = st.session_state.get("_promote_feedback")
        if _pf and _pf.get("ts"):
            try:
                _pf_age_h = (datetime.now() - datetime.fromisoformat(_pf["ts"])).total_seconds() / 3600.0
                if 0 <= _pf_age_h < 0.2:  # 0.2h ≈ 12 min decay window
                    import dataclasses as _dc  # noqa: WPS433
                    _bn_snap = _dc.replace(
                        _bn_snap,
                        recent_promote_count=int(_pf.get("count", 0)),
                        last_promote_age_h=_pf_age_h,
                    )
                else:
                    st.session_state.pop("_promote_feedback", None)  # expired
            except Exception:
                st.session_state.pop("_promote_feedback", None)
        _bn = pipeline_state.compute_next_action(_bn_snap)
        _promotable_n = getattr(_bn_snap, "promotable_count", None)

        # The next-action banner renders ONLY on the ③ Promote view. The
        # snapshot above is still computed on every view because the ⑤
        # Auto-promote card consumes `_promotable_n`; only the visible banner
        # is gated. The Dashboard has its own (richer) Next-Best-Action hero,
        # and Refresh/Score shouldn't be dominated by a promote CTA — so the
        # banner is Promote-only here.
        if _pipe_view == "Promote":
            with st.container(border=True):
                _bn_c1, _bn_c2 = st.columns([5, 2], vertical_alignment="center")
                with _bn_c1:
                    st.markdown(f"### {_bn.icon} {_bn.headline}")
                    if _bn.detail:
                        st.caption(_bn.detail)
                    if _bn.chips:
                        chip_md = "  ".join(
                            f"{c.icon} {c.label}" for c in _bn.chips
                        )
                        st.caption(chip_md)
                with _bn_c2:
                    if _bn.cta_label and st.button(
                        _bn.cta_label, key=f"_banner_cta_{_bn.state}",
                        type="primary", width="stretch",
                    ):
                        _route_banner_cta(_bn.cta_action, _bn_active_runs)
    except Exception as _bn_err:  # noqa: BLE001
        st.caption(f"Banner unavailable: {_bn_err}")

    # ---------- Data freshness + last activity summary ---------
    def _latest_web_scan():
        files = sorted(OUT_DIR.glob("scan_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files
                 if "_scored" not in f.name
                 and "scan_gmail_" not in f.name
                 and "scan_checkpoint" not in f.name]
        return files[0] if files else None

    def _latest_gmail_scan():
        files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def _age_label(p: Path | None) -> str:
        if p is None:
            return "—"
        age_s = datetime.now().timestamp() - p.stat().st_mtime
        if age_s < 3600:
            return f"{int(age_s / 60)}m ago"
        if age_s < 86400:
            return f"{int(age_s / 3600)}h ago"
        return f"{int(age_s / 86400)}d ago"

    _latest_web = _latest_web_scan()
    _latest_gm = _latest_gmail_scan()
    _latest_scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)
    _latest_scored = _latest_scored_files[0] if _latest_scored_files else None

    def _count_rows(p: Path | None) -> int:
        if not p or not p.exists():
            return 0
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return len(d.get("results", []))
        except Exception:
            return 0

    # --- Last activity block: what happened most recently? ---
    # The single most important piece of info on this page: what ran last,
    # did it work, and what should the user do next.
    _last_pipe = latest_pipeline_status()
    _last_runs = scan_runner.list_runs(limit=5)
    _last_run = _last_runs[0] if _last_runs else None

    # Determine the most recent event (pipeline or background run)
    _last_event_time = None
    _last_event_label = None
    _last_event_state = None
    _last_event_detail = ""
    if _last_pipe:
        t = _last_pipe.get("finished_at") or _last_pipe.get("started_at")
        if t:
            _last_event_time = t
            _last_event_label = f"Pipeline ({_last_pipe.get('pipeline_id', '?')})"
            _last_event_state = _last_pipe.get("state", "?")
            stages = _last_pipe.get("stages") or {}
            parts = []
            if stages.get("scrape", {}).get("candidate_count"):
                parts.append(f"scraped {stages['scrape']['candidate_count']}")
            if stages.get("score", {}).get("scored_count"):
                parts.append(f"scored {stages['score']['scored_count']}")
            if not stages:
                cr = _last_pipe.get("crash_reason") or ""
                if "preflight" in cr.lower() or "api" in cr.lower():
                    parts.append("failed at API preflight — key/credits issue")
                elif cr:
                    parts.append(cr[:100])
                else:
                    parts.append("no stages completed")
            _last_event_detail = " · ".join(parts)

    # If the pipeline is live, it IS the latest activity — full stop. Don't
    # let a recently-finished background run (e.g. gmail_fetch) clobber the
    # live pipeline's started_at timestamp; that comparison is apples-to-
    # oranges (started_at vs finished_at) and made the strip lie about state.
    _pipe_is_live = bool(_last_pipe and _last_pipe.get("state") == "running")
    if _last_run and not _pipe_is_live:
        t = _last_run.get("finished_at") or _last_run.get("started_at")
        if t and (not _last_event_time or t > _last_event_time):
            _last_event_time = t
            _last_event_label = _last_run.get("label", "background run")
            _last_event_state = _last_run.get("state", "?")
            _last_event_detail = f"pid {_last_run.get('pid', '?')}"

    # Render last-activity strip
    with st.container(border=True):
        la1, la2, la3 = st.columns([2, 3, 2])
        with la1:
            st.markdown("**Last activity**")
            if _last_event_label:
                _state_icon = {"finished": "✅", "failed": "❌", "running": "🟡",
                               "stale": "⚪", "crashed": "💥", "stopped": "⏹"
                               }.get(_last_event_state or "", "❓")
                st.markdown(f"{_state_icon} **{_last_event_label}**")
                st.caption(f"{_last_event_state} · {fmt_dt(_last_event_time)}")
            else:
                st.caption("No background runs yet — launch one from 🎯 Pipeline.")
        with la2:
            if _last_event_detail:
                st.caption(_last_event_detail)
            # Show file names so user knows what's real
            if _latest_web:
                st.caption(f"📁 Scan: `{_latest_web.name}` ({_age_label(_latest_web)})")
            if _latest_scored:
                st.caption(f"📁 Scored: `{_latest_scored.name}` ({_age_label(_latest_scored)})")
        with la3:
            # The "Next step" hint answers a pull-jobs-in / get-them-scored
            # workflow question ("have I scanned? have I scored?"). On the ③
            # Promote view the user already has scored data and is acting on it —
            # and the Promote-only next-action banner (doc §503) owns "what now?"
            # there. Rendering this hint on Score/Promote duplicated/contradicted
            # that banner, so it's gated to ① Refresh only.
            if _pipe_view == "Refresh":
                # "What to do next" — the key question.
                # Freshness is decided by MTIME, not by filename stem. The pipeline
                # scores the merged worklist (`worklist.json` → `worklist_scored.json`,
                # the v3 worklist contract), so the old `scan_<stamp>` stem is NOT in
                # the scored filename — a stem match falsely reported "not scored yet"
                # even with 512 real LLM scores on disk. A scored artifact is current
                # when it's at least as new as the latest web scan.
                _scored_is_current = False
                if _latest_web and _latest_scored:
                    try:
                        _scored_is_current = (
                            _latest_scored.stat().st_mtime >= _latest_web.stat().st_mtime
                        )
                    except Exception:
                        _scored_is_current = False
                _has_real_scores = False
                if _latest_scored:
                    try:
                        _sd = json.loads(_latest_scored.read_text(encoding="utf-8"))
                        _has_real_scores = bool(_sd.get("stage2_scored"))
                    except Exception:
                        pass

                st.markdown("**Next step**")
                if not _latest_web:
                    st.caption("🔴 No scan — run a scrape first")
                elif not _latest_scored or not _scored_is_current:
                    st.caption(
                        f"🟡 New scan since last score. "
                        f"Run scorer on `{_latest_web.name}`"
                    )
                elif not _has_real_scores:
                    st.caption(
                        "🟡 Only rule-triaged (dry-run) — "
                        "run with API key to get LLM scores"
                    )
                elif _last_event_state == "failed":
                    st.caption("🔴 Last run failed — check error, fix, re-run")
                else:
                    st.caption("🟢 Scan + score complete — review Inspect tab")

    # ---------- Nightly refresh strip (Refresh view only) ----------
    # nightly_refresh.py runs daily at 6:30 AM via Windows Task Scheduler
    # (ApplyAgent_NightlyRefresh) and produces delta_YYYYMMDD.json +
    # brief_YYYYMMDD.json. Surface its last run so the user knows the
    # background loop is alive (or noticed it's stalled). The nightly loop IS
    # the refresh/scrape path, so this strip lives on the ① Refresh view.
    try:
        _delta_files = sorted(OUT_DIR.glob("delta_*.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        _brief_files = sorted(OUT_DIR.glob("brief_*.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        _latest_delta = _delta_files[0] if _delta_files else None
        _latest_brief = _brief_files[0] if _brief_files else None
    except Exception:
        _latest_delta = None
        _latest_brief = None

    if _pipe_view == "Refresh":
      with st.container(border=True):
        nc1, nc2, nc3 = st.columns([2, 3, 2])
        with nc1:
            st.markdown("**Nightly refresh** (6:30 AM daily)")
            if _latest_brief:
                _age_h = (datetime.now().timestamp()
                          - _latest_brief.stat().st_mtime) / 3600
                _icon = "✅" if _age_h < 30 else "⚠️" if _age_h < 72 else "🔴"
                st.markdown(f"{_icon} `{_latest_brief.name}`")
                st.caption(f"{_age_label(_latest_brief)}")
            elif _latest_delta:
                st.caption(f"🟡 delta only — `{_latest_delta.name}` "
                           f"({_age_label(_latest_delta)})")
            else:
                st.caption("⚪ No nightly artifacts found yet.")
        with nc2:
            if _latest_delta:
                try:
                    _dd = json.loads(_latest_delta.read_text(encoding="utf-8"))
                    _new_n = len(_dd.get("new", []) or _dd.get("results", []))
                    st.caption(f"🆕 delta: {_new_n} new role(s) since last score")
                except Exception:
                    pass
            st.caption(
                "scrape (--expansion --gmail) → scan_delta → "
                "morning_brief (--auto-tailor)"
            )
        with nc3:
            st.markdown("**Schedule**")
            st.caption("Windows Task Scheduler · `ApplyAgent_NightlyRefresh`")
            st.caption("Run manually: `schtasks /run /tn ApplyAgent_NightlyRefresh`")
            # 🌅 Full refresh — runs the whole nightly chain NOW (scrape →
            # rebuild → score → brief). Relocated here from the Promote run card
            # (v3.2 strict split): it's the in-app equivalent of the scheduled
            # nightly above, so it belongs on the ① Refresh view beside it.
            # Guards recomputed locally (the run-card locals aren't in scope here).
            _nr_key_ok = api_key.is_key_valid()
            _nr_can_run = not any_work_active
            _nr_scrape_age = _web_scan_age_hours()
            _nr_scrape_fresh = _nr_scrape_age is not None and _nr_scrape_age < 24
            _nr_brief_today = _today_brief_exists()
            _nr_help = ("Scrape → rebuild worklist → score → morning brief. "
                        "~25 min, ~$0.03. Requires API key.")
            if _nr_scrape_fresh:
                _nr_help += (f" ⚠️ Scan is only {_nr_scrape_age:.0f}h old — "
                             "the scrape step will likely find nothing new.")
            if _nr_brief_today:
                _nr_help += " ⚠️ Today's brief already exists — will overwrite."
            if not _nr_key_ok:
                _nr_help += " 🔑 Set an API key in the sidebar first."
            if st.button("🌅 Full refresh now", width="stretch",
                         key="_vc_refresh_full_refresh",
                         disabled=(not _nr_key_ok or not _nr_can_run),
                         help=_nr_help):
                rec = scan_runner.start_run("nightly_refresh", [
                    sys.executable, str(ROOT / "automation" / "nightly_refresh.py"),
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Full refresh"}
                st.toast("🌅 Full refresh launched!", icon="🚀")
                st.rerun()

    if _pipe_view == "Refresh":
        st.markdown("---")

    # ---------- Pause / resume / checkpoint status ----------
    # The scraper drops scan_checkpoint.json after each company and watches for
    # scan_pause.flag. These controls let the user pause a long scrape and
    # resume it later (e.g., after closing the laptop, a reboot, or moving
    # to a personal network for Gmail).
    _ckpt_path = OUT_DIR / "scan_checkpoint.json"
    _pause_path = OUT_DIR / "scan_pause.flag"
    _ckpt = None
    if _ckpt_path.exists():
        try:
            _ckpt = json.loads(_ckpt_path.read_text(encoding="utf-8"))
        except Exception:
            _ckpt = None

    _pause_requested = _pause_path.exists()

    # Determine if a scraper is currently running.
    # A "pipeline" job also runs jd_scraper internally, so treat pipeline_running
    # as scraper-active too — UNLESS --skip-scrape is in its cmd (promote-only).
    def _is_scrape_run(r: dict) -> bool:
        label = r.get("label") or ""
        cmd = r.get("cmd") or []
        if "--skip-scrape" in cmd:
            return False
        return ("jd_scraper" in label or "scrape" in label
                or "pipeline" in label)
    try:
        _scraper_active = pipeline_running or any(
            _is_scrape_run(r) for r in scan_runner.active_runs()
        )
    except Exception:
        _scraper_active = pipeline_running

    # Stale-pause-flag cleanup: if no scraper is running and no checkpoint
    # exists, a leftover scan_pause.flag is orphaned (e.g. the user killed
    # the scraper externally, or a previous run paused, completed, and the
    # cleanup line got skipped). Auto-unlink if the flag is older than 10
    # minutes so the user doesn't see a phantom "paused" panel forever.
    if _pause_requested and not _scraper_active and not _ckpt:
        try:
            if (datetime.now().timestamp() - _pause_path.stat().st_mtime) > 600:
                _pause_path.unlink()
                _pause_requested = False
        except Exception:
            pass

    # Render the scrape panel only when there's something real to show:
    #   - a live scraper (with or without checkpoint/pause flag), or
    #   - a checkpoint to resume (paused state, scraper not running).
    # An orphaned pause flag with no checkpoint and no scraper renders nothing
    # — the cleanup above will eventually remove it.
    # Scrape pause/resume controls are refresh-specific → ① Refresh view only.
    _show_scrape_panel = (
        _pipe_view == "Refresh"
        and (_scraper_active or (_ckpt is not None))
    )
    if _show_scrape_panel:
        with st.container(border=True):
            _section_title = (
                "#### 🟢 Scrape in progress"
                if _scraper_active
                else "#### ⏸ Scrape paused — checkpoint saved"
            )
            st.markdown(_section_title)
            pc = _ckpt or {}
            done = pc.get("completed_count", 0)
            tot = pc.get("total_companies", 0) or 1
            found_so_far = len(pc.get("found", []))
            cx1, cx2, cx3, cx4 = st.columns(4)
            cx1.metric("State",
                       "🔴 running (pause pending)" if (_scraper_active and _pause_requested)
                       else "🟢 running" if _scraper_active
                       else "⏸ paused (checkpoint)" if _ckpt
                       else "⚪ idle")
            cx2.metric("Companies", f"{done}/{tot}" if tot else "—",
                        f"{(done/tot*100):.0f}%" if tot else None)
            cx3.metric("Captured so far", found_so_far)
            cx4.metric("Checkpoint age",
                       human_elapsed(pc.get("updated_at")) if pc.get("updated_at") else "—")

            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                _can_pause = _scraper_active and not _pause_requested
                if st.button("⏸ Request pause", disabled=not _can_pause,
                              width='stretch', key="scrape_pause_btn",
                              help="Creates scan_pause.flag. The scraper checks "
                                   "between companies and exits cleanly after "
                                   "the current one finishes."):
                    _pause_path.parent.mkdir(parents=True, exist_ok=True)
                    _pause_path.write_text(datetime.now().isoformat(), encoding="utf-8")
                    st.success("Pause flag set. Scraper will stop after the "
                                "company it's currently scanning.")
                    st.rerun()
            with bc2:
                _key_ok_resume = api_key.is_key_valid()
                _can_resume = bool(_ckpt) and not _scraper_active and not any_work_active
                if st.button("▶ Resume scrape", disabled=not _can_resume,
                              width='stretch', type="primary",
                              key="scrape_resume_btn",
                              help="Launches jd_scraper.py --resume with the "
                                   "same options as the checkpointed run."):
                    opts = (pc.get("options") or {})
                    cmd = [sys.executable, str(ROOT / "automation" / "jd_scraper.py"),
                           "--resume", "--expansion"]
                    if opts.get("linkedin_only"):
                        cmd.append("--linkedin-only")
                    if opts.get("workday_only"):
                        cmd.append("--workday-only")
                    try:
                        if _pause_path.exists():
                            _pause_path.unlink()
                    except Exception:
                        pass
                    rec = scan_runner.start_run("scrape_resume", cmd)
                    st.success(f"Resumed as `{rec.run_id}`. "
                               "Watch progress on Admin → Runs.")
                    st.rerun()
            with bc3:
                if st.button("🗑 Discard checkpoint",
                              disabled=not bool(_ckpt) or _scraper_active,
                              width='stretch', key="scrape_ckpt_clear_btn",
                              help="Delete the checkpoint file. The next scan "
                                   "starts fresh. Use this if the target list "
                                   "changed or you want to re-scan from scratch."):
                    try:
                        _ckpt_path.unlink()
                        if _pause_path.exists():
                            _pause_path.unlink()
                        st.success("Checkpoint discarded.")
                    except Exception as _e:
                        st.error(f"Could not delete: {_e}")
                    st.rerun()

            # Hard stop — abort the run now (distinct from graceful pause).
            # Safe to use even mid-scrape: a pinned base scan is never
            # overwritten by latest_scan(), so stopping won't lose your pool.
            if _scraper_active:
                try:
                    _active_scrape = next(
                        (r for r in scan_runner.active_runs()
                         if any(t in (r.get("label") or "")
                                for t in ("scrape", "jd_scraper", "pipeline"))),
                        None)
                except Exception:
                    _active_scrape = None
                if _active_scrape:
                    st.markdown("")
                    if st.button("⏹ Stop scrape now (abort)",
                                 width='stretch', type="primary",
                                 key="scrape_hard_stop_btn",
                                 help="Kills the run immediately. Use Pause "
                                      "instead if you want a clean checkpoint. "
                                      "Your pinned base scan is NOT affected."):
                        scan_runner.stop_run(_active_scrape["run_id"])
                        st.warning("⏹ Stop signal sent — the scrape will exit "
                                   "now. Your pinned base is safe.")
                        st.rerun()

            if _pause_requested and _scraper_active:
                st.caption("⏳ Pause requested — waiting for the current company to finish.")
            elif _ckpt:
                st.caption(f"Checkpoint file: `{_ckpt_path}` · signature {_ckpt.get('targets_signature', '?')}")

    # (The old `_stage_card` stepper helper + `stages_info` were superseded by
    # the Pipeline funnel visualization and the per-view stage cards; removed
    # in the v3.2 split as confirmed-dead code.)

    # ---------- Worklist status strip ----------
    # ONE source of truth: worklist.json. Auto-rebuilt by jd_scraper and
    # gmail_fetch when they finish. The user normally never touches the
    # rebuild button — it's there as an escape hatch only.
    _wstatus = worklist.status()
    _wstats = _wstatus.get("stats") or {}
    # The full Worklist card (headline + new-rows + manual-rebuild) renders only
    # on ① Refresh — that's the pool-building page. Score/Promote get the pool's
    # numbers via the funnel + the Scoring-card headline (both read _wstats,
    # computed above), so the card itself would be redundant there. (Deviates
    # from pipeline_redesign.md §495 "renders on all three" — deliberate, per
    # user request to de-duplicate the repeated header.) Uses the same 2-space
    # `if _pipe_view ==` wrap pattern as the nightly-refresh strip to keep the
    # 140-line body un-reindented.
    if _pipe_view == "Refresh":
      with st.container(border=True):
        if _wstatus.get("worklist_exists"):
            # Three states: scoring-in-progress beats scored beats not-scored.
            # When scorer_running is true the progress file shows current/total,
            # so surface that instead of the stale "not yet scored" label.
            if scorer_running:
                _prog = load_scorer_progress() or {}
                _cur = _prog.get("current", 0)
                _tot = _prog.get("total", 0)
                _scored_str = (
                    f"🤖 scoring in progress ({_cur}/{_tot})"
                    if _tot else "🤖 scoring in progress"
                )
            elif _wstatus.get("worklist_scored_exists"):
                _scored_str = "✅ scored"
            else:
                _scored_str = "🟡 not yet scored"
            _new = _wstats.get("new_since_last_score", 0)
            st.markdown(
                f"#### 🎯 Worklist · **{_wstats.get('total', 0)} jobs** "
                f"({_wstats.get('scrape', 0)} 🛰 scrape · "
                f"{_wstats.get('gmail', 0)} 📬 gmail · "
                f"{_wstats.get('both', 0)} 🔁 both) · {_scored_str}"
            )
            _bits = []
            if _new and _wstatus.get("worklist_scored_exists"):
                _bits.append(f"🆕 **{_new} new** since last score")
            _geo_dropped = _wstats.get("gmail_geo_dropped", 0)
            if _geo_dropped:
                _bits.append(f"📍 {_geo_dropped} gmail geo-dropped")
            if _wstatus.get("rebuilt_at"):
                _bits.append(f"rebuilt {_wstatus['rebuilt_at']}")
            if _bits:
                st.caption(" · ".join(_bits))
            st.caption(
                "Worklist = dedup(latest web scrape ∪ rolling 30-day Gmail "
                "harvests). Scorer and promoter read THIS file. "
                "Scrape and Gmail-fetch buttons rebuild it automatically. "
                "'New since last score' = URLs not in the previous scored output "
                "(i.e. the LLM hasn't evaluated them yet)."
            )

            # New-rows expander: when the worklist has been rebuilt with
            # rows that weren't in the previous scoring run, surface the
            # actual rows (company, title, source, URL) — not just the
            # count. The is_new_since_last_score flag is already written
            # by worklist.rebuild() so no schema change is needed.
            if _new and _wstatus.get("worklist_scored_exists"):
                with st.expander(
                    f"🆕 Show the {_new} new row{'s' if _new != 1 else ''} "
                    "since last score",
                    expanded=False,
                ):
                    try:
                        _wl_path = OUT_DIR / "worklist.json"
                        _wl = json.loads(_wl_path.read_text(encoding="utf-8"))
                        _new_rows = [
                            r for r in _wl.get("results", [])
                            if r.get("is_new_since_last_score")
                        ]
                    except Exception as _e:
                        st.caption(f"(could not read worklist.json: {_e})")
                        _new_rows = []
                    if _new_rows:
                        _src_emoji = {"scrape": "🛰", "gmail": "📬", "both": "🔁"}
                        _df_rows = [{
                            "src": _src_emoji.get(r.get("source", ""), "·"),
                            "company": r.get("company", "")[:40],
                            "title": r.get("title", "")[:80],
                            "url": r.get("link", r.get("url", "")),
                        } for r in _new_rows]
                        st.dataframe(
                            pd.DataFrame(_df_rows),
                            hide_index=True, width='stretch',
                            column_config={
                                "url": st.column_config.LinkColumn("open"),
                            },
                            height=min(40 + 36 * len(_df_rows), 340),
                        )
                        st.caption(
                            f"These {_new} row(s) entered the worklist after "
                            "the last scoring run. Re-score to get verdicts "
                            "for them — cached rows pay nothing, only the "
                            "new ones hit the API."
                        )
                    else:
                        st.caption(
                            "(no rows flagged is_new_since_last_score — "
                            "the count may be stale; rebuild the worklist.)"
                        )
        else:
            st.warning(
                "🎯 No worklist yet — run a scrape or Gmail fetch and "
                "the worklist will be built automatically.",
                icon="⚠️",
            )
        # Persistent success banner from the previous Rebuild click.
        # st.rerun() inside the click handler discards any st.success()
        # rendered there, so the user saw nothing happen. Stash the
        # result in session_state and surface it on the next render.
        _last_rebuild = st.session_state.pop("_worklist_rebuild_result", None)
        if _last_rebuild:
            st.success(
                f"✅ Worklist rebuilt: **{_last_rebuild['total']} rows** "
                f"({_last_rebuild['scrape']} 🛰 scrape · "
                f"{_last_rebuild['gmail']} 📬 gmail · "
                f"{_last_rebuild['both']} 🔁 both)"
                + (f" · 🆕 {_last_rebuild['new_since_last_score']} "
                    "new since last score"
                   if _last_rebuild.get("new_since_last_score") else "")
            )

        # Rebuild is normally automatic (scrape + gmail_fetch trigger it).
        # The button is an escape hatch only — tucked under an expander so
        # it doesn't compete with primary actions, and disabled while any
        # work is active so the user can't race the scorer.
        with st.expander("⚙️ Advanced — manual rebuild", expanded=False):
            st.caption(
                "The worklist rebuilds automatically after every scrape "
                "and Gmail fetch. Use this only if you hand-edited a "
                "scan_*.json or suspect the worklist is stale."
            )
            if st.button("🔄 Rebuild now",
                          width='stretch',
                          disabled=any_work_active,
                          key="rebuild_worklist_btn",
                          help=("Disabled while another job is running — "
                                "rebuild would race the scorer."
                                if any_work_active else
                                "Rebuild worklist.json from latest scrape + "
                                "rolling 30-day Gmail.")):
                with st.spinner("Rebuilding worklist…"):
                    _rs = worklist.rebuild()
                st.session_state["_worklist_rebuild_result"] = _rs
                st.toast(
                    f"✅ Rebuilt: {_rs['total']} rows "
                    f"({_rs['scrape']}/{_rs['gmail']}/{_rs['both']})",
                    icon="🎯",
                )
                st.rerun()

    # ---------- Funnel data collection ----------
    scan_f = latest_scan()
    scored_f = latest_scored()

    scrape_count = None
    scrape_raw = None
    dedup_dropped_url = dedup_dropped_near = None
    zero_companies: list[str] = []
    per_company_diag: list[dict] = []
    if scan_f:
        try:
            d = json.loads(scan_f.read_text(encoding="utf-8"))
            scrape_count = len(d.get("results", []))
            dedup = d.get("dedup_stats") or {}
            scrape_raw = dedup.get("input", scrape_count)
            dedup_dropped_url = dedup.get("dropped_url", 0)
            dedup_dropped_near = dedup.get("dropped_near", 0)
            diag = d.get("diagnostics") or {}
            zero_companies = diag.get("zero_result_companies") or []
            per_company_diag = diag.get("per_company") or []
        except Exception:
            pass

    score_input = score_pass = score_count = None
    verdict_counts: dict = {}
    if scored_f:
        try:
            d = json.loads(scored_f.read_text(encoding="utf-8"))
            score_input = d.get("total_input")
            score_pass = d.get("stage1_passed")
            score_count = d.get("stage2_scored")
            for r in d.get("results", []):
                fv = (r.get("fit") or {}).get("fit_verdict", "?")
                verdict_counts[fv] = verdict_counts.get(fv, 0) + 1
        except Exception:
            pass

    # Prefer the FRESH standalone triage file for the triage headline
    # numbers (total_input / stage1_passed / stage1_dropped) when the
    # user has clicked 🎯 Run triage more recently than they last
    # scored. The scored snapshot bakes in triage stats from its own
    # run, which can be days stale — the user explicitly hit Run triage
    # to get a CURRENT view of the rule-pass pool. score_count
    # (stage2_scored, LLM verdicts) stays from the scored file —
    # standalone triage doesn't produce verdicts. This is the same
    # preference logic as pipeline_state.derive_snapshot but applied
    # to the variables the funnel + ③ Triage card actually read.
    _ti_path = OUT_DIR / "worklist_triage.json"
    if _ti_path.exists():
        try:
            _ti_mtime = _ti_path.stat().st_mtime
            _sc_mtime = scored_f.stat().st_mtime if scored_f else 0
        except OSError:
            _ti_mtime = _sc_mtime = 0
        if _ti_mtime > _sc_mtime:
            try:
                _td = json.loads(_ti_path.read_text(encoding="utf-8"))
                # Override with fresh numbers; keep score_count
                # (LLM-verdict total) untouched.
                _ti_total = _td.get("total_input")
                _ti_pass = _td.get("stage1_passed")
                if _ti_total is not None:
                    score_input = _ti_total
                if _ti_pass is not None:
                    score_pass = _ti_pass
            except Exception:
                pass

    apply_n = verdict_counts.get("apply_now", 0)
    tailor_n = verdict_counts.get("tailor_and_apply", 0)
    actionable_n = apply_n + tailor_n

    # Exclude archived rows so this "N to review" count matches the Review
    # Queue (which gates `not archived`) — otherwise an archived Found/Watch
    # row inflates the funnel count and the two surfaces disagree (doc §339).
    tracker_found = sum(
        1 for j in jobs
        if j.get("status") in ("Found", "Watch") and not j.get("archived", False)
    )
    tracker_applied = sum(1 for j in jobs if parse_date(j.get("date_applied")))
    tailored_docs = len(list(OUT_DIR.glob("*_prompt.md")))

    # ---------- Funnel visualization ----------
    # Explain what state the pipeline is in, then show the numbers.
    # The funnel reads from the latest scan file + latest scored file, which
    # may be from DIFFERENT runs. Make that explicit.
    _funnel_scan_name = scan_f.name if scan_f else None
    _funnel_scored_name = scored_f.name if scored_f else None
    _scored_matches_funnel_scan = (
        scan_f and scored_f and scan_f.stem in scored_f.name
    )

    # The funnel spans scrape → triage → score → tracker; show it on Refresh
    # (scrape/dedup focus) and Score (triage/coverage focus). Promote stays
    # lean — the ⑤ card's promotable headline already carries the end count.
    if _pipe_view in ("Refresh", "Score"):
      with st.expander(
        f"📊 Pipeline funnel"
        + (f" — `{_funnel_scan_name}`" if _funnel_scan_name else " — no scan")
        + (" 🤖 scoring…" if scorer_running else
           " ✅ scored" if score_count else
           " ⚠️ not scored" if scan_f else ""),
        expanded=True,
    ):
        # ── Cross-stage consistency banner ────────────────────────────
        # Generalises the "scan vs scored file mismatch" warning below
        # using the input-breadcrumb fingerprint written by fit_scorer.
        # Single source of truth for "are triage/scoring numbers current
        # with the worklist?" — see ui.pipeline_state.derive_consistency
        # and the design discussion that motivated input breadcrumbs.
        try:
            _cons = pipeline_state.derive_consistency(OUT_DIR)
            _cons_sev, _cons_head, _cons_detail = \
                pipeline_state.consistency_banner_copy(_cons)
            if _cons_sev == "success":
                st.success(f"✅ {_cons_head}", icon=None)
            elif _cons_sev == "warn":
                st.warning(f"🟠 {_cons_head}\n\n{_cons_detail}", icon=None)
            elif _cons_sev == "info":
                st.info(f"ℹ️ {_cons_head}\n\n{_cons_detail}", icon=None)
        except Exception as _cons_err:
            # Banner failure must not break the funnel. Surface quietly
            # in the error log; users still see the funnel + the older
            # scan-vs-scored warning below as a fallback.
            try:
                error_log.log_error("consistency_banner", _cons_err,
                                    module="ui.app")
            except Exception:
                pass
            _cons = None

        # Legacy fallback: when the consistency banner above couldn't run,
        # keep the old name-prefix mismatch warning so the user still gets
        # SOME drift signal. The consistency banner subsumes this when it
        # works (sha8 matching is strictly more accurate than filename
        # heuristics).
        if _cons is None and _funnel_scan_name and _funnel_scored_name \
                and not _scored_matches_funnel_scan:
            st.warning(
                f"Numbers below mix two files: scan from `{_funnel_scan_name}` "
                f"but scores from `{_funnel_scored_name}`. "
                f"Run the scorer on your latest scan to unify them.",
                icon="⚠️",
            )

        cols = st.columns([3, 1, 3, 1, 3, 1, 3, 1, 3])

        def _big_number(col, emoji, label, value, sub=""):
            col.markdown(f"<div style='text-align:center'>"
                         f"<div style='font-size:1.2em'>{emoji}</div>"
                         f"<div style='font-size:1.4em; font-weight:600; line-height:1.2'>"
                         f"{value if value is not None else '—'}</div>"
                         f"<div style='font-size:0.8em; opacity:0.8'>{label}</div>"
                         f"<div style='font-size:0.7em; opacity:0.6'>{sub}</div>"
                         f"</div>",
                         unsafe_allow_html=True)

        def _arrow(col, label=""):
            col.markdown(f"<div style='text-align:center; padding-top:14px'>"
                         f"<div style='font-size:1.3em; opacity:0.4'>→</div>"
                         f"<div style='font-size:0.7em; opacity:0.7'>{label}</div>"
                         f"</div>",
                         unsafe_allow_html=True)

        # While a scrape is running the scan file isn't written yet — fall back
        # to the checkpoint's live count so the funnel isn't stuck at 0.
        _ckpt_live = None
        if _scraper_active and _ckpt:
            _ckpt_live = len(_ckpt.get("found", []))
        _scraped_display = scrape_raw if scrape_raw else scrape_count if scrape_count else _ckpt_live
        _scraped_sub = (f"across {len(per_company_diag)} cos" if per_company_diag
                        else f"in progress — {_ckpt.get('completed_count',0)}/{_ckpt.get('total_companies','?')} cos"
                        if _ckpt_live is not None else "")
        _big_number(cols[0], "🛰️", "Scraped", _scraped_display,
                    sub=_scraped_sub)
        # Dedup pass rate
        _dedup_in = scrape_raw or scrape_count or 0
        _dedup_out = scrape_count or 0
        _dedup_pct = (f"{int(100*_dedup_out/_dedup_in)}% kept"
                      if _dedup_in else f"-{(dedup_dropped_url or 0) + (dedup_dropped_near or 0)} dupe"
                      if dedup_dropped_url is not None else "")
        _arrow(cols[1], _dedup_pct)
        _big_number(cols[2], "✂️", "Unique", scrape_count,
                    sub=f"-{dedup_dropped_url} URL, -{dedup_dropped_near} near"
                        if dedup_dropped_url is not None else "")
        # Triage pass rate
        _triage_in = score_input or scrape_count or 0
        _triage_out = score_pass or 0
        _triage_pct = (f"{int(100*_triage_out/_triage_in)}% pass"
                       if _triage_in else f"-{_triage_in - _triage_out} off-profile"
                       if score_input and score_pass else "")
        _arrow(cols[3], _triage_pct)
        _big_number(cols[4], "🎯", "Triaged", score_pass,
                    sub="stage-1 pass" if score_pass else
                        ("not scored yet" if scan_f and not scored_f else ""))
        # Triaged → scored: show coverage rate
        _sc_pct = (f"{int(100*(score_count or 0)/(score_pass or 1))}% LLM-scored"
                   if score_pass else "")
        _arrow(cols[5], _sc_pct or (f"-{(score_pass or 0) - (score_count or 0)} err"
                        if score_pass is not None and score_count is not None and score_pass != score_count else ""))

        # Scored column: explain WHY it's blank if it is
        _scored_sub = ""
        if score_count:
            _scored_sub = f"apply_now:{apply_n} tailor:{tailor_n}"
        elif scored_f and not score_count:
            _scored_sub = "dry-run only (rule-triage, no LLM)"
        elif not scored_f and scan_f:
            _scored_sub = "scorer not run yet"
        _big_number(cols[6], "🤖", "Scored", score_count, sub=_scored_sub)

        _arrow(cols[7], f"-{(actionable_n or 0) - tracker_found} pending" if actionable_n else "")
        _big_number(cols[8], "📋", "Tracker",
                    tracker_found if tracker_found else "—",
                    sub=f"{tracker_applied} applied · {tailored_docs} tailored")

        st.caption(
            "Scraped → deduplicated → keyword pre-filter → LLM scored → promoted to tracker."
        )

    # (The "⏱️ Pipeline running" st.info banner was removed: it duplicated the
    # always-visible _pipeline_live_panel() — which renders on all three views
    # with a live log tail + elapsed timer + Stop button — so it was pure
    # redundant chrome.)

    # zero_companies is a SCRAPE diagnostic (which targets returned 0 candidates)
    # → it belongs only on the ① Refresh (pull-jobs-in) view, alongside the other
    # scrape chrome (nightly strip, pause/resume).
    if _pipe_view == "Refresh" and zero_companies:
        with st.expander(f"⚠️ {len(zero_companies)} companies returned 0 candidates — click to inspect"):
            st.caption(
                "These targets produced no candidates. Common causes: "
                "LinkedIn guest search doesn't surface their Toronto listings (Goldman, Deutsche, PIMCO), "
                "regulator careers pages aren't on Workday (OSFI, OSC, FSRA), "
                "or LinkedIn rate-limited the scan. "
                "Config fix: add a Workday/Greenhouse tenant, or rely on manual adds."
            )
            st.code("\n".join(f"  • {n}" for n in zero_companies), language="text")

    # This rule caps the diagnostics preamble (funnel + scrape diagnostics) before
    # the live panel + stage cards. The funnel renders on Refresh + Score only, so
    # the divider matches that scope — Promote stays lean (no funnel, no stray
    # rule); previously it was ungated and left an orphaned separator on Promote.
    if _pipe_view in ("Refresh", "Score"):
        st.markdown("---")

    # ---------- Main tabs ----------
    # Three tabs: Run (chain + Score-a-URL expander), Inspect (triage
    # funnel + scored drill-down), History. The old per-stage tabs
    # (1·Scrape / 2·Score / 4·Promote) were UI wrappers around CLIs that
    # the Run-chain button already invokes -- collapsed so the user sees
    # one page instead of juggling seven.
    # Tracker URLs for "already promoted" checks in Scored tab
    _tracker_urls = set()
    try:
        _tr_data = load_tracker()
        for _j in _tr_data.get("jobs") or []:
            _u = _j.get("url") or _j.get("link") or _j.get("job_url") or ""
            if _u:
                _tracker_urls.add(_u)
                _tracker_urls.add(_u.rstrip("/").lower())
    except Exception:
        pass

    # Live panel ABOVE tabs so active-job output is always visible
    _pipeline_live_panel()

    # The four section bodies below are defined as functions so BOTH layouts
    # (vertical cards / classic tabs) call the same tested wiring. They are
    # only INVOKED by the dispatcher at the end of the page — defining them
    # here has no side effects. Two-sources panel + tabs creation moved into
    # the classic-layout branch of that dispatcher.

    # ================== CARD/TAB: Worklist ==================
    def _render_worklist_card():
        # @st.fragment scopes the filter-widget reruns (search box, source/
        # sector multiselects, 'New since last score' checkbox) to this
        # fragment body. Without it, every widget click triggers a full-page
        # rerun and st.tabs re-mounts at tab[0] — making the user lose their
        # place. With the fragment, only the table re-filters in place.
        @st.fragment
        def _render_worklist_tab_body():
            _wl_path = OUT_DIR / "worklist.json"
            if not _wl_path.exists():
                st.info("No worklist built yet. Run a scrape first.")
                return
            try:
                _wl_data = json.loads(_wl_path.read_text(encoding="utf-8"))
                _wl_rows = _wl_data.get("results") or []
            except Exception:
                _wl_rows = []
            if not _wl_rows:
                st.info("Worklist is empty.")
                return

            # Per-row cache classification — same logic as the summary
            # strip on the two-sources panel, applied at row level so the
            # user can SEE + filter which specific rows the scorer would
            # call the LLM for.
            _scored_urls: set[str] = set()
            _sc_path = OUT_DIR / "worklist_scored.json"
            if _sc_path.exists():
                try:
                    _sc = json.loads(_sc_path.read_text(encoding="utf-8"))
                    for _r in _sc.get("results", []) or []:
                        _u = _r.get("link") or _r.get("url") or ""
                        if _u:
                            _scored_urls.add(_u)
                except Exception:
                    pass
            _fit_cache_dir = OUT_DIR / "fit_cache"
            try:
                import sys as _sys
                _ad = str(ROOT / "automation")
                if _ad not in _sys.path:
                    _sys.path.insert(0, _ad)
                from fit_scorer import _url_hash as _wl_url_hash  # type: ignore
            except Exception:
                _wl_url_hash = None

            def _row_cache_status(url: str) -> str:
                """Three buckets matching _classify_worklist_against_cache."""
                if not url or _wl_url_hash is None:
                    return "❓ unknown"
                try:
                    has_cache = (_fit_cache_dir
                                 / f"{_wl_url_hash(url)}.v2.json").exists()
                except Exception:
                    has_cache = False
                if has_cache:
                    return "💾 cached"
                if url in _scored_urls:
                    return "♻️ reuse"
                return "💸 needs LLM"

            _wl_df = pd.DataFrame([{
                "company": r.get("company", ""),
                "title": r.get("title", ""),
                "location": r.get("location", ""),
                "sector": r.get("sector", ""),
                "new": r.get("is_new_since_last_score", False),
                "cache": _row_cache_status(
                    r.get("link") or r.get("url", "")
                ),
                "posted": r.get("posted_date", ""),
                "source": r.get("source", ""),
                "url": r.get("link") or r.get("url", ""),
            } for r in _wl_rows])

            wf1, wf2, wf3, wf4, wf5 = st.columns([3, 2, 2, 2, 2])
            with wf1:
                _wl_search = st.text_input("Search company/title",
                                           key="wl_search")
            with wf2:
                _wl_sources = sorted(_wl_df["source"].dropna().unique())
                _wl_src_filt = st.multiselect("Source", _wl_sources,
                                               key="wl_source")
            with wf3:
                _wl_sectors = sorted(
                    s for s in _wl_df["sector"].dropna().unique() if s)
                _wl_sec_filt = st.multiselect("Sector", _wl_sectors,
                                               key="wl_sector")
            with wf4:
                _wl_new_only = st.checkbox("New since last score",
                                           key="wl_new_only")
            with wf5:
                _wl_needs_llm_only = st.checkbox(
                    "Needs LLM only",
                    key="wl_needs_llm",
                    help="Show only rows whose verdicts the scorer would "
                         "fetch via a fresh API call. Excludes cached + "
                         "already-scored rows.",
                )

            _wl_view = _wl_df.copy()
            if _wl_search:
                _sl = _wl_search.lower()
                _wl_view = _wl_view[
                    _wl_view["company"].str.lower().str.contains(_sl, na=False) |
                    _wl_view["title"].str.lower().str.contains(_sl, na=False)]
            if _wl_src_filt:
                _wl_view = _wl_view[_wl_view["source"].isin(_wl_src_filt)]
            if _wl_sec_filt:
                _wl_view = _wl_view[_wl_view["sector"].isin(_wl_sec_filt)]
            if _wl_new_only:
                _wl_view = _wl_view[_wl_view["new"] == True]
            if _wl_needs_llm_only:
                _wl_view = _wl_view[_wl_view["cache"] == "💸 needs LLM"]

            _wl_new_ct = int(_wl_df["new"].sum()) if "new" in _wl_df.columns else 0
            _wl_cached_ct = int((_wl_df["cache"] == "💾 cached").sum())
            _wl_reuse_ct = int((_wl_df["cache"] == "♻️ reuse").sum())
            _wl_llm_ct = int((_wl_df["cache"] == "💸 needs LLM").sum())
            _wm1, _wm2, _wm3, _wm4, _wm5 = st.columns(5)
            _wm1.metric("Rows shown", f"{len(_wl_view):,}")
            _wm2.metric("Total worklist", f"{len(_wl_df):,}")
            _wm3.metric("🆕 New", f"{_wl_new_ct:,}",
                         help="Not in previous scored output")
            _wm4.metric("💾 Cached + ♻️", f"{_wl_cached_ct + _wl_reuse_ct:,}",
                         help=f"{_wl_cached_ct} cached on disk + "
                              f"{_wl_reuse_ct} reusable from scored output")
            _wm5.metric("💸 Needs LLM", f"{_wl_llm_ct:,}",
                         help="Would force a fresh API call on Score now")
            st.dataframe(
                _wl_view,
                hide_index=True, width='stretch', height=600,
                column_config={"url": st.column_config.LinkColumn("url")},
            )

        _render_worklist_tab_body()

    # ================== CARD/TAB: Run (launch + advanced + score-URL) ======
    def _render_run_card():
        # --- Promote launch + power-user config ---
        # Buttons FIRST, config SECOND. This card lives on the ③ Promote view;
        # after the v3.2 strict split it offers only the 📋 Promote launch plus
        # the Advanced pipeline form (full chain for power users). Scrape/Gmail
        # launches live on ① Refresh, scoring on ④ Scoring.
        key_ok_here = api_key.is_key_valid()
        _can_run = not any_work_active

        # Show a clear blocker banner BEFORE the buttons so user knows why
        # things are disabled, with a direct fix action.
        if not key_ok_here:
            st.error(
                "**🔑 API key missing or invalid** — scoring, tailoring, and "
                "full-refresh all require a working Anthropic key. "
                "Open the **sidebar → Manage Anthropic API key** expander, "
                "paste your `sk-ant-...` key, and hit Save & validate. "
                "Scraping works without a key.",
                icon="🔑",
            )

        # ⚡ Launch is now PROMOTE-ONLY (v3.2 strict split). This card lives on
        # the ③ Promote view, so the only stage-launch that belongs here is
        # 📋 Promote scored. The other launches were relocated to the view that
        # owns their stage so each page only offers actions for its own intent:
        #   • 🛰 Refresh scrape / 🌐 Full scrape / 📬 Refresh Gmail / 🌅 Full
        #     refresh → ① Inputs + nightly strip on the ① Refresh view
        #   • 🤖 Score worklist + 🔗 Score-a-URL → ④ Scoring on the ② Score view
        # (doc §485-487, §116/§154/§167, §575). Advanced config below still
        # carries every knob for power users who want the full chain from here.
        st.markdown("#### ⚡ Launch")
        _ws_total = _wstats.get("total", 0)
        _ws_scored_exists = _wstatus.get("worklist_scored_exists", False)
        # Target counts feed the Advanced-config scrape-strategy selectbox below
        # (the launch buttons that used to consume this moved to ① Refresh).
        _counts = _target_counts()

        _promote_age_h = _latest_glob_age_hours("promote_report_*.md")
        _promote_fresh = _promote_age_h is not None and _promote_age_h < 24
        _promote_label = "📋 Promote scored" if _ws_scored_exists else "📋 (score first)"
        _promote_help = ("Promote scored roles into the tracker. "
                         "Reads worklist_scored.json. Dry-run first; "
                         "use the advanced form below for --commit.")
        if _promote_fresh:
            _promote_help += (f" ⚠️ Last promote {_promote_age_h:.0f}h ago — "
                              "review the report before re-running.")
        if st.button(_promote_label, width='stretch', key="_vc_promote_launch",
                     type="primary" if _ws_scored_exists else "secondary",
                     disabled=(not _can_run or not _ws_scored_exists),
                     help=_promote_help):
            rec = scan_runner.start_run("pipeline", [
                sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                "--skip-scrape", "--skip-score",
            ])
            st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Promote scored"}
            # Arm the Apply button (see _route_banner_cta promote branch).
            st.session_state["_promote_preview_armed"] = True
            st.toast("📋 Promote launched!", icon="🚀")
            st.rerun()
        if not _ws_scored_exists:
            st.caption("⏸ Score the worklist first (② Score → 🤖 Score worklist) "
                       "— promote reads `worklist_scored.json`.")
        elif _promote_fresh:
            st.caption(f"⚠️ Promoted {_promote_age_h:.0f}h ago")

        # Stop button — shown whenever any job is active (all launch buttons are
        # disabled then, so this is the only way the user can unblock).
        if any_work_active and active_runs:
            _stop_run = active_runs[0]
            st.warning(
                f"⏳ **{_stop_run.get('label', 'job')}** is running "
                f"({human_elapsed(_stop_run.get('started_at'))}) — "
                "launch buttons are disabled until it finishes.",
                icon="⚠️",
            )
            if st.button("⏹ Stop running job", type="primary", key="ql_stop_btn"):
                scan_runner.stop_run(_stop_run["run_id"])
                st.warning("⏹ Stop signal sent — job will exit after the current step.")
                st.rerun()

        # Live panel moved above tabs — always visible when a job is active.

        # Latest outputs — every action emits a JSON artifact; this row gives
        # one-click JSON + xlsx access without bouncing to History. In the
        # vertical layout each stage card already carries its own download
        # row, so the combined Latest-outputs panel (every artifact a SECOND
        # time) is intentionally NOT rendered here — the per-stage download
        # rows cover it (doc §427). The 3-view layout has no classic tab path.

        # (Gmail trash-cleanup panel was removed from this Promote card in the
        # v3.2 split: Gmail can no longer be fetched from here — the 📬 Refresh
        # Gmail button moved to ① Inputs, which already renders the trash panel
        # right after it. Keeping a second copy on Promote was dead chrome.)

        # --- Recent runs: what actually happened ---
        st.markdown("---")
        st.markdown("#### Recent runs")
        _recent_runs = scan_runner.list_runs(limit=5)
        if _recent_runs:
            _rr_rows = []
            for _rr in _recent_runs:
                _rr_icon = {"running": "🟡", "finished": "✅",
                            "failed": "❌", "stopped": "⏹"}.get(
                            _rr.get("state", ""), "❓")
                _rr_rows.append({
                    "": _rr_icon,
                    "run": _rr.get("label", "?"),
                    "state": _rr.get("state", "?"),
                    "started": fmt_dt(_rr.get("started_at")),
                    "duration": human_elapsed(_rr.get("started_at"), _rr.get("finished_at")),
                })
            st.dataframe(pd.DataFrame(_rr_rows), hide_index=True, width='stretch',
                         height=min(220, 40 + 36 * len(_rr_rows)))
        else:
            st.caption("No background runs yet — launch one above.")

        # --- Advanced config (collapsed by default) ---
        st.markdown("---")
        with st.expander("⚙️ Advanced pipeline configuration", expanded=False):
            cA, cB = st.columns([1, 1])
            with cA:
                scrape_mode = st.selectbox(
                    "Scrape strategy",
                    options=["full", "core", "ats", "linkedin", "expansion"],
                    format_func=lambda x: {
                        "full":      f"Full — all {_counts['full']} targets + expansion (20–40 min)",
                        "core":      f"Core {_counts['core']} targets (15–30 min)",
                        "ats":       "Direct ATS only — Workday/Greenhouse (3–6 min)",
                        "linkedin":  "LinkedIn guest search only (15–25 min)",
                        "expansion": f"Expansion list only — {_counts['expansion']} (5–10 min)",
                    }[x],
                )
                sector = st.text_input("Limit to sector (optional)", placeholder="Pension Funds")
                company = st.text_input("Limit to single company (optional)", placeholder="Scotiabank")
            with cB:
                skip_scrape = st.checkbox("Skip scrape (reuse latest scan)",
                                           help=f"Latest: {scan_f.name if scan_f else '(none)'}")
                skip_score = st.checkbox("Skip score (scrape only)")
                skip_promote = st.checkbox("Skip promote (scrape + score only)", value=True)
                score_concurrency = st.slider("Scorer concurrency", 1, 12, 6)
                score_limit = st.number_input("Score limit (0 = all)", 0, 5000, 0)
                dry_score = st.checkbox("Score dry-run (rule-stage only)")

            # Promote controls — only meaningful when the promote stage runs.
            # Exposed here so fit≥6 / include-watch / expire-stale / auto-tailor
            # are reachable from the UI instead of terminal-only (doc §168/§154).
            if not skip_promote:
                st.markdown("**Promote options**")
                pcA, pcB = st.columns(2)
                with pcA:
                    promote_min_score = st.slider(
                        "Promote min-score (fit≥)", 1, 10, 7,
                        help="Roles scoring below this aren't promoted "
                             "(auto_promote --min-score).")
                    include_watch = st.checkbox(
                        "Include verdict=watch", value=False,
                        help="Promote watch-verdict roles as Watch "
                             "(--include-watch).")
                with pcB:
                    commit_promote = st.checkbox(
                        "Commit to tracker (write)", value=False,
                        help="Without this, promote is a dry-run preview "
                             "(--commit-promote).")
                    expire_stale = st.checkbox(
                        "Expire stale auto-* rows", value=False,
                        help="Mark auto-* tracker rows absent from this scan "
                             "as Expired (--expire-stale).")
                    auto_tailor = st.checkbox(
                        "Auto-tailor new Tier-1", value=False,
                        help="Spawn jd_tailor for each new Tier-1 role after "
                             "commit (--auto-tailor; ignored in dry-run).")
            else:
                promote_min_score = 7
                include_watch = commit_promote = expire_stale = auto_tailor = False

            cmd = [sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                   "--scrape-mode", scrape_mode,
                   "--score-concurrency", str(score_concurrency)]
            if sector.strip():
                cmd += ["--sector", sector.strip()]
            if company.strip():
                cmd += ["--company", company.strip()]
            if skip_scrape:
                cmd.append("--skip-scrape")
            if skip_score:
                cmd.append("--skip-score")
            if skip_promote:
                cmd.append("--skip-promote")
            else:
                cmd += ["--min-score", str(int(promote_min_score))]
                if include_watch:
                    cmd.append("--include-watch")
                if commit_promote:
                    cmd.append("--commit-promote")
                if expire_stale:
                    cmd.append("--expire-stale")
                if auto_tailor:
                    cmd.append("--auto-tailor")
            if score_limit:
                cmd += ["--score-limit", str(int(score_limit))]
            if dry_score:
                cmd.append("--score-dry-run")

            st.code(" ".join(cmd), language="bash")
            if not skip_promote and commit_promote:
                st.warning("⚠️ This run will **write to the tracker** "
                           "(--commit-promote). A .bak is saved first.",
                           icon="🗄️")

            needs_llm = not skip_score or not skip_promote
            can_run_adv = not pipeline_running and (key_ok_here or not needs_llm)
            if needs_llm and not key_ok_here:
                st.warning(
                    "This run will call the Anthropic API. Set a valid key in the sidebar, "
                    "or tick Skip score + Skip promote for scrape-only.",
                    icon="🔑",
                )
            if st.button("▶️ Launch custom pipeline", type="primary",
                         width='stretch', disabled=not can_run_adv,
                         key="adv_launch_pipe"):
                rec = scan_runner.start_run("pipeline", cmd)
                st.success(f"Pipeline launched (`{rec.run_id}`, pid {rec.pid})")
                st.rerun()

    # ---------- Score a single URL (persistent expander) ----------
    # Relocated out of the Promote run card into its own sibling closure so the
    # ④ Scoring card (② Score view) can host it — it's a manual side-channel
    # scorer, conceptually a Score action, not a promote one (doc §575/§155).
    # Body indentation is unchanged from when it lived in _render_run_card.
    def _render_score_a_url():
        with st.expander("🔗 Score a single URL (ad-hoc, no scan needed)",
                          expanded=False):
            st.caption("Paste any job URL for a fresh LLM fit score. ~5s, ~$0.001.")
            url_key_ok = api_key.is_key_valid()
            if not url_key_ok:
                st.warning("🔑 API key required. Set it in the sidebar.")
            url_in = st.text_input(
                "JD URL",
                placeholder="https://jobs.citi.com/job/mississauga/non-trading-market-risk-officer-vice-president/287/93536402784",
                key="url_score_input",
            )
            u1, u2, u3 = st.columns([2, 2, 1])
            with u1:
                company_in = st.text_input("Company (optional — inferred from URL)",
                                            key="url_score_company")
            with u2:
                title_in = st.text_input("Title (optional — inferred from JD)",
                                          key="url_score_title")
            with u3:
                add_to_tr = st.checkbox("Add to tracker",
                                         help="If result is actionable, append to "
                                              "job_tracker_data.json",
                                         key="url_score_add")
            rescore = st.checkbox("Bypass cache (force fresh LLM call)",
                                   key="url_score_rescore")
            if st.button("🤖 Score this URL", type="primary",
                         disabled=(not (url_key_ok and url_in.strip())
                                   or any_work_active),
                         help=("Another job is running — wait for it to "
                               "finish before scoring a one-off URL."
                               if any_work_active else None),
                         key="url_score_btn"):
                cmd = [sys.executable, str(ROOT / "automation" / "score_url.py"),
                       url_in.strip(), "--json-only"]
                if company_in.strip():
                    cmd += ["--company", company_in.strip()]
                if title_in.strip():
                    cmd += ["--title", title_in.strip()]
                if rescore:
                    cmd.append("--rescore")
                if add_to_tr:
                    cmd.append("--add-to-tracker")
                # Launch detached so the UI stays responsive (was a blocking
                # subprocess.run that froze Streamlit for up to 60s). Result
                # renders below via run_inline_agent once the run finishes.
                start_inline_agent("score_url", "score_url", cmd)
                st.session_state["_inline_score_url_addtr"] = add_to_tr
                st.rerun()

            def _render_score_url(log_text, rec):
                # score_url.py --json-only prints indented JSON to stdout and
                # diagnostics to stderr; start_run merges both into the log.
                # The JSON is the only multi-line {...} block — extract it.
                fit = _extract_pretty_json(log_text)
                if fit is None:
                    st.error("Scorer did not return JSON:")
                    st.code(log_text[-1500:], language="text")
                    return
                # score_url warns (but allows) when the URL's company is on the
                # permanent exclude-list — surface it so a manual override is
                # never silent. Marker phrase is emitted by score_url.py.
                if "on the permanent exclude-list" in log_text:
                    st.warning(
                        "⚠ This company is on your permanent **exclude-list**. "
                        "Scored anyway (manual override) — the bulk scrape, "
                        "Gmail, and worklist still skip it. Untick it under "
                        "🚫 Excluded companies if you want it back in the funnel.",
                        icon="🚫",
                    )
                verdict = fit.get("fit_verdict", "?")
                score = fit.get("fit_score", "?")
                tier = fit.get("tier", "?")
                variants = fit.get("applicable_resume_variants") or []
                badge = {"apply_now": "🟢", "tailor_and_apply": "🟡",
                         "watch": "⚪", "skip": "🔴", "error": "❌"}.get(verdict, "⚪")
                st.markdown(
                    f"### {badge} Verdict: `{verdict}` · "
                    f"Score: **{score}/10** · Tier {tier}"
                )
                cA, cB = st.columns(2)
                with cA:
                    st.markdown("**Lead-with resume(s):** "
                                + (" · ".join(variants) if variants else "—"))
                    st.markdown("**Summary:** " + fit.get("summary", "—"))
                with cB:
                    reasons = fit.get("top_3_reasons") or []
                    if reasons:
                        st.markdown("**Why it fits:**")
                        for r in reasons:
                            st.markdown(f"- {r}")
                    gaps = fit.get("skill_gaps") or []
                    if gaps:
                        st.markdown("**Gaps:** " + "; ".join(gaps))
                if st.session_state.get("_inline_score_url_addtr") and \
                        "Added" in log_text:
                    st.success("✅ Added to tracker. Reload the Kanban to see it.")
                    load_tracker.clear()
                st.session_state.pop("_inline_score_url_addtr", None)
                with st.expander("Raw scorer output"):
                    st.code(json.dumps(fit, indent=2), language="json")

            run_inline_agent(
                "score_url", "Score URL", on_finish=_render_score_url,
                running_msg="Fetching JD and scoring… UI stays responsive.",
            )

    # ================== CARD/TAB: Scored (+ triage sub-tabs) ===============
    def _render_scored_card():
        # Suppression admin lives on the ② Score view's ③ Triage card
        # (doc §280/§368/§446), which calls _render_suppressions_admin itself —
        # so the scored card no longer renders it (avoids a double-mount).

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.info("No scored scan yet — run the scorer first.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="triage_file")
            sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
            results = sc.get("results", [])

            # --- Funnel headline metrics ------------------------------------
            total_input = sc.get("total_input", len(results))
            passed = sc.get("stage1_passed", 0)
            dropped = sc.get("stage1_dropped", 0)
            only_filt = sc.get("stage1_only_filtered", 0)
            scored_n = sc.get("stage2_scored", len(results))
            fm1, fm2, fm3, fm4 = st.columns(4)
            fm1.metric("Total input", f"{total_input:,}")
            fm2.metric("Dropped (rule)", f"{dropped:,}",
                        f"{(100*dropped/max(total_input,1)):.0f}%",
                        delta_color="inverse")
            fm3.metric("Passed stage-1", f"{passed:,}",
                        f"{(100*passed/max(total_input,1)):.0f}%")
            fm4.metric("LLM-scored", f"{scored_n:,}")

            triage_tabs = st.tabs([
                "🎯 Scored candidates",
                "🚫 Dropped (rule-triage)",
                "🏢 By company",
                "🏷 By sector",
            ])

            # --- Sub-tab 1: scored candidates -------------------------------
            with triage_tabs[0]:
                # Surface scoring failures (fit_verdict=="error") — they're
                # hidden by the default verdict filter, so without this banner
                # the user can't see that N roles failed to score (doc: API
                # errors view). Lists the first few company/title for triage.
                _err_rows = [
                    r for r in results
                    if (r.get("fit") or {}).get("fit_verdict") == "error"
                ]
                if _err_rows:
                    _err_names = ", ".join(
                        f"{r.get('company','?')}" for r in _err_rows[:5])
                    _more = f" (+{len(_err_rows) - 5} more)" if len(_err_rows) > 5 else ""
                    st.warning(
                        f"⚠️ {len(_err_rows)} role(s) failed to score "
                        f"(verdict=error): {_err_names}{_more}. Re-run the "
                        "scorer or check the API key / rate limits.",
                        icon="⚠️",
                    )
                if not results:
                    st.info("No scored candidates in this file — "
                            "either the scorer was dry-run, the API key "
                            "preflight failed, or all roles dropped at stage 1.")
                else:
                    # Flatten — column order: score → identity → details → metadata
                    rows = []
                    for r in results:
                        f = r.get("fit") or {}
                        _r_url = r.get("link", "")
                        rows.append({
                            "fit": f.get("fit_score", 0),
                            "verdict": f.get("fit_verdict", ""),
                            "tier": f.get("tier", 4),
                            "in_tracker": "✅" if _r_url in _tracker_urls else "",
                            "company": r.get("company", ""),
                            "title": r.get("title", ""),
                            "sector": r.get("sector", ""),
                            "variants": "/".join(f.get("applicable_resume_variants") or []),
                            "summary": f.get("summary", ""),
                            "gaps": ", ".join(f.get("skill_gaps") or []),
                            "source": r.get("source", ""),
                            "posted": r.get("posted_date", ""),
                            "found": r.get("found_at", ""),
                            "url": _r_url,
                        })
                    df = pd.DataFrame(rows).sort_values(["fit", "tier"],
                                                         ascending=[False, True])

                    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
                    with f1:
                        min_fit = st.slider("Min fit score", 1, 10, 7, key="triage_min")
                    with f2:
                        _verdict_opts = sorted(df["verdict"].dropna().unique())
                        _verdict_defaults = [v for v in ["apply_now", "tailor_and_apply"]
                                              if v in _verdict_opts]
                        verdict_filter = st.multiselect(
                            "Verdict", _verdict_opts,
                            default=_verdict_defaults, key="triage_verdict")
                    with f3:
                        sector_filter = st.multiselect(
                            "Sector", sorted(df["sector"].dropna().unique()),
                            key="triage_sector")
                    with f4:
                        search = st.text_input("Search company/title", key="triage_q")

                    view = df[df["fit"] >= min_fit]
                    if verdict_filter:
                        view = view[view["verdict"].isin(verdict_filter)]
                    if sector_filter:
                        view = view[view["sector"].isin(sector_filter)]
                    if search:
                        sl = search.lower()
                        view = view[view["company"].str.lower().str.contains(sl, na=False) |
                                    view["title"].str.lower().str.contains(sl, na=False)]

                    # Promotable rows = visible rows not already in the
                    # tracker. (Already-tracked rows surface in the caption
                    # below for transparency, but get no checkbox.)
                    _promotable = view[view["in_tracker"] != "✅"].copy()
                    _not_promotable = view[view["in_tracker"] == "✅"]

                    st.caption(
                        f"Showing {len(view)} of {len(df)} scored candidates "
                        f"({len(_not_promotable)} already in tracker)"
                    )

                    if not _promotable.empty:
                        # ── Cluster A: URL-keyed selection state ──
                        # Source-of-truth lives in session state, keyed on
                        # URL (the only stable identity across reruns and
                        # filter changes). `df["promote"] = isin(state)`
                        # each render; data_editor edits are reconciled
                        # back via apply_selection_edit() so off-screen
                        # selections survive filter changes intact.
                        _sel_state: set[str] = st.session_state.setdefault(
                            "scoring_selected_urls", set())
                        _visible_urls = set(_promotable["url"].tolist())
                        _promotable.insert(
                            0, "promote",
                            _promotable["url"].isin(_sel_state),
                        )
                        _edited = st.data_editor(
                            _promotable,
                            hide_index=True, width='stretch', height=500,
                            column_config={
                                "promote": st.column_config.CheckboxColumn(
                                    "📋", help="Select to promote to tracker",
                                    default=False, width="small"),
                                "url": st.column_config.LinkColumn("url"),
                            },
                            disabled=[c for c in _promotable.columns if c != "promote"],
                            key="scored_editor",
                        )
                        _ticked_urls = set(
                            _edited.loc[_edited["promote"] == True, "url"].tolist()
                        )
                        # Reconcile: hidden URLs preserved, visible URLs
                        # synced to whatever the user just ticked.
                        st.session_state["scoring_selected_urls"] = \
                            pipeline_state.apply_selection_edit(
                                selection=_sel_state,
                                visible_urls=_visible_urls,
                                ticked_urls=_ticked_urls,
                            )
                        _sel_state = st.session_state["scoring_selected_urls"]

                        # [Select all visible] — bulk-tick the current
                        # (possibly filtered) view in one click (mockup State 7
                        # third footer control). Unions the visible URLs into
                        # the selection so off-screen ticks are preserved.
                        if _visible_urls:
                            if st.button(
                                f"☑ Select all visible ({len(_visible_urls)})",
                                key="scored_select_all_visible",
                                help="Tick every row in the current view; "
                                     "off-screen selections are kept."):
                                st.session_state["scoring_selected_urls"] = (
                                    _sel_state | _visible_urls)
                                st.rerun()

                        # ── [Send N selected] action + pre-flight caption ──
                        if _sel_state:
                            # Lazy-load suppressions for the preflight
                            # caption so a missing/corrupt registry
                            # doesn't break the data_editor render.
                            _supp_state = None
                            try:
                                from automation import suppressions as _supp  # noqa: WPS433
                                _supp_state = _supp.load_active()
                            except Exception:
                                _supp_state = {"sectors": [], "companies": []}

                            # Preflight runs against the FULL scored set
                            # (not the filtered `view`) because the selection
                            # may include URLs the user ticked under a
                            # different filter. min_score=7 mirrors
                            # auto_promote.py's default — that's the value
                            # the shelled subprocess will compare against,
                            # not the page slider.
                            _bd = pipeline_state.compute_preflight_breakdown(
                                selection=_sel_state,
                                scored_rows=results,
                                suppressions_state=_supp_state,
                                min_score=7,
                                tracker_urls=_tracker_urls,
                            )

                            # Large-batch guard (doc §B:243): a hand-picked
                            # selection of ≥25 rows requires an explicit
                            # confirm before the commit fires, so one stray
                            # click can't bulk-write dozens of tracker rows.
                            _BULK_CONFIRM_AT = 25
                            _bulk_big = len(_sel_state) >= _BULK_CONFIRM_AT
                            _bulk_confirmed = True
                            if _bulk_big:
                                _bulk_confirmed = st.checkbox(
                                    f"⚠️ Confirm: promote {len(_sel_state)} roles "
                                    "to the tracker (large batch)",
                                    key="scored_bulk_confirm")

                            _bcol1, _bcol2 = st.columns([2, 1])
                            with _bcol1:
                                _send_clicked = st.button(
                                    f"📋 Send {len(_sel_state)} selected to tracker",
                                    type="primary",
                                    disabled=any_work_active or not _bulk_confirmed,
                                    key="scored_bulk_promote",
                                )
                                st.caption(
                                    pipeline_state.format_preflight_caption(_bd)
                                )
                            with _bcol2:
                                if st.button("Clear selection",
                                             key="scored_bulk_clear"):
                                    st.session_state["scoring_selected_urls"] = set()
                                    st.rerun()

                            if _send_clicked:
                                _sel_n = len(_sel_state)  # capture before clear
                                # Write the URL list to a tempfile and pass
                                # via --only-urls. Atomic file is more robust
                                # than chained --only-url args (no shell
                                # length limit, audit trail in the file).
                                import tempfile as _tf
                                _tmp = _tf.NamedTemporaryFile(
                                    mode="w", encoding="utf-8",
                                    suffix=".urls.txt", delete=False,
                                    dir=str(OUT_DIR),
                                )
                                _tmp.write(
                                    "# auto-generated by ui/app.py — "
                                    f"{datetime.now().isoformat(timespec='seconds')}\n"
                                )
                                for _u in sorted(_sel_state):
                                    _tmp.write(_u + "\n")
                                _tmp.close()
                                _prec = scan_runner.start_run("promote", [
                                    sys.executable,
                                    str(ROOT / "automation" / "auto_promote.py"),
                                    "--only-urls", _tmp.name,
                                    "--commit",
                                ])
                                st.toast(
                                    f"Promoting {len(_sel_state)} role(s)…",
                                    icon="📋")
                                st.session_state["scoring_selected_urls"] = set()
                                # Surface the run in the Dashboard banner AND
                                # rerun so the data_editor drops its ticks —
                                # without the rerun, apply_selection_edit
                                # re-merges the old ticks and the "cleared"
                                # selection silently reappears.
                                st.session_state["_last_launch"] = {
                                    "run_id": _prec.run_id,
                                    "label": "Promote selected",
                                }
                                # Arm the success-feedback overlay (doc §90).
                                st.session_state["_promote_feedback"] = {
                                    "count": _sel_n,
                                    "ts": datetime.now().isoformat(timespec="seconds"),
                                }
                                st.rerun()
                    else:
                        st.dataframe(view, hide_index=True, width='stretch',
                                     height=500,
                                     column_config={"url": st.column_config.LinkColumn("url")})

            # --- Sub-tab 2: dropped (rule-triage) ---------------------------
            with triage_tabs[1]:
                drops = sc.get("triage_drops") or []
                if not drops:
                    st.info(
                        "No triage-drop records in this scored file. "
                        "This usually means the scored file was produced by "
                        "an older version of fit_scorer. Re-run the scorer "
                        "(or a dry-run) to populate the triage audit trail."
                    )
                else:
                    # Categorize via the pure helper so suppressed_*_30d /
                    # _60d / _90d collapse into one histogram row each.
                    _bd = pipeline_state.categorize_drop_reasons(drops)
                    _by_cat = _bd["by_category"]
                    _neg_term_ct = _bd["neg_terms"]

                    rm1, rm2 = st.columns([1, 1])
                    with rm1:
                        st.markdown("**Drop reasons (histogram)**")
                        if _bd["suppressed_total"]:
                            st.caption(
                                f"🔇 {_bd['suppressed_total']} dropped by "
                                "suppression — manage mutes in the "
                                "🔇 Active suppressions panel above."
                            )
                        _reason_df = pd.DataFrame(
                            [{"reason": k, "count": v} for k, v in _by_cat.items()]
                        )
                        if not _reason_df.empty:
                            st.dataframe(_reason_df, hide_index=True, width='stretch',
                                         height=200)
                    with rm2:
                        st.markdown("**Top negative-title terms**")
                        st.caption("Tune NEG_TITLE_TERMS in fit_scorer to adjust.")
                        _neg_df = pd.DataFrame(
                            [{"term": k, "hits": v}
                             for k, v in list(_neg_term_ct.items())[:20]]
                        )
                        if not _neg_df.empty:
                            st.dataframe(_neg_df, hide_index=True, width='stretch',
                                         height=200)
                        else:
                            st.caption("_(no hard-fail negative terms — all drops were "
                                       "insufficient-signal)_")

                    st.markdown("---")
                    st.markdown(f"**All {len(drops):,} dropped roles**")
                    _filter_col, _q_col = st.columns([1, 2])
                    with _filter_col:
                        # Phase 3C: category filter chip — surfaces
                        # suppressed-* drops as a one-click view.
                        _cat_options = ["(all)"] + list(_by_cat.keys())
                        _cat_label = st.selectbox(
                            "Filter by category", _cat_options,
                            key="triage_drop_cat",
                        )
                        _cat_filter = None if _cat_label == "(all)" else _cat_label
                    with _q_col:
                        _drop_q = st.text_input(
                            "Search company/title in drops",
                            key="triage_drop_q",
                            placeholder="scotiabank / data engineer / ...",
                        )

                    _filtered_drops = pipeline_state.filter_drops_by_category(
                        drops, _cat_filter,
                    )
                    _drop_rows = []
                    for d in _filtered_drops:
                        co, ti = d.get("company", ""), d.get("title", "")
                        if _drop_q:
                            q = _drop_q.lower()
                            if q not in co.lower() and q not in ti.lower():
                                continue
                        _drop_rows.append({
                            "company": co,
                            "title": ti,
                            "why": ", ".join(d.get("rule_reasons", []))[:120],
                            "score": d.get("score", 0),
                            "source": d.get("source", ""),
                            "url": d.get("link", ""),
                        })
                    st.caption(f"Showing {len(_drop_rows):,} of {len(drops):,}")
                    if _drop_rows:
                        st.dataframe(
                            pd.DataFrame(_drop_rows),
                            hide_index=True, width='stretch', height=420,
                            column_config={"url": st.column_config.LinkColumn("open")},
                        )

            # --- Sub-tab 3: by-company breakdown ----------------------------
            with triage_tabs[2]:
                st.caption("Roles per company: scraped → passed (LLM) vs dropped (rule).")
                from collections import Counter as _Counter
                _passed_ct = _Counter(r.get("company", "?") for r in results)
                _dropped_ct = _Counter((d.get("company") or "?") for d in sc.get("triage_drops") or [])
                _all_companies = set(_passed_ct) | set(_dropped_ct)
                by_co = []
                for co in sorted(_all_companies):
                    p = _passed_ct.get(co, 0)
                    d = _dropped_ct.get(co, 0)
                    tot = p + d
                    by_co.append({
                        "company": co,
                        "scraped": tot,
                        "passed": p,
                        "dropped": d,
                        "pass_rate": f"{(100*p/tot):.0f}%" if tot else "—",
                    })
                by_co_df = pd.DataFrame(by_co)
                if "scraped" in by_co_df.columns:
                    by_co_df = by_co_df.sort_values("scraped", ascending=False)
                st.dataframe(by_co_df, hide_index=True, width='stretch', height=500)

            # --- Sub-tab 4: by sector (mockup State 7) ----------------------
            with triage_tabs[3]:
                st.caption("Scored roles per sector: count, mean fit, and "
                           "actionable (apply_now + tailor_and_apply).")
                from collections import Counter as _SecCounter  # noqa: WPS433
                _sec_rows: dict[str, dict] = {}
                for r in results:
                    f = r.get("fit") or {}
                    sec = r.get("sector") or "(unknown)"
                    slot = _sec_rows.setdefault(
                        sec, {"sector": sec, "scored": 0, "_fit_sum": 0,
                              "_fit_n": 0, "actionable": 0})
                    slot["scored"] += 1
                    try:
                        _fs = float(f.get("fit_score") or 0)
                        if _fs:
                            slot["_fit_sum"] += _fs
                            slot["_fit_n"] += 1
                    except (TypeError, ValueError):
                        pass
                    if f.get("fit_verdict") in ("apply_now", "tailor_and_apply"):
                        slot["actionable"] += 1
                by_sec = []
                for slot in _sec_rows.values():
                    _n = slot.pop("_fit_n")
                    _s = slot.pop("_fit_sum")
                    slot["mean_fit"] = f"{(_s / _n):.0f}" if _n else "—"
                    by_sec.append(slot)
                if by_sec:
                    by_sec_df = pd.DataFrame(by_sec)[
                        ["sector", "scored", "mean_fit", "actionable"]
                    ].sort_values("scored", ascending=False)
                    st.dataframe(by_sec_df, hide_index=True, width='stretch',
                                 height=500)
                else:
                    st.caption("No scored rows to group.")

    # ================== CARD/TAB: History ==================
    def _render_history_card():
        pipelines = list_pipelines(50)
        if not pipelines:
            st.caption("No pipeline runs yet — launch one from the Run tab.")
        else:
            rows = []
            for p in pipelines:
                stages = p.get("stages", {})
                scrape = stages.get("scrape", {})
                score = stages.get("score", {})
                promote = stages.get("promote", {})
                rows.append({
                    "pipeline_id": p.get("pipeline_id"),
                    "state": p.get("state"),
                    "started": fmt_dt(p.get("started_at")),
                    "finished": fmt_dt(p.get("finished_at")),
                    "duration": human_elapsed(p.get("started_at"), p.get("finished_at")),
                    "scrape": f"{scrape.get('state', '-')} ({scrape.get('candidate_count', '?')})",
                    "score": f"{score.get('state', '-')} ({score.get('scored_count', '?')})",
                    "promote": promote.get("state", "-"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
                         height=300)

            pick_id = st.selectbox("Inspect pipeline", [p["pipeline_id"] for p in pipelines])
            sel = next((p for p in pipelines if p["pipeline_id"] == pick_id), None)
            if sel:
                st.json(sel, expanded=False)
                # Audit-pack download — multi-sheet xlsx covering every pipeline
                # stage (raw scrape, title/geo drops, gmail, worklist, merges,
                # Stage-1 drops, scored, promote skips). Lets Saber see exactly
                # which roles got dropped where so he can give the agent feedback.
                try:
                    import sys as _sys
                    _automation_dir = str(ROOT / "automation")
                    if _automation_dir not in _sys.path:
                        _sys.path.insert(0, _automation_dir)
                    from audit_pack import build_audit_pack as _build_pack
                    # pipeline_YYYYMMDD_HHMMSS → derive YYYYMMDD
                    _stamp = pick_id.split("_")[1] if "_" in pick_id else "latest"
                    if st.button("📦 Build audit pack (xlsx)", key=f"build_pack_{pick_id}"):
                        with st.spinner("Building multi-sheet xlsx…"):
                            st.session_state[f"_pack_bytes_{pick_id}"] = _build_pack(_stamp)
                    if st.session_state.get(f"_pack_bytes_{pick_id}"):
                        st.download_button(
                            "⬇ Download audit_pack.xlsx",
                            data=st.session_state[f"_pack_bytes_{pick_id}"],
                            file_name=f"audit_pack_{_stamp}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_pack_{pick_id}",
                        )
                except Exception as _pack_err:
                    st.caption(f"Audit pack unavailable: {_pack_err}")

        st.markdown("---")
        st.subheader("🛠 Background run history (scan_runner)")
        runs = scan_runner.list_runs(30)
        if runs:
            rrows = [{
                "run_id": r["run_id"],
                "label": r["label"],
                "state": r.get("state"),
                "started": fmt_dt(r.get("started_at")),
                "duration": human_elapsed(r.get("started_at"), r.get("finished_at")),
                "pid": r.get("pid"),
            } for r in runs]
            st.dataframe(pd.DataFrame(rrows), hide_index=True, width='stretch',
                         height=260)
            sel_run = st.selectbox("Tail log", [r["run_id"] for r in runs])
            r = next((r for r in runs if r["run_id"] == sel_run), None)
            if r:
                st.code(scan_runner.tail_log(r["log_path"], max_bytes=60_000), language="text")
        else:
            st.caption("No background runs recorded.")

        # --- Recent Runs (merged from old tab) ---
        st.markdown("---")
        st.subheader("🕒 Recent Pipeline Runs")
        _runs = list_pipelines(20)
        if not _runs:
            st.info("No pipeline runs yet — launch one from the Run tab above.")
        else:
            _badge = {"finished": "✅ finished", "failed": "❌ failed",
                      "crashed": "💥 crashed", "running": "🔄 running",
                      "stale": "⚪ stale", "stopped": "⏹ stopped"}
            _n = len(_runs)
            _ok = sum(1 for r in _runs if r.get("state") == "finished")
            _bad = sum(1 for r in _runs
                       if r.get("state") in ("failed", "crashed", "stale"))
            _costs = [r.get("total_cost") or r.get("cost_usd") or 0.0
                      for r in _runs]
            _costs = [c for c in _costs if isinstance(c, (int, float)) and c > 0]
            _avg_cost = (sum(_costs) / len(_costs)) if _costs else 0.0

            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Runs", _n)
            kc2.metric("Successful", _ok)
            kc3.metric("Failed/crashed", _bad)
            kc4.metric("Avg cost", f"${_avg_cost:.2f}" if _avg_cost else "—")
            st.markdown("---")

            for _r in _runs:
                _pid = _r.get("pipeline_id") or _r.get("id") or "?"
                _state = _r.get("state") or "?"
                _stages = _r.get("stages") or {}
                _started = _r.get("started_at")
                _finished = _r.get("finished_at")
                _wall = human_elapsed(_started, _finished)
                _parts = []
                for _name in ("scrape", "score", "promote", "tailor"):
                    _s = _stages.get(_name) or {}
                    _ss = _s.get("state", "—")
                    if _ss == "skipped":
                        _parts.append(f"{_name}: skipped")
                    elif _s.get("elapsed_sec") is not None:
                        _parts.append(f"{_name}: {int(_s['elapsed_sec'])}s")
                    elif _ss != "—":
                        _parts.append(f"{_name}: {_ss}")
                _stage_line = " · ".join(_parts) if _parts else "no stages recorded"
                _cost = _r.get("total_cost") or _r.get("cost_usd") or 0.0
                _cost_str = f" · ${_cost:.2f}" if isinstance(_cost, (int, float)) and _cost > 0 else ""

                with st.container(border=True):
                    rc1, rc2, rc3 = st.columns([3, 4, 2])
                    rc1.markdown(
                        f"**{fmt_dt(_started)}**  \n"
                        f"{_badge.get(_state, _state)} · `{_pid}`"
                    )
                    rc2.caption(f"⏱ {_wall}{_cost_str}")
                    rc2.caption(_stage_line)
                    with rc3:
                        with st.expander("View details"):
                            _scrape_f = (_stages.get("scrape") or {}).get("scan_file")
                            _score_f = (_stages.get("score") or {}).get("scored_file")
                            _prom_f = (_stages.get("promote") or {}).get("promote_report")
                            for _label, _val in (("scan", _scrape_f),
                                                 ("scored", _score_f),
                                                 ("promote_report", _prom_f)):
                                if _val:
                                    st.caption(f"📁 {_label}: `{_val}`")
                            st.json(_r, expanded=False)

    # ======================================================================
    # LAYOUT DISPATCHER
    # ======================================================================
    # Both layouts call the SAME four render functions defined above plus the
    # shared panels. Only the arrangement differs. Critic fixes baked into the
    # vertical path: fixed 6-card slots (no reflow), no card-level dimming
    # (buttons disable + header chip instead), markdown+caption headlines
    # (not st.metric), button-gated heavy inspect bodies (if-skip, not just
    # expander), and a stage-jump rail to neutralize the scroll tax.

    def _stage_chip(running: bool, state_ok: bool = True,
                    empty: bool = False) -> str:
        # ⏸ = empty/no-data-yet (doc §103 pill level), distinct from ⚪
        # (has data but not "ok"). Empty wins only when not running.
        if running:
            return "🟡 running"
        if empty:
            return "⏸"
        return "🟢" if state_ok else "⚪"

    # True when there's no worklist yet — drives the ⏸ "will activate" copy.
    _pipe_empty = (_wstats.get("total", 0) == 0)

    # ---------------- 3-view card dispatcher (v3.2) -------------------
    # The six stage cards are split across the three sub-pages. Each card
    # body stays exactly where it was (8-space indented under its view
    # guard) — only the wrapping `if _pipe_view == ...:` changes. Stage
    # header chips read these derived flags regardless of view.
    _src_ok = bool(scan_f or _latest_gm)
    _wl_ok = bool(_wstatus.get("worklist_exists"))
    _scored_ok = bool(score_count)
    _ws_scored_exists = bool(_wstatus.get("worklist_scored_exists"))
    _ws_total = _wstats.get("total", 0)

    # ═══════════════ ① REFRESH view: ① Inputs + ② Worklist ═══════════
    if _pipe_view == "Refresh":
        # ── ① INPUTS ──────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown(
                f"#### 🛰 ① Inputs · {_stage_chip(_scraper_active)}"
            )
            render_two_sources_panel()
            # Per-source refresh actions (doc §116). These mirror the launch
            # buttons in the run card but live ON the ① card where the doc +
            # mockup place them. Same freshness/active-run disable guards.
            _in_can_run = not any_work_active
            _in_scrape_age = _web_scan_age_hours()
            _in_scrape_fresh = _in_scrape_age is not None and _in_scrape_age < 24
            _in_gmail_age = _latest_glob_age_hours("scan_gmail_*.json")
            _in_gmail_fresh = _in_gmail_age is not None and _in_gmail_age < 1
            _in_gmail_ok = gmail_ui.is_connected()
            _in_counts = _target_counts()
            _ic1, _ic2 = st.columns(2)
            if _ic1.button(f"🛰 Refresh scrape ({_in_counts['full']})",
                           width="stretch", key="_vc_inputs_refresh_scrape",
                           disabled=(not _in_can_run or _in_scrape_fresh),
                           help=(f"Re-scrape ALL {_in_counts['full']} targets "
                                 f"({_in_counts['core']} core + "
                                 f"{_in_counts['expansion']} expansion). "
                                 "~20–40 min, no API key. Auto-rebuilds the "
                                 "worklist. Use ⚡ Quick core scrape below for "
                                 "the faster core-only pass."
                                 + (f" 🟢 Scan {_in_scrape_age:.0f}h old — fresh."
                                    if _in_scrape_fresh else ""))):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "full", "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Refresh scrape (full)"}
                st.toast("🛰 Full scrape launched!", icon="🚀")
                st.rerun()
            if _ic2.button("📬 Refresh Gmail", width="stretch",
                           key="_vc_inputs_refresh_gmail",
                           disabled=(not _in_gmail_ok or not _in_can_run),
                           help=("Pull LinkedIn alert emails from last 30d "
                                 "(~10–30s, free). Auto-rebuilds the worklist."
                                 if _in_gmail_ok else
                                 "Connect Gmail in the sidebar first.")):
                rec = scan_runner.start_run("gmail_fetch", [
                    sys.executable,
                    str(ROOT / "automation" / "gmail_fetch.py"), "--days", "30",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Gmail fetch"}
                st.toast("📬 Gmail fetch launched!", icon="🚀")
                st.rerun()
            # ⚡ Quick core scrape — the faster core-only pass (66 targets, no
            # expansion list). Demoted to the secondary slot: 🛰 Refresh scrape
            # above now defaults to the FULL list (159) so complete coverage is
            # the default action; this is the quick option when you just want a
            # fast core refresh. Reuses the per-source freshness/active-run
            # guards computed just above.
            if st.button(f"⚡ Quick core scrape ({_in_counts['core']})",
                         width="stretch", key="_vc_inputs_core_scrape",
                         disabled=(not _in_can_run or _in_scrape_fresh),
                         help=f"Faster core-only scrape — {_in_counts['core']} "
                              f"core targets, skips the {_in_counts['expansion']}-"
                              "company expansion list. ~15–30 min, no API key. "
                              "Use 🛰 Refresh scrape above for full coverage."
                              + (f" 🟢 Scan {_in_scrape_age:.0f}h old — fresh."
                                 if _in_scrape_fresh else "")):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "core", "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Core scrape"}
                st.toast("⚡ Core scrape launched!", icon="🚀")
                st.rerun()
            if _in_scrape_fresh:
                st.caption(f"🟢 Scan is {_in_scrape_age:.0f}h old — fresh enough")
            render_gmail_trash_panel()
            _vc_download_row("inputs")

        # ── ② WORKLIST ────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown(
                f"#### 📋 ② Worklist · {_stage_chip(False, _wl_ok, empty=_pipe_empty)} "
                f"{_wstats.get('total', 0):,} rows"
            )
            if _pipe_empty:
                st.caption("⏸ Will activate after the first scrape / Gmail "
                           "fetch populates the pool.")
            else:
                # Hidden-by-mute annotation (doc §370): how many pool rows an
                # active mute would suppress at triage. Cached on file mtimes.
                _wl_p = OUT_DIR / "worklist.json"
                _supp_p = ROOT / "data" / "suppressions.json"
                _hidden, _n_mutes = _worklist_hidden_by_mutes(
                    _wl_p.stat().st_mtime if _wl_p.exists() else 0.0,
                    _supp_p.stat().st_mtime if _supp_p.exists() else 0.0,
                )
                _mute_note = (
                    f" · 🔇 {_hidden} hidden by {_n_mutes} mute"
                    f"{'s' if _n_mutes != 1 else ''}" if _hidden else ""
                )
                # Richer dedup picture: exact-URL + near-dup merges and the
                # new-since-last-score count. dedup_stats isn't in
                # worklist.status(), so read it straight from the envelope
                # (one cheap guarded read; the table reads this file anyway).
                _dedup = {}
                try:
                    _wl_env = json.loads(_wl_p.read_text(encoding="utf-8"))
                    _dedup = _wl_env.get("dedup_stats") or {}
                except Exception:
                    _dedup = {}
                _merge_bits = ""
                _dx, _dn = _dedup.get("dropped_url"), _dedup.get("dropped_near")
                if _dx or _dn:
                    _merge_bits = (f" · ✂️ {_dx or 0} exact + {_dn or 0} "
                                   f"near-dup merged")
                _new_n = _wstats.get("new_since_last_score")
                _new_bits = f" · 🆕 {_new_n:,} new since last score" if _new_n else ""
                st.caption(
                    f"🛰 {_wstats.get('scrape', 0):,} scrape · "
                    f"📬 {_wstats.get('gmail', 0):,} gmail · "
                    f"🔁 {_wstats.get('both', 0):,} both"
                    + _merge_bits + _new_bits + _mute_note
                )
            # Auto-open the worklist table right after a rebuild/scrape/Gmail
            # completes so the user immediately sees the fresh deduped pool.
            # Compares worklist.status()'s rebuilt_at to a session cache. On the
            # FIRST Pipeline render of a session we seed the cache to the
            # current value so a cold load stays CLOSED (perf — ~1,400 rows);
            # it only auto-opens on a rebuild that happens DURING the session.
            _rebuilt = _wstatus.get("rebuilt_at")
            if "_seen_rebuilt_at" not in st.session_state:
                st.session_state["_seen_rebuilt_at"] = _rebuilt   # cold-load seed
            elif _rebuilt and _rebuilt != st.session_state["_seen_rebuilt_at"]:
                st.session_state["_vc_inspect_worklist"] = True   # force open
                st.session_state["_seen_rebuilt_at"] = _rebuilt   # one-shot
            if _vc_inspect_toggle("worklist", "Inspect worklist rows"):
                if _rebuilt:
                    st.caption(f"🕒 Worklist rebuilt {_rebuilt}")
                _render_worklist_card()
            _vc_download_row("worklist")

    # ═══════════════ ② SCORE view: ③ Triage + ④ Scoring ═════════════
    if _pipe_view == "Score":
        # ── ③ TRIAGE ──────────────────────────────────────────────────
        with st.container(border=True):
            _tr_in = score_input or scrape_count or 0
            _tr_pass = score_pass or 0
            _tr_drop = (_tr_in - _tr_pass) if _tr_in else 0
            _tr_ratio = f"{int(100*_tr_drop/_tr_in)}%" if _tr_in else "—"
            st.markdown(
                f"#### 🎯 ③ Triage · {_stage_chip(False, bool(_tr_pass), empty=_pipe_empty)} "
                f"{_tr_pass:,} passed · {_tr_drop:,} dropped ({_tr_ratio})"
            )
            st.caption(
                "Rule-based keyword/level/negative-term filter + active "
                "suppressions. Run a free triage below to see the per-drop "
                "rule reasons in the 👁 Triage preview (or the Triage xlsx)."
            )
            # 🎯 Run triage — standalone, FREE (no LLM). Runs run_pipeline with
            # --score-dry-run --triage-out so stage-1 rule triage runs alone and
            # writes the passed/dropped split to a SEPARATE worklist_triage.json
            # (never clobbers the real LLM scores in worklist_scored.json). The
            # drops surface in the 👁 Triage preview directly below — NOT the ④
            # Scoring card's Dropped sub-tab, which only lists *_scored.json.
            # Lets you review WHICH rows drop and why BEFORE spending on the LLM.
            # Triage is deterministic + free, so re-running Score afterwards
            # yields the identical set (unless the worklist changed in between).
            _tr_total = _wstats.get("total", 0)
            _tr_label = (f"🎯 Run triage (free · {_tr_total} rows)" if _tr_total
                         else "🎯 Run triage (no rows)")
            if st.button(_tr_label, width="stretch", key="_vc_triage_run",
                         disabled=(any_work_active or not _tr_total),
                         help="Rule-stage only — no API cost. Produces the "
                              "passed/dropped split; inspect the drops in the "
                              "👁 Triage preview just below, then Score "
                              "when you're happy with what's kept."):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--skip-scrape", "--skip-promote", "--score-dry-run",
                    "--triage-out", "worklist_triage.json",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Run triage"}
                st.toast("🎯 Triage launched (free)!", icon="🚀")
                st.rerun()

            # Triage preview — reads the standalone worklist_triage.json the
            # button above produces (separate file, never clobbers the real
            # LLM scores in worklist_scored.json). Lets you see WHICH rows drop
            # and why before paying. Gated behind a toggle so we don't read the
            # file every rerun.
            _tr_preview = OUT_DIR / "worklist_triage.json"
            if _tr_preview.exists():
                _tr_age = _file_age_hours(_tr_preview)
                _tr_age_s = (f"{_tr_age*60:.0f}m ago" if _tr_age is not None
                             and _tr_age < 1 else
                             f"{_tr_age:.0f}h ago" if _tr_age is not None
                             else "")
                if _vc_inspect_toggle(
                        "triage_preview",
                        f"👁 Triage preview — which rows dropped ({_tr_age_s})"):
                    try:
                        _tp = json.loads(_tr_preview.read_text(encoding="utf-8"))
                    except Exception:
                        _tp = {}
                    _tp_drops = _tp.get("triage_drops") or []
                    _tp_pass = _tp.get("stage1_passed", 0)
                    _tp_drop = _tp.get("stage1_dropped", len(_tp_drops))
                    st.caption(
                        f"Free rule-triage preview · {_tp_pass:,} would pass · "
                        f"{_tp_drop:,} would drop. Your LLM scores are untouched "
                        "— hit 🤖 Score worklist below when you're happy."
                    )
                    if _tp_drops:
                        _tpb = pipeline_state.categorize_drop_reasons(_tp_drops)
                        _tp_hist = pd.DataFrame(
                            [{"reason": k, "count": v}
                             for k, v in _tpb["by_category"].items()])
                        if not _tp_hist.empty:
                            st.markdown("**Drop reasons (histogram)**")
                            st.dataframe(_tp_hist, hide_index=True,
                                         width='stretch', height=180)
                        _tp_q = st.text_input(
                            "Search company/title in dropped rows",
                            key="triage_preview_q",
                            placeholder="scotiabank / data engineer / ...")
                        _tp_rows = []
                        for d in _tp_drops:
                            co, ti = d.get("company", ""), d.get("title", "")
                            if _tp_q:
                                q = _tp_q.lower()
                                if q not in co.lower() and q not in ti.lower():
                                    continue
                            _tp_rows.append({
                                "company": co, "title": ti,
                                "why": ", ".join(d.get("rule_reasons", []))[:120],
                                "score": d.get("score", 0),
                                "source": d.get("source", ""),
                                "url": d.get("link", ""),
                            })
                        st.caption(f"Showing {len(_tp_rows):,} of {len(_tp_drops):,}")
                        if _tp_rows:
                            st.dataframe(
                                pd.DataFrame(_tp_rows), hide_index=True,
                                width='stretch', height=380,
                                column_config={
                                    "url": st.column_config.LinkColumn("open")})

            # Suppression admin lives here (doc §280) — gated behind a toggle
            # so the page doesn't re-read the registry every rerun.
            if _vc_inspect_toggle("triage", "Manage suppressions (mutes)"):
                _render_suppressions_admin()
            _vc_download_row("triage")

        # ── ④ SCORING ─────────────────────────────────────────────────
        with st.container(border=True):
            # Stale-detection now uses the SHA8-based consistency check
            # (pipeline_state.derive_consistency) instead of ad-hoc mtime
            # comparisons. Stale = scored snapshot's input sha8 ≠ current
            # worklist sha8, i.e. it was built against a different worklist
            # than what's on disk now. Strictly more accurate than mtime:
            # an mtime can change without the row set changing (file got
            # rewritten with identical content), and the row set can change
            # without mtime moving by much (worklist grew but stayed today).
            _sc_scored_path = OUT_DIR / "worklist_scored.json"
            _sc_wl_path = OUT_DIR / "worklist.json"
            _sc_tr_path = OUT_DIR / "worklist_triage.json"
            _sc_scored_age_h = _file_age_hours(_sc_scored_path)
            _sc_wl_age_h = _file_age_hours(_sc_wl_path)
            _sc_tr_age_h = _file_age_hours(_sc_tr_path)
            try:
                _sc_cons = pipeline_state.derive_consistency(OUT_DIR)
            except Exception:
                _sc_cons = None
            # Three layers of stale, in priority order:
            #   1. Scored exists but has no input breadcrumb → can't prove
            #      consistency. Show as stale (don't pretend ✅).
            #   2. Scored has breadcrumb but it doesn't match current
            #      worklist sha8 → definite drift.
            #   3. Fallback (consistency check unavailable) → mtime
            #      heuristic, same as before.
            if _sc_cons is not None and _sc_cons.scored.exists:
                if _sc_cons.scored.input_sha8 is None:
                    _sc_is_stale = True
                else:
                    _sc_is_stale = not _sc_cons.scored.is_consistent
            else:
                _sc_is_stale = (
                    _sc_scored_age_h is not None
                    and (
                        (_sc_wl_age_h is not None and _sc_scored_age_h > _sc_wl_age_h)
                        or (_sc_tr_age_h is not None and _sc_scored_age_h > _sc_tr_age_h)
                    )
                )

            def _fmt_age(h):
                if h is None:
                    return ""
                if h < 1:
                    return f"{h*60:.0f}m"
                if h < 24:
                    return f"{h:.0f}h"
                return f"{h/24:.0f}d"

            # Incompleteness (aborted run) — read from the consistency object
            # computed above. A run truncated by the cost cap leaves rows with
            # placeholder `skip` verdicts; surface them distinctly so "739
            # scored" doesn't overstate real coverage.
            _sc_unscored = (_sc_cons.scored.unscored_count
                            if _sc_cons and _sc_cons.scored.exists else 0)
            _sc_incomplete = bool(_sc_cons and _sc_cons.scored.exists
                                  and _sc_cons.scored.incomplete)
            if scorer_running:
                _sc_chip = "🟡 running"
            elif _pipe_empty and not score_count:
                _sc_chip = "⏸"
            elif _sc_incomplete and score_count:
                _sc_chip = f"🟠 incomplete ({_sc_unscored:,} unscored)"
            elif _sc_is_stale and score_count:
                _sc_chip = f"🟠 stale ({_fmt_age(_sc_scored_age_h)} old)"
            else:
                _sc_chip = "🟢" if _scored_ok else "⚪"
            _sc_count_blurb = (f"{score_count:,} scored"
                               if score_count else "not scored yet")
            if _sc_incomplete and score_count:
                _sc_real = max(score_count - _sc_unscored, 0)
                _sc_count_blurb = (
                    f"{score_count:,} rows — {_sc_unscored:,} unscored "
                    f"(cost cap/API), {_sc_real:,} real")
            elif _sc_is_stale and score_count:
                _sc_count_blurb += " — snapshot pre-dates current triage pool"
            st.markdown(f"#### 🤖 ④ Scoring · {_sc_chip} {_sc_count_blurb}")

            # 🤖 Score worklist — the stage's primary launch action. Relocated
            # here from the Promote run card (v3.2 strict split): scoring is what
            # the ② Score view is FOR, so its launch belongs on the ④ card, not
            # the promote card (doc §154). Guards recomputed locally — the
            # run-card locals aren't in scope here.
            _sc_key_ok = api_key.is_key_valid()
            _sc_can_run = not any_work_active
            _sc_ws_total = _wstats.get("total", 0)
            _sc_age_h = _sc_scored_age_h  # alias kept for downstream uses
            _sc_fresh = _sc_age_h is not None and _sc_age_h < 0.5

            # ── Pre-score preview ──────────────────────────────────────
            # Reads worklist_triage.json (the standalone preview written by
            # the free 🎯 Run triage button) and breaks the post-triage pool
            # into:
            #   • cached       — has fit_cache_v2 file → free re-score
            #   • in_scored    — URL in previous worklist_scored.json (free
            #                    via fit_scorer's second-chance read)
            #   • needs_llm    — no cache, no prior score → actual paid call
            # Falls back gracefully when the preview file is absent (user
            # hasn't clicked 🎯 Run triage yet on the current worklist).
            _sc_pre_total = None  # post-triage row count, or None if no preview
            _sc_pre_cached = 0
            _sc_pre_needs = 0
            _sc_pre_stale_scored = 0
            if _sc_tr_path.exists():
                try:
                    import sys as _sp_sys
                    _ad = str(ROOT / "automation")
                    if _ad not in _sp_sys.path:
                        _sp_sys.path.insert(0, _ad)
                    from fit_scorer import _url_hash as _sp_url_hash  # type: ignore
                    _sp_tp = json.loads(_sc_tr_path.read_text(encoding="utf-8"))
                    _sp_rows = _sp_tp.get("results") or []
                    _sp_fit_dir = OUT_DIR / "fit_cache"
                    _sp_scored_urls: set[str] = set()
                    if _sc_scored_path.exists():
                        try:
                            _sp_sc = json.loads(
                                _sc_scored_path.read_text(encoding="utf-8"))
                            for _r in _sp_sc.get("results", []) or []:
                                _u = _r.get("link") or _r.get("url") or ""
                                if _u:
                                    _sp_scored_urls.add(_u)
                        except Exception:
                            pass
                    _sc_pre_total = len(_sp_rows)
                    for _r in _sp_rows:
                        _u = _r.get("link") or _r.get("url") or ""
                        if not _u:
                            continue
                        try:
                            _has_cache = (_sp_fit_dir
                                          / f"{_sp_url_hash(_u)}.v2.json").exists()
                        except Exception:
                            _has_cache = False
                        _in_sc = _u in _sp_scored_urls
                        if _has_cache:
                            _sc_pre_cached += 1
                        # "Free via prior snapshot" = in the previous scored
                        # file but cache file is gone (second-chance read
                        # reuses the verdict without paying). cached wins
                        # over this bucket via the `not _has_cache` guard.
                        if _in_sc and not _has_cache:
                            _sc_pre_stale_scored += 1
                        if not _has_cache and not _in_sc:
                            _sc_pre_needs += 1
                except Exception:
                    _sc_pre_total = None  # treat any failure as "no preview"

            if _sc_pre_total is not None:
                with st.container(border=True):
                    st.markdown(
                        f"**🔎 Score preview** · {_sc_pre_total:,} in today's "
                        f"triage pool (preview written {_fmt_age(_sc_tr_age_h)} ago)"
                    )
                    _c1, _c2, _c3 = st.columns(3)
                    _c1.metric("Already scored (free)",
                               f"{_sc_pre_cached:,}",
                               help="Has a fit_cache_v2 file on disk — re-score "
                                    "skips the LLM call.")
                    _c2.metric("Need scoring (paid)",
                               f"{_sc_pre_needs:,}",
                               help="No cache and not in any previous scored "
                                    "snapshot — these are the actual LLM calls.")
                    _c3.metric("Free via prior snapshot",
                               f"{_sc_pre_stale_scored:,}",
                               help="URL is in worklist_scored.json but the "
                                    "fit_cache file is missing — fit_scorer's "
                                    "second-chance read reuses the prior verdict "
                                    "without paying.")
                    if _sc_pre_needs == 0:
                        st.caption("✅ Nothing to pay for — every triage-passing "
                                   "row already has a cache hit or prior verdict.")
                    elif _sc_is_stale:
                        st.caption(
                            f"⚠️ Prior `worklist_scored.json` is {_fmt_age(_sc_scored_age_h)} "
                            f"old and was built before today's triage. Re-scoring "
                            "will pay for the "
                            f"{_sc_pre_needs:,} uncached row(s) and refresh the snapshot."
                        )

                    # ── Estimated cost vs the per-run cost cap ───────────
                    # Surfaces what the paid rows will cost AND the cost_guard
                    # cap, so a run that would truncate (like the $2 cap that
                    # stamped 126 rows as unscored) is visible BEFORE you click
                    # — with the exact env var to raise it.
                    if _sc_pre_needs > 0:
                        # Observed ~$0.0045/row for Haiku scoring; round up a
                        # touch so the estimate trends conservative.
                        _EST_PER_PAID_ROW = 0.005
                        _est_cost = _sc_pre_needs * _EST_PER_PAID_ROW
                        try:
                            from cost_guard import CostGuard as _CG  # type: ignore
                            _run_cap = _CG.from_env().per_run_cap_usd
                        except Exception:
                            _run_cap = None
                        _cost_line = (
                            f"💵 Est. **~${_est_cost:.2f}** for {_sc_pre_needs:,} "
                            f"paid row(s) (~${_EST_PER_PAID_ROW:.3f} each)")
                        if _run_cap is not None:
                            _cost_line += f" · per-run cap **${_run_cap:.2f}**"
                        st.caption(_cost_line)
                        if _run_cap is not None and _est_cost > _run_cap:
                            _affordable = int(_run_cap / _EST_PER_PAID_ROW)
                            _suggest = max(1.0, round(_est_cost * 1.2 + 0.49))
                            st.warning(
                                f"⚠️ The estimate (~${_est_cost:.2f}) exceeds the "
                                f"per-run cap (${_run_cap:.2f}) — the run will stop "
                                f"after ~{_affordable:,} paid rows and stamp the "
                                f"rest as unscored `skip`s. To finish in one pass, "
                                f"raise the cap: set the env var "
                                f"`COST_GUARD_PER_RUN_CAP_USD={_suggest:.0f}` before "
                                f"launching (daily cap also applies).",
                                icon=None)
                        elif _run_cap is not None:
                            st.caption(
                                "💡 Tip: the per-run cap is a safety brake. For a "
                                "large first-pass run, raise it with "
                                "`COST_GUARD_PER_RUN_CAP_USD` (e.g. `4`).")
            else:
                st.caption("ℹ️ Run 🎯 **Run triage** above to see a per-row "
                           "cached-vs-paid breakdown before scoring.")

            # Button label now reflects ACTUAL paid work when the preview is
            # available; falls back to worklist row count otherwise.
            if _sc_pre_total is not None and _sc_ws_total:
                _sc_label = (f"🤖 Score worklist ({_sc_pre_needs:,} to pay · "
                             f"{_sc_pre_cached + _sc_pre_stale_scored:,} free)")
            else:
                _sc_label = (f"🤖 Score worklist ({_sc_ws_total})" if _sc_ws_total
                             else "🤖 Score (no rows)")
            _sc_help = (f"Score the {_sc_ws_total}-row worklist. ~5–15 min on "
                        "first run, near-free on re-runs (fit_cache is "
                        "persistent). Requires API key.")
            if _sc_pre_total is not None:
                _sc_help += (f" Today's triage pool: {_sc_pre_total:,} rows, of "
                             f"which {_sc_pre_needs:,} would hit the LLM.")
            if not _sc_key_ok:
                _sc_help += " 🔑 Set an API key in the sidebar first."
            elif _sc_fresh and not _sc_is_stale:
                _sc_help += (f" ⚠️ Last score {_sc_age_h*60:.0f}m ago — "
                             "rescore only if rows changed.")
            elif _sc_is_stale:
                _sc_help += (f" 🟠 Last score {_fmt_age(_sc_scored_age_h)} old "
                             "and pre-dates current triage pool.")
            if st.button(_sc_label, width="stretch", key="_vc_scoring_score_worklist",
                         type="primary" if (_sc_key_ok and _sc_ws_total) else "secondary",
                         disabled=(not _sc_can_run or not _sc_key_ok or not _sc_ws_total),
                         help=_sc_help):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--skip-scrape", "--skip-promote",
                    "--score-concurrency", "6",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id,
                                                    "label": "Score worklist"}
                st.toast("🤖 Scorer launched!", icon="🚀")
                st.rerun()
            if _sc_fresh and _sc_key_ok and _sc_ws_total:
                st.caption(f"⚠️ Scored {_sc_age_h*60:.0f}m ago")
            # Always-visible operational summary of the last run (cached vs new,
            # model, errors, logs). While a run is live it defers to the live
            # progress panel rendered above the cards.
            _render_scorer_status(scorer_running=scorer_running)
            # Scored card hosts the suppression admin + triage sub-tabs +
            # manual-selection promote. Heavy body is button-gated.
            if _vc_inspect_toggle("scoring", "Inspect verdicts + manage suppressions",
                                  default=True):
                _render_scored_card()
            # 🔗 Score-a-single-URL — manual side-channel scorer, persistent
            # expander on the ④ card (doc §575/§155). Relocated from the Promote
            # run card with the rest of the scoring controls.
            _render_score_a_url()
            _vc_download_row("scored")

    # ═══════════════ ③ PROMOTE view: ⑤ Promote + ⑥ Tracker ═════════
    if _pipe_view == "Promote":
        # ── ⑤ PROMOTE (one-click bulk + per-row cherry-pick) ───────────
        # Consolidated promote surface. Replaces the old split of a separate
        # ⑤ Auto-promote card + a 📋 Pick & promote card: both shelled the
        # SAME engine (auto_promote.py), and with no active suppressions and
        # nothing scheduling unattended promotion, the standalone auto-promote
        # card was redundant. Now one card offers both paths:
        #   • ⚡ Promote all N qualifying → auto_promote.py --commit (bulk)
        #   • 📋 Examine & select        → per-row table, --only-urls commit
        # Reuses _render_scored_card / the "scored" download verbatim; the
        # ② Score and ③ Promote views are mutually-exclusive branches, so no
        # widget-key collision and selection state carries over between them.
        with st.container(border=True):
            # Post-suppression promotable count (above threshold, deduped vs
            # tracker, minus active mutes) — same figure the banner computes.
            # Fall back to actionable_n only if the snapshot couldn't compute.
            if _promotable_n is not None:
                _promo_headline = (
                    f"{_promotable_n} ready at fit≥7 (after suppressions)"
                    if _promotable_n else "nothing promotable yet"
                )
            else:
                _promo_headline = (
                    f"{actionable_n} actionable at fit≥7" if actionable_n
                    else "nothing promotable yet"
                )
            st.markdown(
                f"#### 📤 ⑤ Promote · "
                f"{_stage_chip(False, _ws_scored_exists, empty=not _ws_scored_exists)} "
                + _promo_headline
            )
            st.caption(
                "Promote scored candidates to the tracker: one-click ⚡ promote "
                "everything qualifying (fit≥7, deduped, minus any mutes), or "
                "examine and tick specific rows below. Reads worklist_scored.json."
            )

            # ⚡ One-click bulk — promote ALL qualifying (the old ⑤ Auto-promote
            # behavior). auto_promote.py --commit applies the fit≥7 threshold,
            # tracker-dedup, and suppressions itself, so the committed set
            # matches the headline count. ≥25 needs an explicit confirm so one
            # click can't bulk-write dozens of rows.
            _pa_n = _promotable_n if _promotable_n is not None else (actionable_n or 0)
            if _pa_n:
                _pa_confirm = True
                if _pa_n >= 25:
                    _pa_confirm = st.checkbox(
                        f"⚠️ Confirm: promote all {_pa_n} qualifying roles "
                        "(large batch)", key="promote_all_confirm")
                if st.button(
                        f"⚡ Promote all {_pa_n} qualifying (fit≥7) → tracker",
                        type="primary",
                        disabled=any_work_active or not _pa_confirm,
                        key="promote_all_qualifying",
                        help="Bulk-commit every above-threshold role not already "
                             "in the tracker (auto_promote.py --commit). For "
                             "specific rows only, use the table below."):
                    _prec = scan_runner.start_run("promote", [
                        sys.executable,
                        str(ROOT / "automation" / "auto_promote.py"),
                        "--commit",
                    ])
                    st.session_state["_last_launch"] = {
                        "run_id": _prec.run_id, "label": "Promote all qualifying"}
                    st.toast(f"Promoting {_pa_n} qualifying role(s)…", icon="📤")
                    st.rerun()

            # Banner-driven preview→commit: when the next-action banner's
            # promote CTA has run a fresh dry-run, surface its "✅ Apply N to
            # tracker" commit button here. Contextual — stays quiet unless a
            # recent dry-run report exists. (The one-click button above is the
            # no-preview direct path; this is the preview-then-commit path.)
            _vc_promote_apply_panel(any_work_active)

            # Downloads: scored candidate list (xlsx incl. sector) + promote
            # report (what the last commit added).
            _vc_download_row("scored")
            _vc_download_row("promote")

            # 📋 Per-row examine + cherry-pick — the full scored table with
            # filters, checkboxes, and "Send N selected to tracker".
            if _vc_inspect_toggle("promote_pick",
                                  "📋 Examine & select specific candidates",
                                  default=True):
                _render_scored_card()

        # ── ⑥ TRACKER ─────────────────────────────────────────────────
        with st.container(border=True):
            _arch = sum(1 for j in jobs if j.get("archived"))
            st.markdown(
                f"#### 🗂 ⑥ Tracker · {len(jobs) - _arch} active · "
                f"{tracker_found} to review"
            )
            st.caption(
                f"{tracker_found} Found/Watch · {tracker_applied} applied"
                + (f" · {_arch} archived" if _arch else "")
            )
            _tc1, _tc2, _tc3 = st.columns(3)
            if _tc1.button("→ Jobs Kanban", width="stretch", key="_vc_go_kanban"):
                st.session_state["_pending_main_nav"] = "📋 Roles"
                st.session_state["_nav_sub_📋 Roles"] = "Tracker"
                st.rerun()
            if _tc2.button("→ Review Queue", width="stretch", key="_vc_go_review"):
                st.session_state["_pending_main_nav"] = "🏠 Today"
                st.session_state["_nav_sub_🏠 Today"] = "Review"
                st.rerun()
            if _tc3.button("→ Today's brief", width="stretch", key="_vc_go_today"):
                st.session_state["_pending_main_nav"] = "🏠 Today"
                st.session_state["_nav_sub_🏠 Today"] = "Dashboard"
                st.rerun()
            # Tracker downloads (doc §178): raw JSON + per-status xlsx.
            _vc_download_row("tracker")

        # ── Footer: full audit pack + history (re-homed, not dropped) ──
        st.markdown("---")
        with st.expander("📦 Download full audit pack (all stages, one xlsx)",
                         expanded=False):
            _vc_audit_pack_download()
        with st.expander("📜 Run history (pipelines · logs · cost)",
                         expanded=False):
            if st.button("→ Open Scan History page", key="_vc_go_scan_history",
                         help="Full scan/run history with per-scan drill-in."):
                # Scan History now lives INSIDE 🎯 Pipeline, so this is a
                # within-group jump: stash the sub-view in _pipe_pending_view
                # (transferred to the sub-radio key before it instantiates).
                st.session_state["_pipe_pending_view"] = "History"
                st.rerun()
            _render_history_card()


# ============================================================================
# 📋 JOBS KANBAN
# ============================================================================
elif page == "📋 Jobs Kanban":
    st.title("📋 Jobs Tracker")

    # Live panel: tracker mutates during pipeline runs. Surface progress here
    # so users on Kanban don't act on stale data.
    _pipeline_live_panel()

    # Stale-scan banner: warn when underlying source data is aging.
    _kan_scan_age_h = _web_scan_age_hours()
    if _kan_scan_age_h is not None and _kan_scan_age_h >= 48:
        _days = _kan_scan_age_h / 24
        st.info(
            f"🛰 Web scan is **{_days:.0f}d old**. New roles you'd see in "
            "Found may be missing. Consider running a scrape from the "
            "🎯 Pipeline page.",
            icon="⏰",
        )

    # ── Kanban summary strip ──────────────────────────────────────────────────
    _kan_statuses = {}
    _STATUS_ORDER = [
        ("Found","🔍"), ("Watch","👀"), ("Tailoring","✍️"), ("Applied","📤"),
        ("Recruiter_Screen","📞"), ("Phone_Screen","📱"), ("Take_Home","💻"),
        ("Onsite","🏢"), ("Offer","🎉"), ("Rejected","❌"), ("Withdrawn","⚪"),
        ("Expired","🕐"),
    ]
    _ACTIVE_STATUSES = {"Found", "Watch", "Tailoring", "Applied",
                        "Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite"}
    # Phase 3D — separate archived rows from the status histogram so they
    # don't inflate "Found / Watch / Applied" counts. Surface as their own
    # tile in the strip.
    _fu_overdue_count = 0
    _archived_count = 0
    for _jj in jobs:
        if _jj.get("archived", False):
            _archived_count += 1
            continue
        _ss = _jj.get("status", "?")
        _kan_statuses[_ss] = _kan_statuses.get(_ss, 0) + 1
        _fu_next = _jj.get("followup_schedule", {}).get("next_due")
        if _fu_next and parse_date(_fu_next) and parse_date(_fu_next) < date.today():
            _fu_overdue_count += 1
    _active_total = sum(v for k, v in _kan_statuses.items() if k in _ACTIVE_STATUSES)
    _active_stages = [s for s, _ in _STATUS_ORDER if s in _kan_statuses]
    if _active_stages:
        _ks_cols = st.columns(min(len(_active_stages), 8))
        for _kci, (_ks, _ke) in enumerate([(s, e) for s, e in _STATUS_ORDER if s in _kan_statuses]):
            _kci_mod = _kci % 8
            _ks_cols[_kci_mod].metric(f"{_ke} {_ks.replace('_', ' ')}", _kan_statuses[_ks])
    if _fu_overdue_count:
        st.warning(f"**{_fu_overdue_count} role{'s' if _fu_overdue_count != 1 else ''} with overdue follow-ups** — filter Status = Applied to find them.", icon="🔴")
    _archived_suffix = f" · {_archived_count} archived" if _archived_count else ""
    st.caption(f"{_active_total} active · {len(jobs)} total tracked"
                f"{_archived_suffix}")

    # Phase 5 — Active suppressions read-only mirror. The mute action lives
    # on Review Queue, the admin lives on Pipeline → Scored tab. This thin
    # expander surfaces the same registry on the Tracker so the user doesn't
    # have to context-switch to see what's currently muted while triaging
    # the Kanban. Read-only by design — manage from the Pipeline page.
    try:
        from automation import suppressions as _kan_supp  # noqa: WPS433
        _kan_active = _kan_supp.load_active()
        _kan_sec = _kan_active.get("sectors") or []
        _kan_co = _kan_active.get("companies") or []
        _kan_n = len(_kan_sec) + len(_kan_co)
        _kan_label = (
            f"🔇 Active suppressions ({_kan_n})" if _kan_n
            else "🔇 Active suppressions"
        )
        with st.expander(_kan_label, expanded=False):
            if _kan_n == 0:
                st.markdown("_No active mutes._")
            else:
                from datetime import date as _kan_date  # noqa: WPS433
                _kan_today = _kan_date.today()
                for _kan_e in _kan_sec + _kan_co:
                    _kan_name = _kan_e.get("name", "?")
                    _kan_scope = _kan_e.get("scope", "?")
                    _kan_until = _kan_e.get("until")
                    _kan_reason = _kan_e.get("reason", "") or ""
                    with st.container(border=True):
                        st.markdown(
                            f"**{_kan_name}** _{_kan_scope}_  ·  "
                            f"{pipeline_state.format_until_label(_kan_until, _kan_today)}"
                            f"  ·  reason: \"{_kan_reason}\""
                        )
            st.caption(
                "Manage these from the Pipeline page → Scored tab → "
                "🔇 Active suppressions panel."
            )
    except Exception as _kan_supp_exc:  # noqa: BLE001
        # Fail soft — a corrupt registry shouldn't break the Kanban page.
        st.caption(
            f"_(Could not read suppressions: {_kan_supp_exc})_"
        )

    st.markdown("---")

    if jobs_df.empty:
        st.info("Tracker is empty — promote a scored job from 🎯 Pipeline.")
        st.stop()

    # Derive gta_area for every row — prefer explicit location, fall back to
    # URL slug inference (for pre-location-field tracker entries).
    def _area_for_row(row) -> str:
        loc = row.get("location") if isinstance(row, dict) else getattr(row, "location", None)
        url = row.get("url") if isinstance(row, dict) else getattr(row, "url", None)
        if loc:
            a = gta_area_for(loc)
            if a != "—":
                return a
        if url:
            # Extract city slug from /job/<city>/... (Phenom etc.) or location token in URL
            m = re.search(r"/job/([a-z\-]+)/", str(url).lower())
            if m:
                a = gta_area_for(m.group(1).replace("-", " "))
                if a != "—":
                    return a
            # Any GTA city token in the URL at large
            for label, toks in _GTA_AREAS:
                for t in toks:
                    if t.replace(" ", "-") in str(url).lower() or t in str(url).lower():
                        return label
        return "—"

    if not jobs_df.empty:
        jobs_df = jobs_df.assign(gta_area=jobs_df.apply(_area_for_row, axis=1))

    # Filters
    f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 2])
    sectors = sorted(jobs_df["sector"].dropna().unique()) if "sector" in jobs_df.columns else []
    statuses = sorted(jobs_df["status"].dropna().unique()) if "status" in jobs_df.columns else []
    fits = sorted(jobs_df["fit_score"].dropna().unique()) if "fit_score" in jobs_df.columns else []
    areas = sorted(jobs_df["gta_area"].dropna().unique()) if "gta_area" in jobs_df.columns else []
    with f1:
        sel_sector = st.multiselect("Sector", sectors, default=[])
    with f2:
        sel_status = st.multiselect("Status", statuses, default=[])
    with f3:
        sel_fit = st.multiselect("Fit", fits, default=[])
    with f4:
        sel_tier = st.multiselect("Tier", sorted(jobs_df["tier"].dropna().unique()) if "tier" in jobs_df.columns else [])
    with f5:
        sel_area = st.multiselect("GTA area", areas, default=[])
    q = st.text_input("Search (company/title)", "", placeholder="e.g. Scotiabank, ALM...")

    view = jobs_df.copy()
    if sel_sector:
        view = view[view["sector"].isin(sel_sector)]
    if sel_status:
        view = view[view["status"].isin(sel_status)]
    if sel_fit:
        view = view[view["fit_score"].isin(sel_fit)]
    if sel_tier:
        view = view[view["tier"].isin(sel_tier)]
    if sel_area:
        view = view[view["gta_area"].isin(sel_area)]
    if q:
        qlo = q.lower()
        view = view[view["company"].str.lower().str.contains(qlo, na=False) |
                    view["title"].str.lower().str.contains(qlo, na=False)]

    _filter_active = any([sel_sector, sel_status, sel_fit, sel_tier, sel_area, q])
    st.caption(f"Showing {len(view)} of {len(jobs_df)} roles" + (" (filtered)" if _filter_active else ""))

    # Enrich view with a "draft" indicator based on whether a tailor output
    # exists for this role. Uses the canonical _find_tailor_docs() helper
    # (defined near the top of this file) so the lookup matches every other
    # tailor-doc check across the UI.
    # Load url_history once and enrich rows with posted/found
    _url_hist_path = OUT_DIR / "url_history.json"
    try:
        _url_hist = json.loads(_url_hist_path.read_text(encoding="utf-8")) if _url_hist_path.exists() else {}
    except Exception:
        _url_hist = {}

    def _freshness(url: str) -> str:
        entry = _url_hist.get(url or "") or {}
        return freshness_badge(None, entry.get("found_at"))

    if "company" in view.columns and "title" in view.columns:
        view = view.assign(
            draft=view.apply(
                lambda row: "📄 ready" if bool(_find_tailor_docs(row)) else "",
                axis=1,
            )
        )
    if "url" in view.columns:
        view = view.assign(freshness=view["url"].apply(_freshness))

    # Provenance badge: rows promoted from a Gmail-alert scan get a 📬
    # marker so it's visible at a glance which leads came from inbox
    # alerts vs. scraped postings. auto_promote.py preserves the original
    # gmail_* source as a "<source>+fit_scorer" composite.
    if "source" in view.columns:
        # Worklist source tags get rendered as compact badges:
        #   📬 = surfaced via Gmail alert only
        #   🛰 = surfaced via web scrape only
        #   🔁 = surfaced via both (highest-confidence — multiple paths)
        # Legacy source strings fall back: "gmail_*" → 📬, anything else → 🛰.
        def _src_badge(s):
            if not isinstance(s, str):
                return ""
            if "scrape+gmail" in s:
                return "🔁"
            if s.startswith("gmail"):
                return "📬"
            if s.startswith("scraper"):
                return "🛰"
            return ""
        view = view.assign(src=view["source"].apply(_src_badge))

    # Warm-intro column: compact badge for CRM matches.
    if "company" in view.columns:
        def _warm_count(co):
            if not isinstance(co, str) or not co:
                return ""
            n = len(crm_contacts_at_company(crm, co))
            return f"🤝{n}" if n else ""
        view = view.assign(warm=view["company"].apply(_warm_count))

    # Follow-up due indicator — surfaces overdue/upcoming follow-ups
    # directly in the table so they are visible without opening inspector.
    if "followup_schedule" in view.columns:
        def _fu_badge(fs):
            if not isinstance(fs, dict):
                return ""
            nxt = parse_date(fs.get("next_due"))
            if not nxt:
                return ""
            delta = (nxt - date.today()).days
            if delta < 0:
                return f"🔴 {abs(delta)}d ago"
            if delta == 0:
                return "🟡 today"
            if delta <= 3:
                return f"🟡 in {delta}d"
            return ""
        view = view.assign(follow_up=view["followup_schedule"].apply(_fu_badge))

    # Compact-by-default columns — clicking a row opens the full inspector,
    # so the table only needs to be SCANNABLE. Lead with the essentials;
    # the mostly-empty badge columns (Draft/Follow-up/Warm) and low-value
    # context (Variant/Area/sector/Src/Age/Applied) move behind a toggle so
    # they don't shove company/title off the left edge.
    _show_all_cols = st.checkbox(
        "Show all columns", value=False, key="kanban_show_all_cols",
        help="Off (compact): company · title · status · T · Fit · Urg · "
             "Found · Link. On: also Follow-up · Warm · Draft · Variant · "
             "Area · sector · Applied · Src · Age.",
    )
    _compact_cols = ["company", "title", "status", "tier",
                     "fit_score_numeric", "urgency", "date_found", "url"]
    _full_cols = ["company", "title", "status", "tier", "fit_score_numeric",
                  "urgency", "follow_up", "warm", "draft", "sector",
                  "gta_area", "primary_variant", "date_found", "date_applied",
                  "src", "freshness", "url"]
    cols = [c for c in (_full_cols if _show_all_cols else _compact_cols)
            if c in view.columns]
    _col_config = {
        "company": st.column_config.TextColumn("Company", width="medium"),
        "title": st.column_config.TextColumn("Title", width="large"),
        "status": st.column_config.TextColumn("Status", width="small"),
        "url": st.column_config.LinkColumn("Link", width="small"),
        "fit_score_numeric": st.column_config.NumberColumn("Fit", width="small"),
        "tier": st.column_config.NumberColumn("T", width="small"),
        "primary_variant": st.column_config.TextColumn("Variant", width="small"),
        "urgency": st.column_config.TextColumn("Urg", width="small"),
        "draft": st.column_config.TextColumn("Draft", width="small"),
        "follow_up": st.column_config.TextColumn("Follow-up", width="medium"),
        "warm": st.column_config.TextColumn("Warm", width="small"),
        "src": st.column_config.TextColumn("Src", width="small"),
        "freshness": st.column_config.TextColumn("Age", width="small"),
        "gta_area": st.column_config.TextColumn("Area", width="small"),
        "date_found": st.column_config.TextColumn("Found", width="small"),
        "date_applied": st.column_config.TextColumn("Applied", width="small"),
    }
    # Carry "id" (hidden via column_order) so a row click maps back to the
    # job. The table is now the SELECTOR for the Inspect/edit panel below —
    # click a row → its details / fit / JD-link / actions render there
    # (replaces the old "pick from a dropdown" step).
    _df_cols = cols + (["id"] if "id" in view.columns and "id" not in cols else [])
    _sorted_view = (
        view[_df_cols].sort_values(["tier", "fit_score_numeric"],
                                   ascending=[True, False])
        if "fit_score_numeric" in cols else view[_df_cols]
    ).reset_index(drop=True)
    _kb_table_event = st.dataframe(
        _sorted_view,
        hide_index=True, width='stretch', height=540,
        column_config=_col_config,
        column_order=cols,                 # hides the carried "id"
        on_select="rerun",
        selection_mode="single-row",
        key="kanban_table_select",
    )
    # Row click → inspector selection. Persist the selected ID (not the
    # position) and only update on a GENUINE position change, so a
    # button-driven rerun that reshuffles/filters the table can't silently
    # hijack the inspector to a neighbouring row.
    _kb_sel_rows = (
        _kb_table_event.selection.rows
        if getattr(_kb_table_event, "selection", None) else []
    )
    if _kb_sel_rows:
        _kb_pos = _kb_sel_rows[0]
        if (0 <= _kb_pos < len(_sorted_view)
                and _kb_pos != st.session_state.get("_kb_last_sel_pos")):
            st.session_state["_kb_sel_id"] = str(
                _sorted_view.iloc[_kb_pos]["id"])
            st.session_state["_kb_last_sel_pos"] = _kb_pos

    # ── Bulk clear (hand-pick) ───────────────────────────────────────────
    # "Clear old roles, commit to new ones": tick the rows you're done with
    # and archive them in one atomic write. Archive (not delete) is reversible
    # and keeps the URL block so a cleared role won't re-promote on the next
    # scan. Operates on the CURRENTLY FILTERED view, so filter first to narrow
    # the candidate set (e.g. Status=Found) then pick within it.
    with st.expander("🧹 Bulk clear roles (archive selected)", expanded=False):
        if not len(view):
            st.caption("No roles in the current view to clear.")
        else:
            st.caption(
                f"Tick roles to archive, then confirm. Archiving hides them "
                f"from the active Kanban / Review Queue / Today, and blocks "
                f"re-promotion on future scans — but is reversible per-row via "
                f"Inspect → ↩ Restore. Acting on the {len(view)} role(s) "
                f"currently shown" + (" (filtered)." if _filter_active else ".")
            )
            _bulk_rows = [
                {
                    "_pick": False,
                    "id": _bid,
                    "company": _label_co,
                    "title": _label_ti,
                    "status": _label_st,
                }
                for _bid, _label_co, _label_ti, _label_st in zip(
                    view["id"].tolist(),
                    view["company"].tolist() if "company" in view.columns else [""] * len(view),
                    view["title"].tolist() if "title" in view.columns else [""] * len(view),
                    view["status"].tolist() if "status" in view.columns else [""] * len(view),
                )
            ]
            _bulk_df = pd.DataFrame(_bulk_rows)
            _edited = st.data_editor(
                _bulk_df,
                hide_index=True,
                width='stretch',
                height=min(420, 80 + 36 * len(_bulk_rows)),
                column_config={
                    "_pick": st.column_config.CheckboxColumn("Clear?", width="small"),
                    "id": st.column_config.TextColumn("ID", width="small", disabled=True),
                    "company": st.column_config.TextColumn("Company", disabled=True),
                    "title": st.column_config.TextColumn("Title", disabled=True),
                    "status": st.column_config.TextColumn("Status", width="small", disabled=True),
                },
                key="kanban_bulk_clear_editor",
            )
            _picked_ids = _edited.loc[_edited["_pick"] == True, "id"].tolist()  # noqa: E712
            _bc1, _bc2 = st.columns([1, 3])
            with _bc1:
                _bulk_go = st.button(
                    f"🧹 Archive {len(_picked_ids)} selected",
                    type="primary",
                    width='stretch',
                    disabled=not _picked_ids,
                    key="kanban_bulk_clear_go",
                )
            with _bc2:
                if _picked_ids:
                    st.caption(
                        "Reversible — restore any row later from Inspect → ↩ Restore."
                    )
                else:
                    st.caption("Tick at least one role to enable.")
            if _bulk_go and _picked_ids:
                from safe_json import mutate_json as _mj_bulk  # noqa: WPS433
                from automation import tracker_ops as _tops_bulk  # noqa: WPS433
                try:
                    _mj_bulk(
                        TRACKER,
                        lambda t: _tops_bulk.archive_many(
                            t, _picked_ids, "manual_bulk_kanban"),
                        default={"jobs": [], "meta": {}},
                    )
                    load_tracker.clear()
                    st.toast(f"🧹 Archived {len(_picked_ids)} role(s)", icon="🚫")
                except Exception as _bexc:  # noqa: BLE001
                    st.error(f"Bulk archive failed: {_bexc}")
                st.rerun()

    st.markdown("---")
    st.subheader("Inspect / edit")
    if len(view):
        # Selection now comes from CLICKING a row in the table above (see the
        # _kb_sel_id derivation right after st.dataframe) — the table is the
        # selector, no dropdown. Reads the stable id from session_state, so it
        # survives button-reruns and filter changes. Reads the job from the
        # FULL `jobs` list (not the filtered `view`), so a row you just acted
        # on (e.g. rejected out of a Status filter) still shows its result.
        sel_id = st.session_state.get("_kb_sel_id")
        job = next((j for j in jobs if j["id"] == sel_id), None) if sel_id else None
        if job is None:
            st.info(
                "👆 Click any row in the table above to see its fit score, "
                "JD link, and actions (✨ Tailor · ✅ Mark Applied · "
                "❌ Won't apply · 🚫 Archive) here."
            )
        if job:
            c1, c2 = st.columns(2)
            with c1:
                # ── Header with tier badge ──────────────────────────────────
                _job_tier = int(job.get("tier") or 4)
                _tier_color = TIER_COLORS.get(_job_tier, _C_GRAY)
                _fit_num = int(job.get("fit_score_numeric") or 0)
                _score_color = "#10b981" if _fit_num >= 8 else "#f59e0b" if _fit_num >= 6 else "#ef4444" if _fit_num > 0 else "#6b7280"
                st.markdown(
                    f"<div style='margin-bottom:6px'>"
                    f"<span style='font-size:1.1em;font-weight:700'>{job['company']} — {job['title']}</span>"
                    f"<span style='margin-left:8px;padding:2px 8px;border-radius:10px;"
                    f"background:{_tier_color}22;color:{_tier_color};"
                    f"font-size:0.78em;font-weight:700'>T{_job_tier}</span>"
                    f"<span style='margin-left:4px;padding:2px 8px;border-radius:10px;"
                    f"background:{_score_color}22;color:{_score_color};"
                    f"font-size:0.78em;font-weight:700'>{_fit_num}/10</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                variants = job.get("resume_variants") or ([job["primary_variant"]]
                    if job.get("primary_variant") else [])
                variant_str = " · ".join(variants) if variants else "—"
                st.caption(
                    f"{job.get('sector')} · {job.get('status','?')} · "
                    f"fit {job.get('fit_score')} · 📄 {variant_str}"
                )
                # Posting age — how long the role has been live (posted_date),
                # alongside when we found it. Falls back to found-only when the
                # board never exposed a posting date.
                _fb = freshness_badge(job.get("posted_date"), job.get("date_found"))
                if _fb and _fb != "—":
                    st.caption(f"🗓 {_fb}")
                # Inline tailor + apply action strip — same widget that
                # lives in Today's queue. 3 buttons: Open posting · Tailor
                # · Mark applied. Tailor spawns jd_tailor in background;
                # the drawer (rendered at end of page) surfaces the doc
                # and a one-click Apply when ready.
                # ✨ Tailor resume (in the strip above) is now the single
                # entry point — it spawns the agentic resume_agent and the
                # tailor drawer (rendered at the end of this page) surfaces the
                # polished .docx + cover + interview-brief downloads. No
                # separate button here.
                render_tailor_action_row(
                    job, key_prefix="kanban_inspect", tracker_data=tr,
                    tracker_path=TRACKER,
                )
                # Cost/quality tier for ALL resume generation (session-wide).
                _tier_labels = {
                    "balanced": "⚖️ Balanced · Opus draft + Sonnet check (~$0.60)",
                    "max":      "💎 Max · Opus everything (~$1.30)",
                    "cheap":    "💰 Cheap · Sonnet (~$0.25)",
                    "draft":    "⚡ Draft · Sonnet, no validity check (~$0.10)",
                }
                _cur = st.session_state.get("_resume_tier", "balanced")
                st.session_state["_resume_tier"] = st.selectbox(
                    "Resume cost/quality", list(_tier_labels),
                    index=(list(_tier_labels).index(_cur)
                           if _cur in _tier_labels else 0),
                    format_func=lambda k: _tier_labels[k],
                    key="_resume_tier_select",
                    help="Per-resume API cost when you hit ✨ Tailor resume. "
                         "Balanced keeps the Opus-quality draft but runs the "
                         "validity check on cheaper Sonnet. Draft skips the "
                         "validity check entirely.")

                _nxt = job.get("next_action") or ""
                if _nxt:
                    st.info(f"**Next:** {_nxt}", icon="🎯")
                _fit_notes = job.get("fit_notes", "")
                if _fit_notes:
                    with st.expander("Fit notes", expanded=False):
                        st.write(_fit_notes)
                # ── Outreach / activity timeline ───────────────────────────
                _olog = job.get("outreach_log") or []
                _fsched = job.get("followup_schedule") or {}
                _date_app = parse_date(job.get("date_applied"))
                _date_found = parse_date(job.get("date_found"))
                _timeline_events = []
                _date_posted = parse_date(job.get("posted_date"))
                if _date_posted:
                    _timeline_events.append((_date_posted, "📅", "Posted"))
                if _date_found:
                    _timeline_events.append((_date_found, "🔍", "Found"))
                if _date_app:
                    _timeline_events.append((_date_app, "📤", "Applied"))
                for _oe in _olog:
                    _ed = parse_date(_oe.get("date"))
                    if _ed:
                        _ekind = _oe.get("kind") or _oe.get("channel") or "message"
                        _timeline_events.append((_ed, "📨", f"Outreach: {_ekind}"))
                _next_due = parse_date(_fsched.get("next_due"))
                if _next_due:
                    _overdue = _next_due < date.today()
                    _fu_icon = "🔴" if _overdue else "🔔"
                    _timeline_events.append((_next_due, _fu_icon,
                        f"Follow-up {'OVERDUE' if _overdue else 'due'}"))
                if _timeline_events:
                    _timeline_events.sort(key=lambda x: x[0])
                    with st.expander("🕐 Activity timeline", expanded=bool(_olog or _date_app)):
                        for _td, _ti, _tl in _timeline_events:
                            _is_future = _td > date.today()
                            _style = "opacity:0.55;" if _is_future else ""
                            st.markdown(
                                f"<div style='display:flex;gap:8px;padding:4px 0;{_style}'>"
                                f"<span style='font-size:1em'>{_ti}</span>"
                                f"<span style='font-size:0.82em;opacity:0.7;min-width:80px'>"
                                f"{_td.strftime('%b %d')}</span>"
                                f"<span style='font-size:0.88em'>{_tl}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                # CRM cross-reference — "you have N contacts at this company"
                _crm_hits = crm_contacts_at_company(crm, job.get("company", ""))
                if _crm_hits:
                    with st.container(border=True):
                        st.markdown(
                            f"⚡ **{len(_crm_hits)} CRM contact(s) at {job['company']}** "
                            "— warm-intro pathway before cold apply:"
                        )
                        for c in _crm_hits[:5]:
                            if c["_kind"] == "recruiter":
                                st.markdown(
                                    f"- 🎯 **{c.get('firm', '?')}** "
                                    f"({c.get('firm_type', '')}) · "
                                    f"priority={c.get('priority', '?')} · "
                                    f"last-touch {c.get('last_touchpoint', 'never')}"
                                )
                            else:
                                st.markdown(
                                    f"- 🎓 **{c.get('name', '?')}** at "
                                    f"{c.get('current_firm', '?')} · "
                                    f"{c.get('relationship', '')}"
                                )
                        if len(_crm_hits) > 5:
                            st.caption(f"…and {len(_crm_hits) - 5} more — see CRM page.")
                        st.caption("Jump to 🤝 Recruiter CRM to draft an outreach message.")

                # (The old standalone "Tailor resume + cover" button lived
                # here — removed in the resume-pipeline unification. The
                # ✨ Tailor resume button in the action strip above is the
                # single entry point; its drawer surfaces the .docx + cover +
                # interview-brief downloads.)
            with c2:
                with st.form(f"edit_{sel_id}"):
                    _kb_meta = tr.get("meta") or {}
                    _kb_enum = _kb_meta.get("status_enum", ["Watch", "Found", "Applied"])
                    _kb_status = job.get("status")
                    _kb_idx = _kb_enum.index(_kb_status) if _kb_status in _kb_enum else 0
                    new_status = st.selectbox("Status", options=_kb_enum, index=_kb_idx)
                    new_urgency = st.selectbox("Urgency", ["High", "Medium", "Low"],
                                                index=["High", "Medium", "Low"].index(job.get("urgency", "Medium")))
                    new_date_applied = st.date_input("Date applied", parse_date(job.get("date_applied")) or None,
                                                      format="YYYY-MM-DD") if job.get("date_applied") else st.date_input(
                        "Date applied (blank = not applied yet)", value=None, format="YYYY-MM-DD")
                    new_notes = st.text_area("Notes", job.get("notes", ""))
                    submitted = st.form_submit_button("Save")
                    if submitted:
                        # Race fix: route through mutate_json (single exclusive
                        # lock) so this serializes against auto_promote and the
                        # Review-Queue writer instead of clobbering the whole
                        # page-load `tr` dict (same fix as _rq_apply_action).
                        from safe_json import mutate_json as _mj  # noqa: WPS433

                        def _mut_save(t):
                            for j in t.get("jobs", []):
                                if j["id"] == sel_id:
                                    j["status"] = new_status
                                    j["urgency"] = new_urgency
                                    # Seed follow-up on first Applied date
                                    if new_date_applied and not parse_date(j.get("date_applied")):
                                        seed_followup(j, new_date_applied)
                                    elif new_date_applied:
                                        j["date_applied"] = new_date_applied.isoformat()
                                    j["notes"] = new_notes
                                    break
                            return t

                        _mj(TRACKER, _mut_save, default={"jobs": [], "meta": {}})
                        load_tracker.clear()
                        st.success("Saved.")
                        st.rerun()

                # "Mark Applied" already lives in the action strip at the top
                # of this inspector (Open posting · Tailor · ✅ Applied) — no
                # duplicate button here. The bottom groups the "stop pursuing"
                # actions under one header instead of scattering them, and
                # drops the internal (id=…) that was leaking into labels.
                st.markdown("**Not pursuing this role?**")
                # Phase 3D — Archive / Restore (toggles on current state).
                # Routes through tracker_ops.archive + mutate_json so the
                # write serializes against auto_promote.
                _sel_job = next((j for j in tr["jobs"]
                                 if j.get("id") == sel_id), None)
                _is_archived = bool((_sel_job or {}).get("archived", False))
                if not _is_archived:
                    if st.button("🚫 Archive", width='stretch',
                                 key=f"_kb_archive_{sel_id}",
                                 help="Hide from Review Queue + "
                                      "Today's brief + Kanban active "
                                      "view. URL still blocks "
                                      "re-promotion."):
                        from safe_json import mutate_json as _mj_kb  # noqa: WPS433
                        from automation import tracker_ops as _tops_kb  # noqa: WPS433
                        try:
                            _mj_kb(TRACKER,
                                    lambda t: _tops_kb.archive(
                                        t, sel_id, "manual_kanban"),
                                    default={"jobs": [], "meta": {}})
                            load_tracker.clear()
                            st.toast("📁 Archived", icon="🚫")
                        except Exception as _exc:  # noqa: BLE001
                            st.error(f"Archive failed: {_exc}")
                        st.rerun()
                else:
                    # Phase 5 — context-aware Restore. If this row was
                    # archived as part of a still-active mute, surface
                    # "(still muted ⚠)" and gate the click on an inline
                    # confirm that lets the user lift the mute too.
                    _kb_ar_reason = (_sel_job or {}).get(
                        "archive_reason", "",
                    ) or ""
                    _kb_live_mute: dict | None = None
                    _kb_parsed = pipeline_state.parse_archive_reason(
                        _kb_ar_reason,
                    )
                    if _kb_parsed:
                        try:
                            from automation import suppressions as _kb_supp_mod  # noqa: WPS433
                            _kb_supp_state = _kb_supp_mod.load_active()
                            _kb_sc, _kb_nm = _kb_parsed
                            try:
                                if _kb_sc == "sector":
                                    from automation import sectors as _kb_sec  # noqa: WPS433
                                    _kb_ck_raw = _kb_sec.canonical(_kb_nm)
                                    _kb_ck = _kb_ck_raw.lower() if _kb_ck_raw \
                                        else _kb_nm.lower()
                                else:
                                    from automation import brand_aliases as _kb_ba  # noqa: WPS433
                                    _kb_ck = _kb_ba.canonical_brand(_kb_nm).lower()
                            except Exception:  # noqa: BLE001
                                _kb_ck = _kb_nm.lower()
                            _kb_scope_key = "sectors" if _kb_sc == "sector" \
                                else "companies"
                            for _kb_entry in _kb_supp_state.get(
                                _kb_scope_key, [],
                            ) or []:
                                if _kb_entry.get("canonical_key") == _kb_ck:
                                    _kb_live_mute = _kb_entry
                                    break
                        except Exception:  # noqa: BLE001
                            _kb_live_mute = None

                    _kb_btn_label = (
                        "↩ Restore (still muted ⚠)"
                        if _kb_live_mute
                        else "↩ Restore"
                    )
                    if st.button(
                        _kb_btn_label,
                        width='stretch',
                        key=f"_kb_restore_{sel_id}",
                        help="Bring this row back into the "
                             "active Kanban + Review Queue.",
                    ):
                        if _kb_live_mute:
                            st.session_state["_kb_restore_open"] = sel_id
                            st.rerun()
                        else:
                            from safe_json import mutate_json as _mj_kb  # noqa: WPS433
                            from automation import tracker_ops as _tops_kb  # noqa: WPS433
                            try:
                                _mj_kb(TRACKER,
                                        lambda t: _tops_kb.restore(t, sel_id),
                                        default={"jobs": [], "meta": {}})
                                load_tracker.clear()
                                st.toast("↩ Restored", icon="✅")
                            except Exception as _exc:  # noqa: BLE001
                                st.error(f"Restore failed: {_exc}")
                            st.rerun()

                    if (st.session_state.get("_kb_restore_open") == sel_id
                            and _kb_live_mute and _kb_parsed):
                        from datetime import date as _kb_date  # noqa: WPS433
                        _kb_today = _kb_date.today()
                        _kb_cf_scope, _kb_cf_name = _kb_parsed
                        _kb_cf_until_lbl = pipeline_state.format_until_label(
                            _kb_live_mute.get("until"), _kb_today,
                        )
                        with st.container(border=True):
                            st.caption(
                                f"This row was archived as part of muting "
                                f"{_kb_cf_scope} {_kb_cf_name!r}, which is "
                                f"still active ({_kb_cf_until_lbl}). Restore "
                                f"alone will bring this row back; future "
                                f"scans will still skip {_kb_cf_scope} "
                                f"{_kb_cf_name!r}."
                            )
                            _kb_cf_lift = st.checkbox(
                                f"Also lift the {_kb_cf_scope} mute on "
                                f"'{_kb_cf_name}'",
                                value=False,
                                key=f"_kb_restore_lift_{sel_id}",
                            )
                            _kb_cf_b1, _kb_cf_b2 = st.columns(2)
                            _kb_cf_go = _kb_cf_b1.button(
                                "↩ Restore", type="primary",
                                width='stretch',
                                key=f"_kb_restore_go_{sel_id}",
                            )
                            _kb_cf_cancel = _kb_cf_b2.button(
                                "Cancel", width='stretch',
                                key=f"_kb_restore_cancel_{sel_id}",
                            )
                            if _kb_cf_go:
                                from safe_json import mutate_json as _mj_kb  # noqa: WPS433
                                from automation import tracker_ops as _tops_kb  # noqa: WPS433
                                _kb_restore_ok = False
                                try:
                                    _mj_kb(TRACKER,
                                            lambda t: _tops_kb.restore(t, sel_id),
                                            default={"jobs": [], "meta": {}})
                                    load_tracker.clear()
                                    _kb_restore_ok = True
                                except Exception as _exc:  # noqa: BLE001
                                    st.error(f"Restore failed: {_exc}")
                                if _kb_restore_ok and _kb_cf_lift:
                                    try:
                                        _kb_supp_mod.lift(
                                            _kb_cf_scope, _kb_cf_name,
                                        )
                                        st.toast(
                                            f"↩ Restored & lifted "
                                            f"{_kb_cf_scope} mute on "
                                            f"{_kb_cf_name!r}", icon="🔓",
                                        )
                                    except Exception as _exc:  # noqa: BLE001
                                        st.warning(
                                            f"Restored, but lift failed: "
                                            f"{_exc}", icon="⚠️",
                                        )
                                elif _kb_restore_ok:
                                    st.toast(
                                        "↩ Restored (mute remains active)",
                                        icon="✅",
                                    )
                                st.session_state.pop(
                                    "_kb_restore_open", None,
                                )
                                st.rerun()
                            if _kb_cf_cancel:
                                st.session_state.pop(
                                    "_kb_restore_open", None,
                                )
                                st.rerun()

                # ❌ Won't apply (Reject) — the "I've decided NOT to apply"
                # action, alternative to ✅ Mark Applied. Sets status=Rejected
                # (terminal → drops out of apply/review/follow-up queues, moves
                # to the ❌ Rejected column) + rejection_date + a categorized
                # reason. Reversible via the Status dropdown above. Distinct
                # from 🚫 Archive, which only hides without recording a verdict.
                _kb_reject_reasons = [
                    "Not a fit", "Location", "Comp too low", "Seniority mismatch",
                    "Already applied elsewhere", "Company", "Other",
                ]
                # (Sits under the "Not pursuing this role?" header above,
                # next to 🚫 Archive — the two "stop pursuing" actions grouped.)
                _rj1, _rj2 = st.columns([2, 1])
                with _rj1:
                    _kb_reject_reason = st.selectbox(
                        "Rejection reason", _kb_reject_reasons,
                        key=f"_kb_reject_reason_{sel_id}",
                        label_visibility="collapsed",
                    )
                with _rj2:
                    _kb_do_reject = st.button(
                        "❌ Won't apply",
                        width='stretch',
                        key=f"_kb_reject_{sel_id}",
                        disabled=(job.get("status") == "Rejected"),
                        help="Mark Rejected with this reason. Drops it from "
                             "your apply / Review Queue / follow-up queues and "
                             "moves it to the ❌ Rejected column. Reversible "
                             "via the Status dropdown above.",
                    )
                if job.get("status") == "Rejected":
                    st.caption(
                        f"❌ Rejected"
                        + (f" — {job.get('rejection_reason')}"
                           if job.get("rejection_reason") else "")
                        + (f" ({job.get('rejection_date')})"
                           if job.get("rejection_date") else "")
                    )
                if _kb_do_reject:
                    # Inline the mutation (mirrors ✅ Mark Applied) instead of
                    # calling tracker_ops.reject: a long-running Streamlit
                    # process can hold a stale tracker_ops import from before
                    # reject() existed, and reloading submodules mid-session is
                    # unreliable — that AttributeError, combined with an
                    # unconditional st.rerun() below, silently wiped the error
                    # and looked like "nothing happened". Same fields
                    # tracker_ops.reject writes; rerun ONLY on success so a
                    # genuine failure stays on screen.
                    from safe_json import mutate_json as _mj_rej  # noqa: WPS433
                    _rej_stamp = date.today().isoformat()

                    def _mut_reject(t):
                        for j in t.get("jobs", []):
                            if j["id"] == sel_id:
                                j["status"] = "Rejected"
                                j["rejection_reason"] = _kb_reject_reason
                                j["rejection_date"] = _rej_stamp
                                j["status_changed_by"] = "manual_reject"
                                j["status_changed_on"] = _rej_stamp
                                break
                        return t

                    try:
                        _mj_rej(TRACKER, _mut_reject,
                                default={"jobs": [], "meta": {}})
                    except Exception as _exc:  # noqa: BLE001
                        st.error(f"Reject failed: {_exc}")
                    else:
                        load_tracker.clear()
                        st.toast(f"❌ Rejected — {_kb_reject_reason}", icon="❌")
                        st.rerun()

    # Tailor drawer — shared with Dashboard. Opens whenever ✨ Tailor or
    # 📄 View tailor was clicked anywhere on this page.
    render_tailor_drawer(jobs, tr, TRACKER)


# ============================================================================
# 🤝 RECRUITER CRM
# ============================================================================
elif page == "🤝 Recruiter CRM":
    st.title("🤝 Recruiter + Warm-intro CRM")
    if not crm:
        st.warning("No recruiter_crm.json found.")
        st.stop()

    # ---------- Weekly outreach digest ----------
    digest = outreach_digest(crm)
    weekly_target = (crm.get("meta", {}).get("weekly_target", {}).get("new_outreach")) or 10
    weekly_sent = digest["weekly_sent"]
    pct = int(min(100, weekly_sent / weekly_target * 100)) if weekly_target else 0

    dc1, dc2, dc3, dc4, dc5 = st.columns(5)
    dc1.metric("This week sent", f"{weekly_sent} / {weekly_target}",
               delta=weekly_sent - weekly_target)
    dc2.metric("Never contacted", len(digest["never_contacted"]))
    dc3.metric("Active (≤14d)", len(digest["active"]))
    dc4.metric("Stale (15–35d)", len(digest["stale"]), delta_color="inverse")
    dc5.metric("Cold (>35d)", len(digest["cold"]), delta_color="inverse")
    st.progress(pct / 100.0, text=f"Weekly outreach progress: {weekly_sent}/{weekly_target} "
                                  f"({pct}%)")

    with st.expander(f"📬 Outreach digest — prioritized nudges "
                     f"({len(digest['never_contacted']) + len(digest['stale']) + len(digest['cold'])} pending)"):
        st.caption(
            "Priority order: 🆕 never-contacted (High priority first) → "
            "⏰ stale (15–35d, reply-chase) → 🧊 cold (>35d, reactivate or retire). "
            "Use templates below to draft in-voice nudges."
        )
        tn, ts, tc = st.tabs([
            f"🆕 Never ({len(digest['never_contacted'])})",
            f"⏰ Stale ({len(digest['stale'])})",
            f"🧊 Cold ({len(digest['cold'])})",
        ])

        def _render_digest_rows(items, tab, mode):
            if not items:
                tab.caption("Nothing here. 🎉")
                return
            rows = []
            for item in items:
                if isinstance(item, tuple):
                    days, c = item
                else:
                    days, c = None, item
                rows.append({
                    "id": c.get("id"),
                    "kind": c.get("_kind", "?"),
                    "firm_or_name": c.get("firm") or c.get("name", ""),
                    "priority": c.get("priority", ""),
                    "status": c.get("status", ""),
                    "last_touch": c.get("last_touchpoint") or "(never)",
                    "days_since": days if days is not None else "—",
                    "next_action": (c.get("next_action") or "")[:80],
                })
            tab.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
            # Draft a message
            pick = tab.selectbox("Contact to draft for", [r["id"] for r in rows],
                                  key=f"dig_pick_{mode}")
            contact = next(({**c, "_kind": c.get("_kind", "?")} for item in items
                           for c in ([item[1]] if isinstance(item, tuple) else [item])
                           if c.get("id") == pick), None)
            if contact:
                templates = crm.get("outreach_message_templates", {})
                tpl_key = tab.selectbox(
                    "Template",
                    list(templates.keys()) if templates else ["(none)"],
                    key=f"dig_tpl_{mode}",
                )
                body = templates.get(tpl_key, "")
                rendered = render_template(body, contact)
                tab.text_area("Drafted message (edit before sending)", rendered,
                              height=200, key=f"dig_msg_{mode}")
                if tab.button(f"📝 Log as sent today",
                              key=f"dig_log_{mode}", width='stretch'):
                    # Update the contact's last_touchpoint + append to structured log
                    for r in crm.get("recruiters", []):
                        if r["id"] == pick:
                            r["last_touchpoint"] = date.today().isoformat()
                            if r.get("status") == "Not_Contacted":
                                r["status"] = "Outreach_Sent"
                    for a in crm.get("alumni_warm_intros", []):
                        if a["id"] == pick:
                            a["last_touchpoint"] = date.today().isoformat()
                            if a.get("status") == "Not_Contacted":
                                a["status"] = "Outreach_Sent"
                    crm.setdefault("outreach_log", []).append({
                        "date": date.today().isoformat(),
                        "contact_id": pick,
                        "template": tpl_key,
                        "channel": "linkedin",
                    })
                    save_crm(crm)
                    st.success(f"Logged outreach to {pick}.")
                    st.rerun()

        _render_digest_rows(digest["never_contacted"], tn, "never")
        _render_digest_rows(digest["stale"], ts, "stale")
        _render_digest_rows(digest["cold"], tc, "cold")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["Recruiters", "Alumni warm-intros", "Templates"])
    with tab1:
        recs = crm.get("recruiters", [])
        rdf = pd.DataFrame(recs)
        if not rdf.empty:
            cols = [c for c in ["id", "firm", "firm_type", "location", "priority",
                                "status", "last_touchpoint", "next_action"] if c in rdf.columns]
            st.dataframe(rdf[cols], hide_index=True, width='stretch')
            # ── Quick-log row: mark any recruiter as contacted today ─────────
            with st.expander("⚡ Quick-log: mark contacted today", expanded=False):
                _quick_ids = [r["id"] for r in recs
                               if r.get("status") in ("Not_Contacted", "Outreach_Sent", "Active")]
                if _quick_ids:
                    _qlog_pick = st.selectbox("Recruiter", _quick_ids, key="crm_qlog_pick")
                    _qlog_note = st.text_input("Note (optional)", key="crm_qlog_note",
                                               placeholder="LinkedIn DM / email / call …")
                    if st.button("✅ Log as contacted today", key="crm_qlog_btn", type="primary"):
                        for _rx in crm.get("recruiters", []):
                            if _rx["id"] == _qlog_pick:
                                _rx["last_touchpoint"] = date.today().isoformat()
                                if _rx.get("status") == "Not_Contacted":
                                    _rx["status"] = "Outreach_Sent"
                                break
                        crm.setdefault("outreach_log", []).append({
                            "date": date.today().isoformat(),
                            "contact_id": _qlog_pick,
                            "note": _qlog_note,
                            "channel": "manual",
                        })
                        save_crm(crm)
                        st.success(f"Logged contact with {_qlog_pick} today.")
                        st.rerun()
                else:
                    st.caption("All recruiters already contacted. 🎉")
            sel = st.selectbox("Pick firm id to inspect/edit", rdf["id"].tolist())
            r = next((x for x in recs if x["id"] == sel), None)
            if r:
                _crm_sc = CRM_STATUS_COLORS.get(r.get("status", ""), _C_GRAY)
                _crm_pc = PRIORITY_COLORS.get(r.get("priority", ""), _C_GRAY)
                st.markdown(
                    f"<div style='margin:6px 0'>"
                    f"<span style='font-size:1.1em;font-weight:700'>{r['firm']}</span>"
                    f"<span style='margin-left:8px;padding:2px 10px;border-radius:10px;"
                    f"background:{_crm_sc}22;color:{_crm_sc};font-size:0.8em;font-weight:600'>"
                    f"{r.get('status','?')}</span>"
                    f"<span style='margin-left:4px;padding:2px 10px;border-radius:10px;"
                    f"background:{_crm_pc}22;color:{_crm_pc};font-size:0.8em;font-weight:600'>"
                    f"{r.get('priority','?')}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{r.get('firm_type')} · {r.get('location')} · Last touch: {r.get('last_touchpoint','never')}")
                if r.get("notes"):
                    st.write(r.get("notes", ""))
                st.markdown(f"**Coverage:** {r.get('coverage','')}")
                st.markdown(f"**Next action:** {r.get('next_action','')}")
                with st.form(f"rec_{sel}"):
                    _rec_enum = crm.get("meta", {}).get("status_enum",
                                                          ["Not_Contacted", "Outreach_Sent"])
                    _rec_status = r.get("status")
                    _rec_idx = _rec_enum.index(_rec_status) if _rec_status in _rec_enum else 0
                    new_status = st.selectbox("Status", _rec_enum, index=_rec_idx)
                    new_last = st.date_input("Last touchpoint", parse_date(r.get("last_touchpoint")))
                    new_notes = st.text_area("Notes", r.get("notes", ""))
                    if st.form_submit_button("Save"):
                        for x in crm["recruiters"]:
                            if x["id"] == sel:
                                x["status"] = new_status
                                x["last_touchpoint"] = new_last.isoformat() if new_last else None
                                x["notes"] = new_notes
                                break
                        save_crm(crm)
                        st.success("Saved.")
                        st.rerun()

    with tab2:
        alumni = crm.get("alumni_warm_intros", [])
        st.dataframe(pd.DataFrame(alumni), hide_index=True, width='stretch')

    with tab3:
        templates = crm.get("outreach_message_templates", {})
        for name, body in templates.items():
            with st.expander(name):
                st.code(body, language="text")


# ============================================================================
# 📅 WEEKLY PLAN
# ============================================================================
elif page == "📅 Weekly Plan":
    st.title("📅 Weekly Plan")
    wp = ROOT / "docs" / "this_week.md"
    cp = ROOT / "docs" / "operating_cadence.md"
    t1, t2, t3 = st.tabs(["This week", "Operating cadence", "Weekly report"])
    with t1:
        st.markdown(wp.read_text(encoding="utf-8") if wp.exists() else "_(no this_week.md)_")
    with t2:
        st.markdown(cp.read_text(encoding="utf-8") if cp.exists() else "_(no operating_cadence.md)_")
    with t3:
        reports = sorted(OUT_DIR.glob("weekly_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports:
            which = st.selectbox("Report", [p.name for p in reports])
            st.markdown((OUT_DIR / which).read_text(encoding="utf-8"))
        else:
            st.info("No weekly reports yet.")


# ============================================================================
# 📝 CONTENT & MEMORY
# ============================================================================
elif page == "📝 Content & Memory":
    st.title("📝 Content & Memory")

    t_crit, t_repo, t_linkedin, t_engagement, t_campaign = st.tabs([
        "🎯 Targeting Criteria",
        "📚 Master Repository",
        "📅 LinkedIn Calendar",
        "📋 Engagement Log",
        "🧠 Campaign Memory",
    ])

    # ── Tab 1: Targeting Criteria ────────────────────────────────────────────
    with t_crit:
        st.markdown("### 🎯 Role Targeting Criteria")
        st.caption("Live rules governing which roles to pursue, how to angle the application, and where to direct outreach energy.")

        # ── Key identity tags — the 6 phrases that open doors ────────────────
        _tags = [
            ("ALM / IRRBB", "#3b82f6"),
            ("Model Risk & Governance", "#6366f1"),
            ("Balance Sheet Analytics", "#0891b2"),
            ("Stochastic Scenario Engine", "#0284c7"),
            ("Institutional Platform Delivery", "#7c3aed"),
            ("Director / VP level", "#059669"),
        ]
        _tag_html = "".join(
            f"<span style='display:inline-block;padding:4px 12px;margin:3px 4px;"
            f"border-radius:14px;background:{c}20;border:1px solid {c}55;"
            f"color:{c};font-size:0.82em;font-weight:600'>{t}</span>"
            for t, c in _tags
        )
        st.markdown(
            f"<div style='margin:4px 0 12px 0'>{_tag_html}</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        crit_col1, crit_col2 = st.columns([1, 1], gap="large")

        with crit_col1:
            st.caption("Two primary families · four active lanes (Master Repo §7). "
                       "Opportunistic: trading-book market-risk capital, consulting.")
            st.markdown("#### 🔵 PRIMARY Family — Risk & Model Analytics")
            st.markdown(
                "_Co-equal lanes: ALM/IRRBB/Treasury · Model Validation · "
                "Investment & Market Risk._  \n"
                "**Best-fit titles:**  \n"
                "Director — ALM & Balance Sheet Risk  \n"
                "Director — IRRBB Modelling  \n"
                "Senior Manager / Director — Model Risk & Validation  \n"
                "Director — Investment / Market Risk Analytics (VaR/CVaR)  \n"
                "Head of ALM Analytics · Director — Treasury Risk"
            )
            st.markdown(
                "**Evidence stack:**  \n"
                "• Delegated sign-off authority on multi-asset institutional portfolios (Moody's)  \n"
                "• Cash flow projection engine design & delivery (Moody's)  \n"
                "• IRRBB-analogous shock analytics & curve calibration (Moody's)  \n"
                "• VaR/CVaR & portfolio optimization, risk decomposition (Ortec/Moody's)  \n"
                "• LDI, stochastic scenario generators (Ortec) · model governance (Moody's)"
            )
            st.info(
                "**Target employers:** Scotiabank · RBC · BMO · CIBC · TD · National Bank · Equitable Bank  \n"
                "CPP · OTPP · OMERS · HOOPP · PSP · OPTrust · CAAT · IMCO  \n"
                "Manulife · Sun Life · Canada Life · Intact · iA · RGA"
            )

            st.markdown("#### 🟢 PRIMARY Family — Vendor-Platform / Solutions Engineering")
            st.markdown(
                "_Co-equal with Risk & Model Analytics — runs active outbound._  \n"
                "**Best-fit titles:**  \n"
                "Director — Aladdin Solutions Engineering / Client Engagement  \n"
                "Senior Analytics Specialist · Solutions Consultant (Risk Analytics)  \n"
                "Director — Risk Solutions · Pre-Sales / Solutions Engineering  \n"
                "Product Specialist (Risk/ALM platforms) · Director — Client Advisory"
            )
            st.markdown(
                "**Evidence stack:**  \n"
                "• Institutional platform delivery at Moody's (direct parallel to Aladdin, S&P, MSCI)  \n"
                "• Calypso → PFaroe migration leadership  \n"
                "• Client-translation across investment teams and dev  \n"
                "• Agentic-AI workflow design (Claude Code, Cursor)"
            )
            st.info(
                "**Target employers:** BlackRock (Aladdin) · Bloomberg · MSCI · S&P Global  \n"
                "FactSet · Morningstar DBRS · SS&C Algorithmics · Numerix · Prometeia · Clearwater"
            )

        with crit_col2:
            st.markdown("#### 💰 Compensation Targets")
            comp_data = [
                {"Band": "Director / VP — Big 6 Banks", "Base (CAD)": "$195–260K", "Total Comp": "$300–420K"},
                {"Band": "Director — Maple 8 Pension", "Base (CAD)": "$200–310K", "Total Comp": "$320–500K"},
                {"Band": "Director — US/Global AM", "Base (CAD)": "$195–310K", "Total Comp": "$330–550K"},
                {"Band": "Director — Vendor (Bloomberg, MSCI)", "Base (CAD)": "$175–250K", "Total Comp": "$260–400K"},
                {"Band": "Sr. Manager — Insurer / Mid-bank", "Base (CAD)": "$165–230K", "Total Comp": "$220–310K"},
                {"Band": "Sr. Manager — Big 4 Risk Advisory", "Base (CAD)": "$170–230K", "Total Comp": "$220–300K"},
            ]
            st.dataframe(pd.DataFrame(comp_data), hide_index=True, width="stretch")
            st.caption("Floor: $160K base for Sr. Manager. Negotiate off **total comp**, not base alone.")

            st.markdown("#### 🏛️ Active OSFI Regulatory Hooks")
            osfi_hooks = [
                ("E-23 Model Risk Management", "Effective 2027-05-01", "🔴 High"),
                ("B-12 IRRBB Revision", "Q1 2026 consultations", "🔴 High"),
                ("LAR 2026 Liquidity Adequacy", "2026 deadline", "🟡 Medium"),
                ("IFRS 17 (insurers)", "Ongoing", "🟡 Medium"),
                ("IFRS 9 ECL (banks)", "Ongoing", "🟡 Medium"),
            ]
            for hook, timeline, urgency in osfi_hooks:
                st.markdown(f"{urgency} **{hook}** — {timeline}")

            st.markdown("#### 📐 Application Rules")
            st.markdown(
                "✅ **Warm intros over cold** for Director+ roles — ~70% referral-driven in Toronto finance  \n"
                "✅ Open every Big 6 / pension cover letter with a **concrete capability tied to the team**, not generic regulatory framing  \n"
                "✅ Open every vendor cover letter with the **platform practitioner hook** (know your buyers)  \n"
                "✅ Confirm work authorization wording **before first application**  \n"
                "🚫 Do not self-describe as '8+ years' or '10+ years' — **~7 years** is correct  \n"
                "🚫 Do not actively search retired angles (PM, Portfolio Manager, Project Mgr) — ad-hoc only"
            )

            st.markdown("#### 📋 Weekly KPI Targets")
            kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
            try:
                _tracker_kpi = json.loads((ROOT / "data" / "job_tracker_data.json").read_text(encoding="utf-8"))
                _kpis = _tracker_kpi.get("meta", {}).get("weekly_kpi_targets", {})
                kpi_col1.metric("Applications / wk", _kpis.get("tailored_applications", 8))
                kpi_col2.metric("Outreach / wk", _kpis.get("outreach_messages", 10))
                kpi_col3.metric("Coffees / wk", _kpis.get("coffee_chats", 3))
            except Exception:
                kpi_col1.metric("Applications / wk", 8)
                kpi_col2.metric("Outreach / wk", 10)
                kpi_col3.metric("Coffees / wk", 3)

    # ── Tab 2: Master Repository ─────────────────────────────────────────────
    with t_repo:
        _repo_path = ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"
        if not _repo_path.exists():
            st.warning("Master repository not found at `docs/Saber_Ayatollahi_Master_Repository.md`.")
        else:
            _repo_text = _repo_path.read_text(encoding="utf-8")

            # Quick-nav section links
            _sections = [
                ("1. Identity & Contact", "## 1. IDENTITY"),
                ("2. Education", "## 2. EDUCATION"),
                ("3. Experience", "## 3. PROFESSIONAL"),
                ("4. Skills", "## 4. SKILLS"),
                ("5. Bullet Library", "## 5. TAGGED"),
                ("6. STAR Stories", "## 6. STAR"),
                ("7. Positioning", "## 7. TARGET"),
                ("8. Summary Bank", "## 8. SUMMARY"),
                ("9. Logistics", "## 9. LOGISTICS"),
                ("10. Resume Variants", "## 10. RESUME"),
                ("11. Strategy", "## 11. JOB-SEARCH"),
            ]

            st.caption(f"Source: `{_repo_path.relative_to(ROOT)}` · {len(_repo_text.split(chr(10)))} lines · Last modified: {datetime.fromtimestamp(_repo_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}")

            # Section filter
            _sec_names = ["(full document)"] + [s[0] for s in _sections]
            _picked_sec = st.selectbox("Jump to section", _sec_names, key="repo_section_jump")

            if _picked_sec == "(full document)":
                _display_text = _repo_text
            else:
                # Find the matching section header in the text
                _sec_marker = next((s[1] for s in _sections if s[0] == _picked_sec), None)
                if _sec_marker:
                    _sec_idx = _repo_text.find(_sec_marker)
                    # Find next top-level section
                    _next_sec_idx = len(_repo_text)
                    for _, _m in _sections:
                        _ni = _repo_text.find(_m, _sec_idx + 10)
                        if _ni > _sec_idx and _ni < _next_sec_idx:
                            _next_sec_idx = _ni
                    _display_text = _repo_text[_sec_idx:_next_sec_idx]
                else:
                    _display_text = _repo_text

            # Search filter — with ±2 lines of context
            _repo_search = st.text_input("🔍 Search in repository", key="repo_search",
                                          placeholder="e.g. IRRBB, cash flow, sign-off")
            if _repo_search:
                _lines = _display_text.split("\n")
                _q_lo = _repo_search.lower()
                _hit_indices = [i for i, l in enumerate(_lines) if _q_lo in l.lower()]
                if _hit_indices:
                    # Collapse overlapping context windows into contiguous blocks
                    _ctx = 2
                    _blocks = []
                    _cur_start = _cur_end = None
                    for _hi in _hit_indices:
                        _ws = max(0, _hi - _ctx)
                        _we = min(len(_lines) - 1, _hi + _ctx)
                        if _cur_start is None:
                            _cur_start, _cur_end = _ws, _we
                        elif _ws <= _cur_end + 1:
                            _cur_end = max(_cur_end, _we)
                        else:
                            _blocks.append((_cur_start, _cur_end, _hit_indices))
                            _cur_start, _cur_end = _ws, _we
                    if _cur_start is not None:
                        _blocks.append((_cur_start, _cur_end, _hit_indices))
                    st.success(f"Found **{len(_hit_indices)}** match(es) across {len(_blocks)} block(s):")
                    _shown = 0
                    for _bs, _be, _ in _blocks[:8]:
                        _block_lines = []
                        for _li in range(_bs, _be + 1):
                            _ll = _lines[_li]
                            if _q_lo in _ll.lower():
                                _block_lines.append(f"▶ {_ll}")
                            else:
                                _block_lines.append(f"  {_ll}")
                            _shown += 1
                        st.code("\n".join(_block_lines), language="markdown")
                    if len(_blocks) > 8:
                        st.caption(f"… +{len(_blocks)-8} more context blocks")
                else:
                    st.warning(f"No matches for '{_repo_search}' in {'this section' if _picked_sec != '(full document)' else 'the repository'}")

            with st.expander("📄 Repository Content", expanded=(_picked_sec != "(full document)")):
                st.markdown(_display_text)

    # ── Tab 3: LinkedIn Calendar ─────────────────────────────────────────────
    with t_linkedin:
        p = ROOT / "docs" / "linkedin_content_engine.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no linkedin_content_engine.md)_")

    # ── Tab 4: Engagement Log ────────────────────────────────────────────────
    with t_engagement:
        p = ROOT / "docs" / "linkedin_engagement_log.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no linkedin_engagement_log.md)_")

    # ── Tab 5: Campaign Memory ───────────────────────────────────────────────
    with t_campaign:
        candidates = [
            Path.home() / ".claude" / "projects" / "C--Dev-ApplyAgent" / "memory",
            Path.home() / ".claude" / "projects" / "C--Users-ayatollS-Downloads-deep-research-report" / "memory",
        ]
        memdir = next((c for c in candidates if c.exists()), None)
        if memdir:
            st.caption(f"Source: `{memdir}`")
            for f in sorted(memdir.glob("*.md")):
                with st.expander(f.name):
                    st.markdown(f.read_text(encoding="utf-8"))
        else:
            st.info("No Claude memory directory found.")

# ============================================================================
# 📜 SCAN HISTORY — cumulative record of every scan + pipeline run
# ============================================================================
elif page == "📜 Scan History":
    st.title("📜 Scan History")
    st.caption(
        "Cumulative record of every scan the pipeline has produced. Scrape "
        "outputs (`scan_*.json`), scored outputs (`scan_*_scored.json`), and "
        "pipeline runs (`pipeline_*.json`) are all logged here forever."
    )

    # Quick-access: build an audit pack for the most recent scan in one click.
    # Per-scan packs are wired further down on the inspector.
    try:
        import sys as _sys
        _automation_dir = str(ROOT / "automation")
        if _automation_dir not in _sys.path:
            _sys.path.insert(0, _automation_dir)
        from audit_pack import build_audit_pack as _build_pack_latest
        _lc1, _lc2 = st.columns([1, 3])
        with _lc1:
            if st.button("📦 Audit pack — latest scan",
                         key="build_pack_latest_top"):
                with st.spinner("Building multi-sheet xlsx…"):
                    st.session_state["_pack_bytes_latest"] = (
                        _build_pack_latest("latest"))
        with _lc2:
            if st.session_state.get("_pack_bytes_latest"):
                st.download_button(
                    "⬇ Download audit_pack_latest.xlsx",
                    data=st.session_state["_pack_bytes_latest"],
                    file_name="audit_pack_latest.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_pack_latest_top",
                )
    except Exception as _pack_err:
        st.caption(f"Audit pack unavailable: {_pack_err}")

    # -------- Pipeline runs (from PIPELINE_DIR/*.json) --------
    st.markdown("### Pipeline runs")
    pipelines = list_pipelines(limit=200)
    if not pipelines:
        st.info("No pipeline runs yet — launch one from the 🎯 Pipeline page.")
    else:
        pipe_rows = []
        for p in pipelines:
            stages = p.get("stages") or {}
            scrape_s = stages.get("scrape") or {}
            score_s = stages.get("score") or {}
            verdicts = (score_s.get("verdicts") or {})
            # Cast int|"—" to str so pyarrow doesn't trip on mixed types
            # when streamlit serializes this dataframe.
            pipe_rows.append({
                "pipeline_id": p.get("pipeline_id", "?"),
                "started": p.get("started_at", ""),
                "finished": p.get("finished_at", ""),
                "state": p.get("state", "?"),
                "mode": (p.get("args") or {}).get("scrape_mode", "?"),
                "candidates": str(scrape_s.get("candidate_count", "—")),
                "scored": str(score_s.get("scored_count", "—")),
                "apply_now": verdicts.get("apply_now", 0),
                "tailor": verdicts.get("tailor_and_apply", 0),
                "watch": verdicts.get("watch", 0),
                "skip": verdicts.get("skip", 0),
                "scan_file": scrape_s.get("scan_file", ""),
            })
        st.dataframe(pd.DataFrame(pipe_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(pipe_rows), 400))

    st.markdown("---")

    # -------- Scan files (raw scraper outputs) --------
    st.markdown("### Raw scan files")
    scan_files = sorted(
        [f for f in OUT_DIR.glob("scan_*.json") if "_scored" not in f.name],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not scan_files:
        st.info("No scan files yet — run the scraper in 🎯 Pipeline.")
    else:
        scan_rows = []
        for f in scan_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                count = len(data.get("results", []))
                scan_date = data.get("scan_date", "")
                sectors = data.get("sector_counts") or {}
            except Exception:
                count = "?"
                scan_date = ""
                sectors = {}
            scan_rows.append({
                "file": f.name,
                "scan_date": scan_date,
                "candidates": str(count),  # pyarrow-friendly: int|"?"  -> str
                "sectors": len(sectors),
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        st.dataframe(pd.DataFrame(scan_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(scan_rows), 300))

        # Inspector
        pick = st.selectbox("Inspect scan", [r["file"] for r in scan_rows],
                            key="scan_hist_pick")
        if pick:
            try:
                d = json.loads((OUT_DIR / pick).read_text(encoding="utf-8"))
                cols = st.columns(4)
                cols[0].metric("Candidates", len(d.get("results", [])))
                cols[1].metric("Scan date", d.get("scan_date", "—"))
                diag = d.get("diagnostics") or {}
                cols[2].metric("Zero-result cos", len(diag.get("zero_result_companies", [])))
                cols[3].metric("LI throttled", "yes" if diag.get("linkedin_throttled") else "no")
                # Sector distribution
                sc = d.get("sector_counts") or {}
                if sc:
                    st.markdown("**By sector**")
                    st.dataframe(
                        pd.DataFrame(
                            [{"sector": k, "count": v} for k, v in sorted(sc.items(), key=lambda kv: -kv[1])]
                        ),
                        hide_index=True, width='stretch',
                    )
                # Paired scored file if it exists
                scored = OUT_DIR / (Path(pick).stem + "_scored.json")
                if scored.exists():
                    st.success(f"📊 Scored counterpart: `{scored.name}` "
                               f"({round(scored.stat().st_size / 1024, 1)} KB)")
                # Audit-pack download — multi-sheet xlsx covering scrape raw,
                # title/geo drops, gmail, worklist + merges, Stage-1 drops,
                # scored, promote skips. Lets Saber give the agent feedback
                # on which roles got dropped where and why.
                try:
                    import sys as _sys
                    _automation_dir = str(ROOT / "automation")
                    if _automation_dir not in _sys.path:
                        _sys.path.insert(0, _automation_dir)
                    from audit_pack import build_audit_pack as _build_pack
                    _stamp = (d.get("scan_date")
                              or Path(pick).stem.replace("scan_", ""))
                    if st.button("📦 Build audit pack (xlsx)",
                                 key=f"build_pack_scanhist_{pick}"):
                        with st.spinner("Building multi-sheet xlsx…"):
                            st.session_state[f"_pack_bytes_scanhist_{pick}"] = (
                                _build_pack(_stamp))
                    if st.session_state.get(f"_pack_bytes_scanhist_{pick}"):
                        st.download_button(
                            "⬇ Download audit_pack.xlsx",
                            data=st.session_state[f"_pack_bytes_scanhist_{pick}"],
                            file_name=f"audit_pack_{_stamp}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_pack_scanhist_{pick}",
                        )
                except Exception as _pack_err:
                    st.caption(f"Audit pack unavailable: {_pack_err}")
            except Exception as e:
                st.error(f"Could not read {pick}: {e}")

    st.markdown("---")

    # -------- Scored files --------
    st.markdown("### Scored scans")
    scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
    if not scored_files:
        st.info("No scored files yet — run the scorer in 🎯 Pipeline.")
    else:
        scored_rows = []
        for f in scored_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results = data.get("results") or []
                verdicts: dict = {}
                for r in results:
                    v = (r.get("fit") or {}).get("fit_verdict", "?")
                    verdicts[v] = verdicts.get(v, 0) + 1
            except Exception:
                results = []
                verdicts = {}
            scored_rows.append({
                "file": f.name,
                "scored": len(results),
                "apply_now": verdicts.get("apply_now", 0),
                "tailor": verdicts.get("tailor_and_apply", 0),
                "watch": verdicts.get("watch", 0),
                "skip": verdicts.get("skip", 0),
                "error": verdicts.get("error", 0),
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            })
        st.dataframe(pd.DataFrame(scored_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(scored_rows), 300))


# ============================================================================
# ⚙️ ADMIN  — direct access to individual agents and outputs
# ============================================================================
elif page == "⚙️ Admin":
    st.title("⚙️ Admin")
    st.caption("The 🎯 Pipeline page is the main entry point. This page is for running individual "
               "agents directly, or browsing raw outputs.")

    # Quick-jump notice for month-end
    _admin_data_file = ROOT / "data" / "job_tracker_data.json"
    _admin_archive_dir = ROOT / "data" / "archives"
    _admin_tracker_jobs = 0
    try:
        _admin_tracker_jobs = len(json.loads(_admin_data_file.read_text(encoding="utf-8")).get("jobs", []))
    except Exception:
        pass
    _admin_archives = list(_admin_archive_dir.glob("job_tracker_*.json")) if _admin_archive_dir.exists() else []

    _admin_a1, _admin_a2 = st.columns([3, 1])
    with _admin_a1:
        st.info(
            f"**Month-end reset:** {_admin_tracker_jobs} jobs in live tracker · "
            f"{len(_admin_archives)} archive(s) on disk. "
            "Use **🗄️ Month-End Archive & Reset** below to archive and start fresh.",
            icon="🗄️",
        )
    with _admin_a2:
        # Streamlit has no in-page anchor scroll (the old hidden <a> + toast
        # was a no-op), so this is an honest advisory rather than a fake jump.
        st.caption("⬇️ The **🗄️ Month-End Archive & Reset** section is further "
                   "down this page.")

    # ---------- Cost ledger ----------
    st.subheader("💰 Cost ledger (lifetime)")
    st.caption(
        "Every LLM call from fit_scorer (and any future scorer/tailor that "
        "imports `cost_ledger`) is recorded here. Cumulative, never resets "
        "across sessions or machines (per this machine's `data/` folder)."
    )
    try:
        _ledger = cost_ledger.load()
        _tot = _ledger.get("totals", {}) or {}
        _pm = _ledger.get("per_model", {}) or {}
        _daily = _ledger.get("daily", {}) or {}

        cL1, cL2, cL3, cL4 = st.columns(4)
        cL1.metric("Total spend", f"${_tot.get('estimated_cost_usd', 0):.4f}")
        cL2.metric("LLM calls", f"{_tot.get('llm_calls', 0):,}")
        cL3.metric("Cache hits", f"{_tot.get('cache_hits', 0):,}")
        _in = _tot.get("input_tokens", 0) or 0
        _out = _tot.get("output_tokens", 0) or 0
        cL4.metric("Tokens", f"{(_in + _out):,}",
                   f"in {_in:,} · out {_out:,}")

        if _pm:
            st.markdown("**Per-model breakdown**")
            rows = []
            for model, m in sorted(_pm.items(), key=lambda kv: -kv[1].get("cost_usd", 0)):
                rows.append({
                    "model": model,
                    "calls": m.get("calls", 0),
                    "in_tokens": m.get("in_tokens", 0),
                    "out_tokens": m.get("out_tokens", 0),
                    "cost_usd": round(m.get("cost_usd", 0), 4),
                    "first_used": m.get("first_used", ""),
                    "last_used": m.get("last_used", ""),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

        if _daily:
            st.markdown("**Last 30 days**")
            # Sort by date desc, show top 30
            recent = sorted(_daily.items(), key=lambda kv: kv[0], reverse=True)[:30]
            drows = []
            for d, v in recent:
                drows.append({
                    "date": d,
                    "calls": v.get("calls", 0),
                    "in_tokens": v.get("in_tokens", 0),
                    "out_tokens": v.get("out_tokens", 0),
                    "cost_usd": round(v.get("cost_usd", 0), 4),
                })
            st.dataframe(pd.DataFrame(drows), hide_index=True, width='stretch',
                         height=min(40 + 36 * len(drows), 300))

        st.caption(f"Ledger file: `{cost_ledger.LEDGER_PATH}` · "
                   f"created {_ledger.get('created_at', '—')} · "
                   f"updated {_ledger.get('updated_at', '—')}")
    except Exception as _le:
        st.error(f"Ledger read failed: {_le}")
    st.markdown("---")

    # ---------- Backend session log (start.ps1) ----------
    # `logs/current.log` is a pointer file written by start.ps1 with the
    # path to the active session log (Streamlit + backend stdout/stderr).
    # PowerShell writes the pointer as UTF-8-with-BOM; the log itself is
    # UTF-16 LE. Guard the decode either way and strip ANSI before display.
    st.subheader("🪵 Backend session log")
    _logs_dir = ROOT / "logs"
    _pointer = _logs_dir / "current.log"
    _session_log = None
    if _pointer.exists():
        try:
            _p = _pointer.read_text(encoding="utf-8-sig").strip()
            if _p and Path(_p).exists():
                _session_log = Path(_p)
        except Exception:
            _session_log = None
    if _session_log is None:
        st.caption("No active session log. Launch via `start.ps1` to capture "
                   "Streamlit + backend stdout/stderr here.")
    else:
        st.caption(f"`{_session_log.name}`")
        try:
            _size = _session_log.stat().st_size
            _cap = 16_000
            with open(_session_log, "rb") as _lf:
                if _size > _cap:
                    _lf.seek(_size - _cap)
                    _raw = b"...[truncated]\n" + _lf.read()
                else:
                    _raw = _lf.read()
            if _raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                _txt = _raw.decode("utf-16", errors="replace")
            else:
                _txt = _raw.decode("utf-8", errors="replace")
            _txt = re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", _txt).replace("\r", "")
            st.code(_txt or "(empty)", language="text", height=320)
        except Exception as _le2:
            st.caption(f"(read error: {_le2})")
        if st.button("🔄 Refresh log", key="admin_session_log_refresh"):
            st.rerun()
    st.markdown("---")

    # ---------- Error log ----------
    st.subheader("🪵 Error log")
    st.caption(
        "Silent failures (progress-file writes, fit-cache corruption, "
        "HTTP retries exhausted, ledger writes) land in "
        "`logs/errors.jsonl`. One JSONL record per error — module, "
        "context, error_type, message, and traceback."
    )
    if error_log is None:
        st.info("`automation/error_log.py` isn't importable — skipping.")
    else:
        try:
            recent = error_log.recent_errors(limit=200)
        except Exception as _ree:
            st.error(f"Error log read failed: {_ree}")
            recent = []

        # Top metric row
        _last_hour = error_log.count_recent(since_minutes=60) if error_log else 0
        _last_day = error_log.count_recent(since_minutes=60 * 24) if error_log else 0
        em1, em2, em3, em4 = st.columns(4)
        em1.metric("Total recent", f"{len(recent):,}")
        em2.metric("Last hour", f"{_last_hour:,}")
        em3.metric("Last 24h", f"{_last_day:,}")
        em4.metric("Log file",
                   f"{(error_log.LOG_PATH.stat().st_size // 1024):,} KB"
                   if error_log.LOG_PATH.exists() else "—")

        if not recent:
            st.success("✅ No errors in the log.")
        else:
            # Filter row
            mods = sorted({r.get("module", "?") for r in recent})
            ctxs = sorted({r.get("context", "?") for r in recent})
            fe1, fe2, fe3 = st.columns([2, 2, 2])
            with fe1:
                pick_mod = st.multiselect("Module", mods, default=mods,
                                            key="err_mod")
            with fe2:
                pick_ctx = st.multiselect("Context", ctxs, default=[],
                                            key="err_ctx",
                                            help="Leave empty to show all")
            with fe3:
                err_q = st.text_input("Search message/traceback",
                                        key="err_q")

            def _match(rec):
                if rec.get("module") not in pick_mod:
                    return False
                if pick_ctx and rec.get("context") not in pick_ctx:
                    return False
                if err_q:
                    q = err_q.lower()
                    hay = (rec.get("message", "") + " "
                           + rec.get("traceback", "")).lower()
                    if q not in hay:
                        return False
                return True

            filtered = [r for r in recent if _match(r)]
            st.caption(f"Showing {len(filtered):,} of {len(recent):,} records")

            # Table view
            rows = [{
                "when": r.get("timestamp", ""),
                "module": r.get("module", "?"),
                "context": r.get("context", "?"),
                "error_type": r.get("error_type", "?"),
                "message": r.get("message", "")[:120],
            } for r in filtered]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                             width='stretch', height=300)

            # Drill-down on one record
            if filtered:
                labels = [
                    f"{r.get('timestamp','?')} · {r.get('module','?')} · "
                    f"{r.get('context','?')} · {r.get('error_type','?')}"
                    for r in filtered
                ]
                idx = st.selectbox("Inspect record", range(len(filtered)),
                                    format_func=lambda i: labels[i],
                                    key="err_pick")
                rec = filtered[idx]
                with st.container(border=True):
                    st.markdown(f"**{rec.get('error_type','?')}** "
                                f"in `{rec.get('module','?')}` / "
                                f"`{rec.get('context','?')}`")
                    st.caption(rec.get("timestamp", ""))
                    st.markdown(f"**Message:** {rec.get('message','')}")
                    if rec.get("traceback"):
                        st.code(rec["traceback"], language="text")
                    # Extra fields beyond the core schema
                    extra_keys = [k for k in rec
                                   if k not in {"timestamp", "module", "context",
                                                 "error_type", "message",
                                                 "traceback"}]
                    if extra_keys:
                        st.markdown("**Extra fields**")
                        st.json({k: rec[k] for k in extra_keys})

        # Archive-current-log button. Never deletes; renames the current
        # errors.jsonl to errors.archived_<stamp>.jsonl so the badge goes
        # back to green but the forensic record is preserved.
        st.markdown("---")
        ac1, ac2 = st.columns([1, 3])
        with ac1:
            if st.button("🗄 Archive current log", key="err_archive",
                          disabled=(error_log is None
                                    or not error_log.LOG_PATH.exists())):
                try:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest = error_log.LOG_PATH.with_name(
                        f"errors.archived_{stamp}.jsonl")
                    error_log.LOG_PATH.rename(dest)
                    st.success(f"Archived to {dest.name}")
                    st.rerun()
                except Exception as _ae:
                    st.error(f"Archive failed: {_ae}")
        with ac2:
            st.caption(
                "Archiving renames `errors.jsonl` to "
                "`errors.archived_<stamp>.jsonl`. The current log goes back "
                "to empty; the archive file stays in `logs/` for forensics."
            )
    st.markdown("---")

    # ---------- Weekly Maintenance ----------
    st.subheader("📅 Weekly Maintenance")
    st.caption(
        "Run these once a week to keep the search fresh. "
        "The nightly refresh does the URL rotation automatically, but you can "
        "trigger it manually here too."
    )

    _url_hist_path = OUT_DIR / "url_history.json"
    _url_archives  = sorted(OUT_DIR.glob("url_history_*.json"), reverse=True)

    # --- Metrics row ---
    wm_c1, wm_c2, wm_c3, wm_c4 = st.columns(4)

    if _url_hist_path.exists():
        _uh_age_s   = datetime.now().timestamp() - _url_hist_path.stat().st_mtime
        _uh_age_d   = _uh_age_s / 86400
        _uh_size_kb = _url_hist_path.stat().st_size / 1024
        try:
            _uh_count = len(json.loads(_url_hist_path.read_text(encoding="utf-8")))
        except Exception:
            _uh_count = "?"
        _uh_age_label = f"{_uh_age_d:.1f}d"
        _uh_delta     = ("🟢 fresh" if _uh_age_d < 3
                         else "🟡 aging" if _uh_age_d < 7
                         else "🔴 stale — rotate!")
        wm_c1.metric("URL history age", _uh_age_label, _uh_delta)
        wm_c2.metric("Seen URLs", f"{_uh_count:,}" if isinstance(_uh_count, int) else _uh_count)
        wm_c3.metric("History size", f"{_uh_size_kb:.0f} KB")
        wm_c4.metric("Archives on disk", len(_url_archives))
    else:
        wm_c1.metric("URL history age", "—")
        wm_c2.metric("Seen URLs", "—")
        wm_c3.metric("History size", "—")
        wm_c4.metric("Archives on disk", len(_url_archives))
        st.info("No url_history.json yet — it will be created on the first scrape.")

    st.markdown("")  # breathing room

    wm_btn_col, wm_info_col = st.columns([1, 3])

    with wm_btn_col:
        _rotate_disabled = bool(any_work_active) or not _url_hist_path.exists()
        if st.button("🔄 Rotate URL history now",
                     width='stretch',
                     disabled=_rotate_disabled,
                     help=("Rotates url_history.json immediately — same logic as "
                           "the auto-rotation in nightly refresh (archives the old "
                           "file, fresh db for next scrape).")):
            # Perform the rotation inline (same logic as nightly_refresh.py)
            try:
                _uh_age_s2  = datetime.now().timestamp() - _url_hist_path.stat().st_mtime
                _stamp      = datetime.now().strftime("%Y%m%d_%H%M%S")
                _archive    = _url_hist_path.with_name(f"url_history_{_stamp}.json")
                _url_hist_path.rename(_archive)
                st.success(
                    f"✅ Rotated! `url_history.json` → `{_archive.name}` "
                    f"({_uh_age_s2/86400:.1f}d old). "
                    "Next nightly refresh starts with a clean dedup database."
                )
                st.rerun()
            except Exception as _re:
                st.error(f"Rotation failed: {_re}")

    with wm_info_col:
        if _url_hist_path.exists():
            if _uh_age_d >= 7:
                st.warning(
                    "⚠️ URL history is **stale** (≥7 days). "
                    "Old job links are being filtered out of every scrape. "
                    "Rotate now — or run nightly refresh (it auto-rotates)."
                )
            elif _uh_age_d >= 3:
                st.info(
                    "🟡 URL history is aging. Nightly refresh will rotate it "
                    "automatically when it hits 7 days."
                )
            else:
                st.success("🟢 URL history is fresh — no action needed.")
        if _rotate_disabled and any_work_active:
            st.caption("⏳ Button available when no jobs are running.")

    # --- Old run logs cleanup ---
    st.markdown("")
    _runs_dir  = OUT_DIR / "runs"
    _old_logs  = []
    if _runs_dir.exists():
        _cutoff = datetime.now().timestamp() - 7 * 86400
        _old_logs = [p for p in _runs_dir.glob("*.log")
                     if p.stat().st_mtime < _cutoff]
    _total_log_kb = sum(p.stat().st_size for p in _old_logs) / 1024 if _old_logs else 0

    with st.expander(
        f"🧹 Old run logs — {len(_old_logs)} logs older than 7d "
        f"({_total_log_kb:.0f} KB)",
        expanded=False,
    ):
        if not _old_logs:
            st.success("No old run logs to clean up.")
        else:
            st.caption(
                f"These {len(_old_logs)} log files are >7 days old and safe to delete. "
                "JSON status files are kept so run history remains intact."
            )
            _log_rows = [{
                "file": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "age_days": round((datetime.now().timestamp() - p.stat().st_mtime) / 86400, 1),
            } for p in sorted(_old_logs, key=lambda x: x.stat().st_mtime)]
            st.dataframe(pd.DataFrame(_log_rows), hide_index=True, width='stretch')

            if st.button(
                f"🗑 Delete {len(_old_logs)} old log files ({_total_log_kb:.0f} KB)",
                type="secondary",
                key="wm_delete_old_logs",
            ):
                _errs = []
                for _lp in _old_logs:
                    try:
                        _lp.unlink()
                    except Exception as _le:
                        _errs.append(f"{_lp.name}: {_le}")
                if _errs:
                    st.error("Some files could not be deleted:\n" + "\n".join(_errs))
                else:
                    st.success(f"✅ Deleted {len(_old_logs)} old log files.")
                st.rerun()


    # ---------- Month-End Archive & Reset ----------
    st.subheader("🗄️ Month-End Archive & Reset")
    st.caption(
        "At the end of each search month, archive your full tracker to a dated snapshot "
        "and start fresh. All active jobs, outreach history, and follow-up schedules are "
        "preserved in the archive — the live tracker resets to zero new leads."
    )

    _data_file = ROOT / "data" / "job_tracker_data.json"
    _archive_dir = ROOT / "data" / "archives"
    _url_hist = ROOT / "automation" / "url_history.json"
    _now = datetime.now()
    _archive_month = _now.strftime("%Y%m")
    _archive_name = f"job_tracker_{_archive_month}.json"
    _archive_path = _archive_dir / _archive_name

    # Load current tracker for preview
    try:
        _tracker_raw = json.loads(_data_file.read_text(encoding="utf-8")) if _data_file.exists() else {}
        _all_jobs = _tracker_raw.get("jobs", [])
        _meta = _tracker_raw.get("meta", {})
        # Exclude archived rows from the pre-wipe preview counts so they
        # don't overstate active/applied/closed (doc §339). NOT is_active()
        # here — that would collapse the deliberate Applied+ vs Active-leads
        # split this preview relies on; a plain archived gate is correct.
        _applied_jobs  = [j for j in _all_jobs if j.get("status") in ("Applied","Recruiter_Screen","Phone_Screen","Take_Home","Onsite","Offer") and not j.get("archived", False)]
        _active_jobs   = [j for j in _all_jobs if j.get("status") in ("Found","JD_Verified","Tailoring","Watch") and not j.get("archived", False)]
        _closed_jobs   = [j for j in _all_jobs if j.get("status") in ("Rejected","Ghosted","Withdrawn","Expired") and not j.get("archived", False)]
        _tracker_ok = True
    except Exception as _te:
        _tracker_ok = False
        _all_jobs = []; _applied_jobs = []; _active_jobs = []; _closed_jobs = []
        _meta = {}

    # Status banner
    if _archive_path.exists():
        st.info(f"📋 Archive **{_archive_name}** already exists in `data/archives/`. Running again will overwrite it.")

    # Preview columns
    me_col1, me_col2, me_col3, me_col4 = st.columns(4)
    me_col1.metric("Total jobs in tracker", len(_all_jobs))
    me_col2.metric("In pipeline (Applied+)", len(_applied_jobs), help="Applied, Recruiter Screen, Phone Screen, Take Home, Onsite, Offer")
    me_col3.metric("Active leads", len(_active_jobs), help="Found, JD Verified, Tailoring, Watch")
    me_col4.metric("Closed", len(_closed_jobs), help="Rejected, Ghosted, Withdrawn, Expired")

    st.markdown(
        "▶️ **What will happen:**  \n"
        "1️⃣ Archive `data/job_tracker_data.json` → `data/archives/` (dated snapshot)  \n"
        "2️⃣ Reset the live tracker to **0 jobs** (meta / status enum / tier definitions preserved)  \n"
        "3️⃣ Update `campaign_start` to today and clear `changelog`"
    )

    _reset_url_hist = st.checkbox(
        "Also archive `url_history.json` (lets the scraper revisit all URLs next month)",
        value=True,
        key="me_reset_url_hist",
    )

    _me_confirm = st.text_input(
        "Type **NEW MONTH** to confirm",
        value="",
        key="me_confirm_phrase",
        placeholder="NEW MONTH",
    )

    _me_ready = _me_confirm.strip() == "NEW MONTH" and _tracker_ok

    if st.button(
        "🗄️ Archive & Reset for New Month",
        type="primary",
        width="stretch",
        disabled=not _me_ready,
        key="me_archive_go",
        help="Type NEW MONTH above to enable" if not _me_ready else None,
    ):
        try:
            # 1. Create archive dir
            _archive_dir.mkdir(parents=True, exist_ok=True)

            # 2. Write archive snapshot
            _archive_path.write_text(
                _data_file.read_text(encoding="utf-8"), encoding="utf-8"
            )

            # 3. Build fresh tracker (preserve meta fields, wipe jobs/changelog)
            _fresh_meta = dict(_meta)
            _fresh_meta["last_reset"] = _now.strftime("%Y-%m-%d")
            _fresh_meta["campaign_start"] = _now.strftime("%Y-%m-%d")
            _fresh_meta["scan_count"] = 0
            _fresh_meta["total_roles"] = 0
            _fresh_meta["changelog"] = [
                {
                    "date": _now.strftime("%Y-%m-%d"),
                    "event": f"Month-end reset. Archived {len(_all_jobs)} jobs to {_archive_name}.",
                }
            ]
            _fresh_tracker = {
                "meta": _fresh_meta,
                "jobs": [],
            }
            # Route through save_tracker so we get the .bak.<timestamp>.json
            # safety copy in addition to the dated archive above. If the
            # write crashes mid-JSON, the .bak file is untouched.
            save_tracker(_fresh_tracker)

            # 4. Optionally archive url_history. Same belt-and-braces:
            # write a .bak alongside the dated archive before the reset
            # write, so a crash mid-write doesn't leave the file empty.
            if _reset_url_hist and _url_hist.exists():
                # Read once; reuse for both archive and bak so we don't risk
                # the source file changing between reads.
                _uh_src = _url_hist.read_text(encoding="utf-8")
                _uh_dest = _url_hist.parent / f"url_history_{_archive_month}.json"
                _uh_dest.write_text(_uh_src, encoding="utf-8")
                _uh_bak = _url_hist.with_suffix(
                    f".bak.{_now.strftime('%Y%m%d-%H%M%S')}.json"
                )
                _uh_bak.write_text(_uh_src, encoding="utf-8")
                # Atomic reset: tempfile + os.replace so a crash between
                # truncate and re-populate can't leave url_history empty.
                import os as _os, tempfile as _tf
                _fresh = json.dumps(
                    {"urls": [], "archived_on": _now.strftime("%Y-%m-%d")},
                    indent=2,
                )
                _fd, _tmp = _tf.mkstemp(prefix=_url_hist.name + ".",
                                          suffix=".tmp",
                                          dir=str(_url_hist.parent))
                try:
                    with _os.fdopen(_fd, "w", encoding="utf-8") as _f:
                        _f.write(_fresh)
                    _os.replace(_tmp, _url_hist)
                except Exception:
                    try: _os.unlink(_tmp)
                    except OSError: pass
                    raise
                _url_msg = "  \n✅ URL history archived to `" + _uh_dest.name + "` and reset."
            else:
                _url_msg = ""

            _success_msg = (
                "✅ **Month-end reset complete!**  \n"
                + f"🗄️ {len(_all_jobs)} jobs archived → `data/archives/{_archive_name}`  \n"
                + f"🔄 Live tracker reset to 0 jobs." + _url_msg
            )
            st.success(_success_msg)
            st.cache_data.clear()
            st.rerun()

        except Exception as _me_err:
            st.error(f"❌ Reset failed: {_me_err}")

    if not _tracker_ok:
        st.warning("Could not read tracker file — check `data/job_tracker_data.json`.")

    # Show existing archives
    if _archive_dir.exists():
        _existing_archives = sorted(_archive_dir.glob("job_tracker_*.json"), reverse=True)
        if _existing_archives:
            with st.expander(f"📚 Past archives ({len(_existing_archives)} found)", expanded=False):
                for _af in _existing_archives:
                    try:
                        _af_data = json.loads(_af.read_text(encoding="utf-8"))
                        _af_jobs = len(_af_data.get("jobs", []))
                        _af_size = _af.stat().st_size // 1024
                        _af_mtime = datetime.fromtimestamp(_af.stat().st_mtime).strftime("%Y-%m-%d")
                        st.caption(f"📄 `{_af.name}` — {_af_jobs} jobs, {_af_size} KB, archived {_af_mtime}")
                    except Exception:
                        st.caption(f"📄 `{_af.name}`")

    st.markdown("---")

    # ---------- Reset & cleanup ----------
    # Four scopes, each a two-click (plan -> confirm -> execute) flow so
    # the user always sees WHAT will be deleted before it happens. The
    # plan/execute split lives in automation/reset_ops.py.
    st.subheader("🗑 Reset & cleanup")
    st.caption(
        "Delete specific runs, clear caches, or reset the whole app. "
        "Every destructive action shows a preview first; `Full reset` "
        "requires a typed confirmation phrase. Backups are made of "
        "tracker/CRM/ledger before any reset so you can roll back."
    )

    try:
        import reset_ops  # noqa: E402  (already on sys.path via automation/)
    except Exception as _rx:
        st.error(f"reset_ops module unavailable: {_rx}")
        reset_ops = None  # type: ignore

    if reset_ops is not None:
        # Inventory bar — what's on disk right now
        _inv = reset_ops.inventory_outputs()
        iv1, iv2, iv3, iv4, iv5 = st.columns(5)
        iv1.metric("Scans", _inv["scan_count"])
        iv2.metric("Scored", _inv["scored_count"])
        iv3.metric("Pipeline runs", _inv["pipeline_runs"])
        iv4.metric("Tailor docs", _inv["tailor_docs"])
        iv5.metric("outputs/ size",
                    f"{_inv['outputs_bytes'] / (1024*1024):.1f} MB")
        st.caption(
            f"Caches: JD {_inv['jd_cache_bytes']//1024} KB · "
            f"Fit {_inv['fit_cache_bytes']//1024} KB · "
            f"background runs logged: {_inv['background_runs']}"
        )

        reset_tabs = st.tabs([
            "🎯 Delete one scan",
            "🧹 Clear all scans",
            "💾 Clear caches",
            "💣 Full reset",
        ])

        # -------- Tab 1: Delete one scan ---------------------------------
        with reset_tabs[0]:
            scans = reset_ops.list_scans()
            if not scans:
                st.info("No scans on disk yet — run the scraper in 🎯 Pipeline.")
            else:
                labels = [
                    f"{s['stem']} · {s['rows']:,} rows · "
                    f"{s['size_kb']:,} KB · {s['mtime']}"
                    for s in scans
                ]
                idx = st.selectbox(
                    "Scan to delete", range(len(scans)),
                    format_func=lambda i: labels[i],
                    key="reset_scan_pick",
                )
                chosen = scans[idx]
                plan = reset_ops.plan_delete_scan(chosen["stem"])
                if plan.files_to_delete:
                    st.markdown("**Will delete:**")
                    for p in plan.files_to_delete:
                        st.code(str(p.name), language="text")
                    st.caption(f"Total: {plan.summary()}")
                    rc1, rc2 = st.columns([1, 3])
                    with rc1:
                        if st.button("🗑 Delete this scan",
                                      type="primary",
                                      width='stretch',
                                      key="reset_scan_go"):
                            result = reset_ops.execute(plan)
                            if result.errors:
                                st.error(
                                    f"Deleted {result.deleted_files} file(s); "
                                    f"{len(result.errors)} error(s): "
                                    + "; ".join(result.errors[:3])
                                )
                            else:
                                st.success(
                                    f"Deleted {result.deleted_files} file(s) "
                                    f"({result.deleted_bytes/1024:.0f} KB)."
                                )
                            st.cache_data.clear()
                            st.rerun()
                    with rc2:
                        st.caption(
                            "One-click delete. No typed confirmation for "
                            "single-scan deletes — small blast radius."
                        )

        # -------- Tab 2: Clear all scans ---------------------------------
        with reset_tabs[1]:
            plan = reset_ops.plan_clear_scans()
            if not plan.files_to_delete:
                st.info("No scans to clear.")
            else:
                st.markdown(
                    f"**Will delete {len(plan.files_to_delete)} file(s)** "
                    f"(~{plan.total_bytes/(1024*1024):.1f} MB):"
                )
                preview_n = min(10, len(plan.files_to_delete))
                for p in plan.files_to_delete[:preview_n]:
                    st.code(p.name, language="text")
                if len(plan.files_to_delete) > preview_n:
                    st.caption(
                        f"… +{len(plan.files_to_delete) - preview_n} more")
                st.caption(
                    f"**Preserved:** {', '.join(plan.preserved)}. "
                    "The scan_checkpoint.json is also preserved so an "
                    "in-progress paused scrape can still resume."
                )
                if st.checkbox("I understand this removes all scan history",
                                 key="reset_scans_ack"):
                    if st.button("🧹 Clear all scans now",
                                  type="primary",
                                  width='stretch',
                                  key="reset_scans_go"):
                        result = reset_ops.execute(plan)
                        if result.errors:
                            st.error(
                                f"Deleted {result.deleted_files} file(s); "
                                f"{len(result.errors)} error(s): "
                                + "; ".join(result.errors[:3])
                            )
                        else:
                            st.success(
                                f"Deleted {result.deleted_files} file(s) "
                                f"({result.deleted_bytes/(1024*1024):.1f} MB)."
                            )
                        st.cache_data.clear()
                        st.rerun()

        # -------- Tab 3: Clear caches ------------------------------------
        with reset_tabs[2]:
            plan = reset_ops.plan_clear_caches()
            st.markdown(
                f"**Will empty** `jd_cache/` and `fit_cache/` "
                f"({len(plan.files_to_delete)} file(s), "
                f"~{plan.total_bytes/1024:.0f} KB)."
            )
            st.caption(
                "Forces scrapes to re-fetch JDs and the scorer to re-call "
                "the LLM on every role. Useful when scoring logic changed "
                "and you want clean re-runs. Does NOT delete scans, "
                "scored files, tracker, CRM, or the lifetime ledger."
            )
            if plan.files_to_delete:
                if st.button("💾 Clear caches",
                              type="primary",
                              width='stretch',
                              key="reset_cache_go"):
                    result = reset_ops.execute(plan)
                    if result.errors:
                        st.error(
                            f"Deleted {result.deleted_files} file(s); "
                            f"{len(result.errors)} error(s): "
                            + "; ".join(result.errors[:3])
                        )
                    else:
                        st.success(
                            f"Deleted {result.deleted_files} cache file(s) "
                            f"({result.deleted_bytes/1024:.0f} KB)."
                        )
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.info("Caches already empty.")

        # -------- Tab 4: Full reset --------------------------------------
        with reset_tabs[3]:
            plan = reset_ops.plan_full_reset()
            st.warning(
                "**Full reset** wipes `automation/outputs/`, clears the "
                "tracker, clears the recruiter CRM, and resets the "
                "lifetime cost ledger to zero. Tracker, CRM, and ledger "
                "are backed up first.",
                icon="⚠️",
            )
            rf1, rf2 = st.columns([1, 1])
            with rf1:
                st.markdown("**Will delete:**")
                st.caption(
                    f"{len(plan.files_to_delete)} top-level file(s), "
                    f"{len(plan.dirs_to_empty)} subdir(s) emptied, "
                    f"{len(plan.json_to_reset)} JSON reset, "
                    f"ledger zeroed. "
                    f"~{plan.total_bytes/(1024*1024):.1f} MB freed."
                )
            with rf2:
                st.markdown("**Preserved:**")
                for pr in plan.preserved:
                    st.caption(f"· {pr}")
            required_phrase = "RESET EVERYTHING"
            typed = st.text_input(
                f'Type `{required_phrase}` to confirm',
                value="",
                key="reset_full_confirm",
                placeholder=required_phrase,
            )
            if st.button("💣 Full reset (cannot be undone except from backups)",
                          type="primary",
                          width='stretch',
                          disabled=(typed.strip() != required_phrase),
                          key="reset_full_go"):
                result = reset_ops.execute(
                    plan,
                    confirm_phrase=typed,
                    required_phrase=required_phrase,
                )
                if result.errors:
                    st.error(
                        f"Partial reset: {result.deleted_files} file(s) "
                        f"deleted, {len(result.errors)} error(s): "
                        + "; ".join(result.errors[:5])
                    )
                else:
                    st.success(
                        f"✅ Full reset complete. "
                        f"{result.deleted_files} file(s) removed "
                        f"({result.deleted_bytes/(1024*1024):.1f} MB). "
                        f"Tracker + CRM + ledger: reset. "
                        f"Backups: {len(result.backups)}."
                    )
                    for bak in result.backups:
                        st.caption(f"🗄 backup: `{bak.name}`")
                st.cache_data.clear()
                st.rerun()

    st.markdown("---")

    # ---------- Nightly schedule ----------
    st.subheader("🌙 Nightly schedule")
    st.caption(
        "Install a Windows scheduled task that runs scrape + delta + brief at 6:30 AM "
        "daily. You wake up to fresh matches on the Dashboard."
    )
    sch_col1, sch_col2 = st.columns(2)
    with sch_col1:
        st.code(
            "# One-time install (from PowerShell, not as admin):\n"
            f"cd {ROOT}\n"
            "powershell -ExecutionPolicy Bypass -File automation\\install_schedule.ps1",
            language="powershell",
        )
    with sch_col2:
        st.code(
            "# Check status / run now / uninstall:\n"
            "schtasks /query /tn ApplyAgent_NightlyRefresh /v /fo LIST\n"
            "schtasks /run   /tn ApplyAgent_NightlyRefresh\n"
            "schtasks /delete /tn ApplyAgent_NightlyRefresh /f",
            language="powershell",
        )
    _admin_scrape_age = _web_scan_age_hours()
    _admin_scrape_fresh = _admin_scrape_age is not None and _admin_scrape_age < 24
    _admin_nr_help = "Disabled while another job is running." if any_work_active else None
    if _admin_scrape_fresh and not any_work_active:
        _admin_nr_help = (f"⚠️ Scan is only {_admin_scrape_age:.0f}h old — "
                          "scrape step will likely find nothing new.")
    if st.button("🌅 Run nightly refresh now (background)",
                 width='content',
                 disabled=bool(any_work_active),
                 help=_admin_nr_help):
        _nr_cmd = [sys.executable, str(ROOT / "automation" / "nightly_refresh.py")]
        _nr_rec = scan_runner.start_run("nightly_refresh", _nr_cmd)
        st.session_state["_last_launch"] = {"run_id": _nr_rec.run_id, "label": "Nightly refresh"}
        st.toast("🌅 Nightly refresh launched!", icon="🚀")
        st.rerun()
    if any_work_active:
        st.caption("⏳ A job is already running — button re-enables when it finishes.")
    elif _admin_scrape_fresh:
        st.caption(f"⚠️ Scan {_admin_scrape_age:.0f}h old — scrape step will be a no-op")

    st.markdown("---")

    st.subheader("📁 Outputs directory")
    out_files = sorted(OUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out_files = [p for p in out_files if p.is_file()][:40]
    if out_files:
        rows = [{
            "file": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        } for p in out_files]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=320)

    st.markdown("---")
    st.subheader("Run a single agent")

    agent = st.radio("Agent", ["Weekly report", "JD tailor"], horizontal=True)

    if agent == "Weekly report":
        if st.button("📊 Generate weekly report", type="primary",
                     disabled=any_work_active):
            cmd = [sys.executable, str(ROOT / "automation" / "weekly_report.py")]
            # Detached launch (was a blocking subprocess.run freezing the UI
            # for up to 120s). Output renders below when the run settles.
            start_inline_agent("weekly_report", "weekly_report", cmd)
            st.rerun()
        run_inline_agent(
            "weekly_report", "Weekly report",
            running_msg="Generating weekly report… UI stays responsive.",
        )

    elif agent == "JD tailor":
        if jobs_df.empty:
            st.info("Tracker is empty — nothing to archive yet.")
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                pick = st.selectbox("Role", jobs_df["id"].tolist())
            with c2:
                dry = st.checkbox("Dry run (no API)", value=False)
            _ad_tailor_ok = api_key.is_key_valid() or dry
            if not _ad_tailor_ok:
                st.caption("🔑 API key required (or tick Dry run).")
            if st.button("✏️ Tailor resume + cover", type="primary",
                         disabled=(not _ad_tailor_ok or any_work_active)):
                cmd = [sys.executable, str(ROOT / "automation" / "jd_tailor.py"),
                       "--job-id", pick]
                if dry:
                    cmd.append("--dry-run")
                # Detached launch (was a blocking subprocess.run freezing the
                # UI for up to 300s). Output renders below when it settles.
                start_inline_agent("jd_tailor_admin", f"tailor_{pick}", cmd)
                st.session_state["_inline_tailor_admin_pick"] = pick
                st.rerun()

            def _render_tailor_admin(log_text, rec):
                st.code(log_text[-4000:] if log_text else "(no output)",
                        language="text")
                _pick = st.session_state.get("_inline_tailor_admin_pick", "")
                if _pick:
                    latest = sorted(
                        OUT_DIR.glob(f"*_{_pick.replace('-', '_')}*.md"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
                    if latest:
                        with st.expander(f"Output: {latest[0].name}",
                                         expanded=True):
                            st.markdown(latest[0].read_text(encoding="utf-8"))
                st.session_state.pop("_inline_tailor_admin_pick", None)

            run_inline_agent(
                "jd_tailor_admin", "JD tailor", on_finish=_render_tailor_admin,
                running_msg="Tailoring resume + cover… UI stays responsive.",
            )

# ═══════════════════════════════════════════════════════════════════════════
# 📊 ANALYTICS PAGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📊 Analytics":
    import altair as alt

    st.title("📊 Analytics")
    st.caption("Search pipeline at a glance — funnel, fit distribution, sector coverage, and scrape trends.")

    # ── Load data ──────────────────────────────────────────────────────────
    _an_tracker = load_tracker()
    _an_jobs    = _an_tracker.get("jobs", [])

    # Scan files for trend. Match scan_YYYYMMDD.json only — the loose
    # scan_*.json glob also pulled in scan_YYYYMMDD_scored.json sidecars,
    # which are missing top-level scrape stats and crashed Analytics with
    # KeyError('total_new_candidates').
    _an_scan_files = sorted(
        p for p in OUT_DIR.glob("scan_*.json")
        if p.stem.replace("scan_", "").isdigit() and len(p.stem) == 13
    )
    _an_scans = []
    for _sf in _an_scan_files:
        try:
            _sd = json.loads(_sf.read_text(encoding="utf-8"))
            _an_scans.append(_sd)
        except Exception:
            pass

    # ── TOP KPI ROW ────────────────────────────────────────────────────────
    _an_scraped  = (_an_scans[-1].get("total_new_candidates", 0) if _an_scans else 0)
    _an_tracked  = len(_an_jobs)
    _an_high_fit = sum(1 for j in _an_jobs if (j.get("fit_score_numeric") or 0) >= 4)
    _an_applied  = sum(1 for j in _an_jobs if j.get("date_applied"))
    _an_response = sum(1 for j in _an_jobs
                       if j.get("rejection_date") or j.get("status") in ("Offer", "Interview"))

    _ak1, _ak2, _ak3, _ak4, _ak5 = st.columns(5)
    _ak1.metric("Latest scrape",  f"{_an_scraped:,}",  help="New candidates from most recent scrape (post-dedup)")
    _ak2.metric("Tracked jobs",   str(_an_tracked),    help="Total jobs in your tracker")
    _ak3.metric("High-fit (4–5)", str(_an_high_fit),   help="fit_score_numeric ≥ 4")
    _ak4.metric("Applied",        str(_an_applied),    help="date_applied is set")
    _ak5.metric("Responses",      str(_an_response),   help="Rejection logged or Interview/Offer status")

    st.markdown("---")

    # ── ROW 1: Funnel + Score Distribution ────────────────────────────────
    _an_col_l, _an_col_r = st.columns(2)

    with _an_col_l:
        st.markdown("#### 🔽 Application funnel")
        _an_funnel_df = pd.DataFrame({
            "Stage": ["Scraped", "Tracked", "High-fit", "Applied", "Response"],
            "Count": [_an_scraped, _an_tracked, _an_high_fit, _an_applied, _an_response],
        })
        _an_funnel_chart = (
            alt.Chart(_an_funnel_df)
            .mark_bar(color="#6366f1", cornerRadiusEnd=4)
            .encode(
                x=alt.X("Count:Q", title="Jobs"),
                y=alt.Y("Stage:N",
                        sort=["Scraped", "Tracked", "High-fit", "Applied", "Response"],
                        title=None),
                tooltip=["Stage:N", "Count:Q"],
            )
            .properties(height=220)
        )
        st.altair_chart(_an_funnel_chart, use_container_width=True)
        if _an_scraped:
            st.caption(
                f"Scraped → Tracked conversion: "
                f"**{_an_tracked / _an_scraped * 100:.1f}%**"
            )

    with _an_col_r:
        st.markdown("#### ⭐ Fit score distribution")
        _an_score_counts: dict = {}
        for _j in _an_jobs:
            _s = _j.get("fit_score_numeric")
            if _s is not None:
                _an_score_counts[int(_s)] = _an_score_counts.get(int(_s), 0) + 1
        if _an_score_counts:
            _an_score_df = pd.DataFrame([
                {"Score": f"{int(k)} ({'⭐' * int(k)})", "Count": v, "_k": int(k)}
                for k, v in _an_score_counts.items()
            ]).sort_values("_k")
            _an_score_chart = (
                alt.Chart(_an_score_df)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Score:N", sort=alt.SortField("_k"), title="Fit Score"),
                    y=alt.Y("Count:Q", title="Jobs"),
                    color=alt.Color(
                        "_k:Q",
                        scale=alt.Scale(domain=[3, 4, 5],
                                        range=["#f59e0b", "#10b981", "#6366f1"]),
                        legend=None,
                    ),
                    tooltip=["Score:N", "Count:Q"],
                )
                .properties(height=220)
            )
            st.altair_chart(_an_score_chart, use_container_width=True)
            st.caption("  ·  ".join(
                f"**{lbl}**: {_an_score_counts.get(k, 0)}"
                for lbl, k in [("High (5)", 5), ("Strong (4)", 4), ("Medium (3)", 3)]
                if _an_score_counts.get(k)
            ))
        else:
            st.info("No scored jobs yet — run the scorer in 🎯 Pipeline.")

    st.markdown("---")

    # ── ROW 2: Sector breakdown + Urgency donut ───────────────────────────
    _an_col2_l, _an_col2_r = st.columns([3, 2])

    with _an_col2_l:
        st.markdown("#### 🏢 Sector breakdown")
        _an_sector_counts: dict = {}
        for _j in _an_jobs:
            _sec = (_j.get("sector") or "Unknown")
            _an_sector_counts[_sec] = _an_sector_counts.get(_sec, 0) + 1
        _an_sector_df = pd.DataFrame([
            {"Sector": k, "Jobs": v}
            for k, v in _an_sector_counts.items()
        ])
        if "Jobs" in _an_sector_df.columns:
            _an_sector_df = _an_sector_df.sort_values("Jobs", ascending=False)
        _an_sector_chart = (
            alt.Chart(_an_sector_df)
            .mark_bar(color="#0ea5e9", cornerRadiusEnd=4)
            .encode(
                x=alt.X("Jobs:Q"),
                y=alt.Y("Sector:N", sort="-x", title=None),
                tooltip=["Sector:N", "Jobs:Q"],
            )
            .properties(height=max(220, len(_an_sector_df) * 26))
        )
        st.altair_chart(_an_sector_chart, use_container_width=True)

    with _an_col2_r:
        st.markdown("#### 🚦 Urgency breakdown")
        _an_urg_order  = ["High", "Medium", "Low", "Unknown"]
        _an_urg_counts: dict = {}
        for _j in _an_jobs:
            _u = _j.get("urgency") or "Unknown"
            _an_urg_counts[_u] = _an_urg_counts.get(_u, 0) + 1
        _an_urg_df = pd.DataFrame([
            {"Urgency": k, "Jobs": _an_urg_counts.get(k, 0),
             "Color": URGENCY_COLORS.get(k, _C_SLATE)}
            for k in _an_urg_order if _an_urg_counts.get(k, 0) > 0
        ])
        if not _an_urg_df.empty:
            _an_urg_chart = (
                alt.Chart(_an_urg_df)
                .mark_arc(innerRadius=50)
                .encode(
                    theta=alt.Theta("Jobs:Q"),
                    color=alt.Color(
                        "Urgency:N",
                        scale=alt.Scale(
                            domain=list(_an_urg_df["Urgency"]),
                            range=list(_an_urg_df["Color"]),
                        ),
                    ),
                    tooltip=["Urgency:N", "Jobs:Q"],
                )
                .properties(height=220)
            )
            st.altair_chart(_an_urg_chart, use_container_width=True)
        for _u in _an_urg_order:
            _cnt = _an_urg_counts.get(_u, 0)
            if _cnt:
                _ic = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(_u, "⚪")
                st.caption(f"{_ic} **{_u}**: {_cnt}")

    st.markdown("---")

    # ── ROW 3: Scrape trend ───────────────────────────────────────────────
    st.markdown("#### 📈 Scrape volume trend")
    if len(_an_scans) >= 2:
        _an_trend_rows = []
        for _sd in _an_scans:
            _raw = str(_sd.get("scan_date", ""))
            try:
                _lbl = datetime.strptime(_raw, "%Y%m%d").strftime("%b %d")
            except Exception:
                _lbl = _raw
            _dd = _sd.get("dedup_stats", {})
            _an_trend_rows.append({
                "Date":              _lbl,
                "Input (raw)":       _dd.get("input", 0),
                "Dropped (URL dup)": _dd.get("dropped_url", 0),
                "Dropped (near-dup)":_dd.get("dropped_near", 0),
                "Scraped (kept)":    _sd.get("total_new_candidates", 0),
            })
        _an_trend_long = pd.DataFrame(_an_trend_rows).melt(
            id_vars=["Date"],
            value_vars=["Input (raw)", "Dropped (URL dup)", "Dropped (near-dup)", "Scraped (kept)"],
            var_name="Metric",
            value_name="Count",
        )
        _an_trend_chart = (
            alt.Chart(_an_trend_long)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X("Date:N", title="Scan date"),
                y=alt.Y("Count:Q", title="Jobs"),
                color=alt.Color(
                    "Metric:N",
                    scale=alt.Scale(
                        domain=["Input (raw)", "Dropped (URL dup)",
                                "Dropped (near-dup)", "Scraped (kept)"],
                        range=["#94a3b8", "#f59e0b", "#ef4444", "#6366f1"],
                    ),
                ),
                tooltip=["Date:N", "Metric:N", "Count:Q"],
            )
            .properties(height=260)
        )
        st.altair_chart(_an_trend_chart, use_container_width=True)
        _an_last  = _an_scans[-1]
        _an_in    = (_an_last.get("dedup_stats", {}).get("input") or 1)
        _an_out   = (_an_last.get("total_new_candidates") or 0)
        st.caption(
            f"Latest dedup efficiency: **{_an_out / _an_in * 100:.0f}%** kept "
            f"({_an_out:,} of {_an_in:,} raw candidates). "
            f"{len(_an_scans)} scan{'s' if len(_an_scans) != 1 else ''} on record."
        )
    else:
        st.info("Need ≥ 2 scans to show a trend. Run the nightly pipeline to accumulate data.")
        if _an_scans:
            _an_one = _an_scans[0]
            _sc1, _sc2, _sc3 = st.columns(3)
            _sc1.metric("Input (raw)", _an_one.get("dedup_stats", {}).get("input", 0))
            _sc2.metric("After dedup", _an_one.get("total_new_candidates", 0))
            _sc3.metric("Companies",   _an_one.get("companies_scanned", 0))

    st.markdown("---")

    # ── ROW 4: Sector scan coverage (latest scrape) ───────────────────────
    st.markdown("#### 🗺️ Sector scan coverage (latest scrape)")
    if _an_scans:
        _an_by_sector = _an_scans[-1].get("by_sector", {})
        if _an_by_sector:
            _an_cov_df = pd.DataFrame([
                {"Sector": k, "Open roles": v}
                for k, v in sorted(_an_by_sector.items(), key=lambda x: -x[1])
            ])
            _an_cov_chart = (
                alt.Chart(_an_cov_df)
                .mark_bar(color="#818cf8", cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Open roles:Q"),
                    y=alt.Y("Sector:N", sort="-x", title=None),
                    tooltip=["Sector:N", "Open roles:Q"],
                )
                .properties(height=max(220, len(_an_cov_df) * 24))
            )
            st.altair_chart(_an_cov_chart, use_container_width=True)
            _an_total_open = sum(_an_by_sector.values())
            st.caption(
                f"**{_an_total_open:,}** total open roles across "
                f"**{len(_an_by_sector)}** sectors "
                f"(scan {_an_scans[-1].get('scan_date', 'unknown')})."
            )
    else:
        st.info("No scan files yet — run the nightly pipeline to generate scan data.")


# ===========================================================================
# REVIEW QUEUE PAGE
# One-at-a-time card workflow for triaging "Found" jobs.
# ===========================================================================
elif page == "📬 Review Queue":
    st.title("📬 Review Queue")
    st.caption(
        "Work through new matches one card at a time. "
        "Each card shows fit, keywords, and the suggested next action. "
        "Promote to Watch, Shortlist, or Expire your choice."
    )

    # Live panel: review queue is populated by the pipeline; surface
    # in-flight runs so the user knows new rows may be incoming.
    _pipeline_live_panel()

    # Stale-scan banner: review queue draws from "Found" rows promoted
    # off the latest scan; warn if that scan is aging.
    _rq_scan_age_h = _web_scan_age_hours()
    if _rq_scan_age_h is not None and _rq_scan_age_h >= 48:
        _days = _rq_scan_age_h / 24
        st.info(
            f"🛰 Web scan is **{_days:.0f}d old**. The cards below may be "
            "missing recent roles. Run a scrape from 🎯 Pipeline to refresh.",
            icon="⏰",
        )

    # Phase 3D — Pending-archive retry banner. If a previous Mute+Archive
    # left a row in the deferred queue (suppression saved, archive failed),
    # surface a one-click retry up here so the user isn't ambushed by a
    # job re-appearing in their queue.
    try:
        from automation import suppressions as _supp_top  # noqa: WPS433
        _pending = _supp_top.drain_pending_archives() \
            if st.session_state.get("_rq_drain_pending") else []
        # Read-only peek (don't drain): use a separate file probe so we
        # don't mutate state on every render.
        _PENDING_PATH = ROOT / "data" / "suppressions_pending_archives.jsonl"
        _pending_count = 0
        if _PENDING_PATH.exists():
            for _ln in _PENDING_PATH.read_text(encoding="utf-8").splitlines():
                if _ln.strip():
                    _pending_count += 1
        if _pending_count:
            with st.container(border=True):
                st.warning(
                    f"⚠️ {_pending_count} archive(s) deferred from previous "
                    "mute action(s). Retry now to clean up.",
                    icon="📁",
                )
                if st.button("🔁 Retry deferred archives",
                              key="_rq_retry_pending"):
                    from safe_json import mutate_json as _mj_r  # noqa: WPS433
                    from automation import tracker_ops as _tops_r  # noqa: WPS433
                    _drained = _supp_top.drain_pending_archives()
                    _retry_ok = 0
                    _retry_fail: list[str] = []
                    for _entry in _drained:
                        _jid = _entry.get("job_id", "")
                        try:
                            _mj_r(TRACKER,
                                   lambda t, _j=_jid: _tops_r.archive(
                                       t, _j, "deferred_retry"),
                                   default={"jobs": [], "meta": {}})
                            _retry_ok += 1
                        except Exception as _exc:  # noqa: BLE001
                            _retry_fail.append(f"{_jid}: {_exc}")
                            try:
                                _supp_top.queue_pending_archive(
                                    _jid, str(_entry.get("reason", "")),
                                )
                            except Exception:
                                pass
                    load_tracker.clear()
                    if _retry_ok:
                        st.toast(f"📁 Archived {_retry_ok} deferred row(s)",
                                  icon="✅")
                    if _retry_fail:
                        st.error("Some archives still failed:\n- "
                                  + "\n- ".join(_retry_fail[:5]))
                    st.rerun()
    except Exception:
        pass  # never let the banner break the page

    # Phase 3D — [Undo] chip for the most recent mute (within 12 minutes).
    _undo_state = st.session_state.get("_rq_mute_undo")
    if isinstance(_undo_state, dict):
        try:
            _undo_age_min = (datetime.now() - datetime.fromisoformat(
                _undo_state.get("ts") or ""
            )).total_seconds() / 60
        except Exception:
            _undo_age_min = 999
        if _undo_age_min < 12:
            _uc1, _uc2 = st.columns([5, 1])
            _uc1.caption(
                f"🔇 Recently muted {_undo_state['scope']} "
                f"{_undo_state['name']!r}. Click Undo if that wasn't right."
            )
            if _uc2.button("↶ Undo", key="_rq_undo_mute"):
                try:
                    from automation import suppressions as _supp_undo  # noqa: WPS433
                    # lift() silently no-ops (logs lift_noop) when the mute is
                    # already gone — e.g. another tab/session lifted it, or it
                    # expired. Probe before/after like the CLI's _cmd_lift so
                    # the toast reflects what actually happened instead of
                    # always claiming success.
                    _u_scope = _undo_state["scope"]
                    _u_key = _u_scope + "s"
                    _before = _supp_undo.load_active()
                    _before_keys = {e.get("canonical_key")
                                    for e in _before.get(_u_key, []) or []}
                    _supp_undo.lift(_u_scope, _undo_state["name"])
                    _after = _supp_undo.load_active()
                    _after_keys = {e.get("canonical_key")
                                   for e in _after.get(_u_key, []) or []}
                    if _before_keys - _after_keys:
                        st.toast("Mute undone", icon="↶")
                    else:
                        st.toast("Mute already lifted — nothing to undo",
                                 icon="ℹ️")
                except Exception as _exc:  # noqa: BLE001
                    st.error(f"Undo failed: {_exc}")
                del st.session_state["_rq_mute_undo"]
                st.rerun()
        else:
            del st.session_state["_rq_mute_undo"]

    # Pull jobs needing review (Found, highest fit first)
    # Phase 3D: respect the `archived` field so muted-and-archived rows
    # disappear from the queue immediately. tracker_ops.is_active applies
    # the canonical filter `not archived AND status not in TERMINAL`; we
    # intersect with status=="Found" because the Review Queue is the
    # Found-row triage page specifically.
    from automation import tracker_ops as _tops_rq  # noqa: WPS433
    _rq_all   = load_tracker()
    _rq_jobs  = _rq_all.get("jobs", [])
    _rq_queue = sorted(
        [j for j in _rq_jobs
         if j.get("status") == "Found" and not j.get("archived", False)],
        key=lambda j: (
            -(j.get("fit_score_numeric") or 0) * lane_mult(j),
            -({"High": 3, "Medium": 2, "Low": 1}.get(j.get("urgency", ""), 0)),
        ),
    )
    _rq_total = len(_rq_queue)

    if _rq_total == 0:
        st.success("All caught up no Found jobs left to review!", icon="✅")
        st.info(
            "New jobs appear here after the nightly pipeline runs. "
            "Check the Pipeline page to run a fresh scrape."
        )
        st.stop()

    # Session state: current card index + session tally
    if "_rq_idx" not in st.session_state:
        st.session_state["_rq_idx"] = 0
    if "_rq_session_acted" not in st.session_state:
        st.session_state["_rq_session_acted"] = 0

    _rq_idx = min(int(st.session_state["_rq_idx"]), _rq_total - 1)

    # Progress bar
    _rq_pct = _rq_idx / _rq_total if _rq_total else 1.0
    _rq_h1, _rq_h2 = st.columns([5, 1])
    _rq_h1.progress(
        _rq_pct,
        text=f"Card {_rq_idx + 1} of {_rq_total} · {_rq_total - _rq_idx} remaining",
    )
    _rq_h2.metric("Actioned today", st.session_state["_rq_session_acted"])
    st.markdown("")

    # Current card
    _rq_job       = _rq_queue[_rq_idx]
    _rq_score_num = _rq_job.get("fit_score_numeric") or 0
    _rq_score_txt = _rq_job.get("fit_score") or "n/a"
    _rq_urgency   = _rq_job.get("urgency") or "n/a"
    _rq_tier      = _rq_job.get("tier")
    _rq_level     = _rq_job.get("level") or "n/a"
    _rq_sector    = _rq_job.get("sector") or "n/a"
    _rq_comp      = _rq_job.get("expected_comp_band_cad") or ""
    _rq_kw        = _rq_job.get("keywords") or []
    _rq_fit_notes = _rq_job.get("fit_notes") or ""
    _rq_next_act  = _rq_job.get("next_action") or ""
    _rq_osfi      = _rq_job.get("osfi_hook") or ""
    _rq_url       = _rq_job.get("url") or _rq_job.get("portal_url") or ""
    _rq_job_id    = _rq_job.get("id", "")

    _rq_score_color = {"5": "#6366f1", "4": "#10b981", "3": "#f59e0b"}.get(
        str(int(_rq_score_num)), "#94a3b8"
    )
    _rq_urg_color = URGENCY_COLORS.get(_rq_urgency, _C_SLATE)

    with st.container(border=True):
        # Title row
        _rq_t1, _rq_t2 = st.columns([5, 1])
        with _rq_t1:
            st.markdown(
                f"### {_rq_job.get('company', 'Unknown')} "
                f"— {_rq_job.get('title', 'Unknown role')}"
            )
        with _rq_t2:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;"
                f"background:{_rq_score_color}22;border:2px solid {_rq_score_color};"
                f"border-radius:10px;'>"
                f"<div style='font-size:22px;font-weight:700;color:{_rq_score_color}'>"
                f"{'&#11088;' * int(_rq_score_num)}</div>"
                f"<div style='font-size:11px;color:{_rq_score_color};font-weight:600'>"
                f"Fit {int(_rq_score_num)}/5 · {_rq_score_txt}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Tag row — badge every boosted PRIMARY lane (ALM/VAL/VEN/QUANT).
        _rq_tags = []
        _rq_pv = (_rq_job.get("primary_variant") or "").upper()
        if _rq_pv in LANE_MULTIPLIERS:
            _rq_lane_color = LANE_COLORS.get(_rq_pv, _C_INDIGO)
            _rq_tags.append(
                f"<span style='color:{_rq_lane_color};font-weight:700'>"
                f"{_rq_pv} {LANE_MULTIPLIERS[_rq_pv]}×</span>"
            )
        if _rq_tier:
            _rq_tags.append(f"\U0001f3c5 Tier {_rq_tier}")
        _rq_tags.append(f"\U0001f4c2 {_rq_sector}")
        _rq_tags.append(f"\U0001f464 {_rq_level}")
        _rq_tags.append(
            f"<span style='color:{_rq_urg_color};font-weight:600'>"
            f"⚡ {_rq_urgency} urgency</span>"
        )
        if _rq_comp:
            _rq_tags.append(f"\U0001f4b0 {_rq_comp}")
        st.markdown("  ·  ".join(_rq_tags), unsafe_allow_html=True)

        # Bridge-from-stack — one-line "why this fits YOU" accelerator
        _rq_bridge = extract_bridge(_rq_job)
        if _rq_bridge:
            st.markdown(
                f"<div style='margin:6px 0 10px 0;padding:6px 12px;"
                f"background:#6366f10d;border-left:3px solid #6366f1;"
                f"border-radius:0 6px 6px 0;font-size:0.85em;"
                f"color:#4f46e5'>"
                f"\U0001f517 <b>Bridge:</b> {_rq_bridge}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("")

        # Body columns
        _rq_b1, _rq_b2 = st.columns([3, 2])
        with _rq_b1:
            if _rq_fit_notes:
                st.markdown("**\U0001f4dd Fit notes**")
                _preview = _rq_fit_notes[:500]
                st.markdown(_preview + (" ..." if len(_rq_fit_notes) > 500 else ""))
                if len(_rq_fit_notes) > 500:
                    with st.expander("Read full fit notes"):
                        st.markdown(_rq_fit_notes)
            if _rq_osfi:
                with st.expander("\U0001f4dc Regulatory hook", expanded=False):
                    st.caption(_rq_osfi)

        with _rq_b2:
            if _rq_kw:
                st.markdown("**\U0001f3f7 Keywords**")
                _kw_html = " ".join(
                    f"<span style='display:inline-block;margin:2px;padding:2px 8px;"
                    f"background:#6366f122;border:1px solid #6366f144;"
                    f"border-radius:12px;font-size:12px'>{kw}</span>"
                    for kw in _rq_kw[:12]
                )
                st.markdown(_kw_html, unsafe_allow_html=True)
                if len(_rq_kw) > 12:
                    st.caption(f"... +{len(_rq_kw) - 12} more")
            if _rq_next_act:
                st.markdown("")
                st.markdown("**\U0001f3af Suggested next action**")
                _trunc = _rq_next_act[:280] + (" ..." if len(_rq_next_act) > 280 else "")
                st.info(_trunc, icon="\U0001f4a1")

        st.markdown("")
        st.markdown("---")

        # Tailored docs badge on Review Queue card
        _rq_docs = _find_tailor_docs(_rq_job)
        if _rq_docs:
            with st.expander(f"📄 Tailored docs ({len(_rq_docs)}) — preview"):
                for _rdoc in _rq_docs:
                    st.caption(f"**{_rdoc.name}**")
                    _rt = _rdoc.read_text(encoding="utf-8", errors="replace")
                    _rt_suffix = " *(truncated)*" if len(_rt) > 2000 else ""
                    st.markdown(_rt[:2000] + _rt_suffix)
                    st.markdown("---")

        # Action buttons
        _rq_a1, _rq_a2, _rq_a3, _rq_a4, _rq_a5 = st.columns([2, 2, 2, 2, 1])

        def _rq_apply_action(new_status, new_urgency=None):
            # Phase 3D race fix: route through mutate_json so this write
            # serializes against auto_promote and any other concurrent
            # tracker writer. Previously, the naked json.loads/save_tracker
            # pair could interleave with auto_promote's mutate_json and
            # silently drop one side's edits.
            from safe_json import mutate_json as _mj  # noqa: WPS433
            from automation import tracker_ops as _tops  # noqa: WPS433

            def _mut(t):
                if new_status:
                    try:
                        _tops.set_status(t, _rq_job_id, new_status)
                    except KeyError:
                        return t  # job missing — caller already moved on
                if new_urgency:
                    job = _tops.find_job(t, _rq_job_id)
                    if job is not None:
                        job["urgency"] = new_urgency
                return t

            _mj(TRACKER, _mut, default={"jobs": [], "meta": {}})
            load_tracker.clear()
            # Double-skip fix: an actioned card flips off status=="Found" and
            # drops out of the re-filtered queue on rerun, so the NEXT card
            # slides into this same index automatically. Do NOT advance
            # _rq_idx here — only the pure Skip button advances (its card
            # stays in the queue). The clamp at the top of the page handles
            # the last-card case.
            st.session_state["_rq_session_acted"] = (
                st.session_state.get("_rq_session_acted", 0) + 1
            )

        if _rq_a1.button(
            "\U0001f4cc Watch", width='stretch',
            help="Move to Watch - monitor without committing to apply"
        ):
            _rq_apply_action("Watch")
            st.rerun()

        if _rq_a2.button(
            "✅ Apply", type="primary", width='stretch',
            help="Record application — sets date_applied and seeds follow-up schedule"
        ):
            st.session_state["_rq_apply_open"] = _rq_job_id
            st.rerun()

        if _rq_a3.button(
            "❌ Expire", width='stretch',
            help="Mark as Expired - not pursuing"
        ):
            _rq_apply_action("Expired")
            st.rerun()

        if _rq_url:
            if _rq_url:
                _rq_a4.link_button("🔗 Open JD", _rq_url, width='stretch')

        if _rq_a5.button("⏭", width='stretch', help="Skip - come back later",
                         disabled=(_rq_idx >= _rq_total - 1)):
            st.session_state["_rq_idx"] = _rq_idx + 1
            st.rerun()

    # Phase 3D — secondary action row: Archive (per-row button) + More popover
    # (mute-sector / mute-company). Per design doc § "UI hygiene corrections":
    # Archive is its own button, NOT inside the More menu (single entry point).
    _rq_b1, _rq_b2, _rq_b_spacer = st.columns([2, 2, 6])
    if _rq_b1.button(
        "🚫 Archive", width='stretch', key=f"_rq_archive_{_rq_job_id}",
        help="Hide this job from Review Queue + Today's brief + Kanban "
             "active view. URL still blocks re-promotion. Restore later "
             "from the Archived expander.",
    ):
        from safe_json import mutate_json as _mj  # noqa: WPS433
        from automation import tracker_ops as _tops  # noqa: WPS433
        try:
            _mj(TRACKER, lambda t: _tops.archive(t, _rq_job_id, "manual_review_queue"),
                default={"jobs": [], "meta": {}})
            load_tracker.clear()
            # Double-skip fix: archived card drops out of the queue on rerun,
            # so the next card takes this index — don't advance _rq_idx.
            st.session_state["_rq_session_acted"] = (
                st.session_state.get("_rq_session_acted", 0) + 1
            )
            st.toast(
                f"🚫 Archived {_rq_job.get('company') or '?'} · {_rq_job.get('title') or '?'}",
                icon="📁",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Archive failed: {exc}")
        st.rerun()

    with _rq_b2.popover("⋯ More options", use_container_width=True):
        st.caption(
            "Suppress an entire sector or company so future scoring + "
            "promote runs skip them. The current job is auto-archived "
            "on confirm."
        )
        _mute_sector = _rq_job.get("sector") or ""
        _mute_company = _rq_job.get("company") or ""
        if _mute_sector:
            if st.button(
                f"🔇 Mute sector  '{_mute_sector}'",
                key=f"_rq_mute_sec_{_rq_job_id}",
                width='stretch',
            ):
                st.session_state["_rq_mute_open"] = {
                    "job_id": _rq_job_id,
                    "scope": "sector",
                    "name": _mute_sector,
                }
                st.rerun()
        else:
            st.caption("_(no sector tag on this row — mute by company instead)_")
        if _mute_company:
            if st.button(
                f"🔇 Mute company '{_mute_company}'",
                key=f"_rq_mute_co_{_rq_job_id}",
                width='stretch',
            ):
                st.session_state["_rq_mute_open"] = {
                    "job_id": _rq_job_id,
                    "scope": "company",
                    "name": _mute_company,
                }
                st.rerun()

    # Inline Apply form — shown when user clicks Apply on a card
    if st.session_state.get("_rq_apply_open") == _rq_job_id:
        with st.container(border=True):
            st.markdown(f"#### ✅ Confirm application — {_rq_job.get('company')} · {_rq_job.get('title')}")
            with st.form(key=f"rq_apply_form_{_rq_job_id}"):
                # Job-id-scoped widget keys (mirrors the Mute form) so the
                # date/channel/notes a user enters for one card never bleed
                # into the next card's Apply form across reruns.
                _ap_col1, _ap_col2 = st.columns(2)
                _ap_date = _ap_col1.date_input(
                    "Date applied", value=date.today(), help="When did you submit the application?",
                    key=f"_rq_ap_date_{_rq_job_id}",
                )
                _ap_channel = _ap_col2.selectbox(
                    "Applied via", ["Company portal", "LinkedIn", "Email", "Referral", "Recruiter", "Other"],
                    key=f"_rq_ap_channel_{_rq_job_id}",
                )
                _ap_notes = st.text_area(
                    "Notes (optional)", placeholder="E.g. referral from Jane, used tailored resume v2, ...",
                    height=80, key=f"_rq_ap_notes_{_rq_job_id}",
                )
                _ap_tailor = st.checkbox(
                    "🤖 Launch jd_tailor in background (tailors resume + cover letter)",
                    value=False,
                    help="Requires API key. Runs jd_tailor.py for this job ID.",
                    key=f"_rq_ap_tailor_{_rq_job_id}",
                )
                _ap_c1, _ap_c2 = st.columns(2)
                _ap_submit = _ap_c1.form_submit_button("✅ Confirm application", type="primary", width='stretch')
                _ap_cancel = _ap_c2.form_submit_button("Cancel", width='stretch')

            if _ap_submit:
                # Phase 3D race fix: serialize against auto_promote.
                from safe_json import mutate_json as _mj  # noqa: WPS433
                from automation import tracker_ops as _tops  # noqa: WPS433
                _log_entry = {
                    "date": _ap_date.isoformat(),
                    "type": "applied",
                    "channel": _ap_channel,
                    "notes": _ap_notes or "",
                }

                def _apply_mut(t):
                    job = _tops.find_job(t, _rq_job_id)
                    if job is None:
                        return t
                    job["status"] = "Applied"
                    seed_followup(job, applied_on=_ap_date)
                    if not isinstance(job.get("outreach_log"), list):
                        job["outreach_log"] = []
                    job["outreach_log"].append(_log_entry)
                    return t

                _mj(TRACKER, _apply_mut, default={"jobs": [], "meta": {}})
                load_tracker.clear()
                if _ap_tailor and _rq_job_id and api_key.is_key_valid():
                    _tailor_cmd = [sys.executable,
                                   str(ROOT / "automation" / "resume_agent.py"),
                                   "--job-id", _rq_job_id, "--tier",
                                   _resume_tier()]
                    scan_runner.start_run(f"resume_{_rq_job_id}", _tailor_cmd)
                    st.toast(f"📄 Resume generation launched for {_rq_job_id}",
                             icon="🚀")
                del st.session_state["_rq_apply_open"]
                # Double-skip fix: the now-Applied card drops out of the
                # Found queue on rerun; the next card slides into this index.
                st.session_state["_rq_session_acted"] = st.session_state.get("_rq_session_acted", 0) + 1
                st.toast(f"✅ Application recorded for {_rq_job.get('company')}!", icon="📨")
                st.rerun()

            if _ap_cancel:
                del st.session_state["_rq_apply_open"]
                st.rerun()

    # Phase 3D — Mute inline confirm form (mirrors the Apply form pattern).
    # Two-write protocol per design doc § Cluster D:
    #   1. Write the suppression FIRST (the higher-signal, less-frequently-
    #      corrected write — lift on regret is one click).
    #   2. Attempt archive SECOND. On failure → queue to
    #      suppressions_pending_archives.jsonl + yellow toast — don't roll
    #      back the suppression.
    _mute_open = st.session_state.get("_rq_mute_open")
    if isinstance(_mute_open, dict) and _mute_open.get("job_id") == _rq_job_id:
        _m_scope = _mute_open.get("scope", "sector")
        _m_name = _mute_open.get("name", "")
        with st.container(border=True):
            st.markdown(
                f"#### 🔇 Mute {_m_scope} — {_m_name!r}"
            )
            st.caption(
                "Future scoring + promote runs will skip this scope until the "
                "expiry date. The current job is auto-archived on confirm so "
                "it disappears from your queue immediately."
            )
            with st.form(key=f"rq_mute_form_{_rq_job_id}"):
                _mc1, _mc2 = st.columns(2)
                _m_dur = _mc1.selectbox(
                    "Duration", ("30d", "60d", "90d", "permanent"),
                    index=1, key=f"_rq_mute_dur_{_rq_job_id}",
                )
                _m_reason = _mc2.text_input(
                    "Reason (visible in audit log)",
                    placeholder="1 interview / 14 apps in 8 weeks",
                    key=f"_rq_mute_reason_{_rq_job_id}",
                )
                _mb1, _mb2 = st.columns(2)
                _m_submit = _mb1.form_submit_button(
                    f"🔇 Mute & archive", type="primary", width='stretch',
                )
                _m_cancel = _mb2.form_submit_button("Cancel", width='stretch')

            if _m_submit:
                _ttl_days = None if _m_dur == "permanent" else int(_m_dur.rstrip("d"))
                ok, err, until, canon = pipeline_state.validate_suppression_form(
                    scope=_m_scope, name=_m_name,
                    ttl_days=_ttl_days, reason=_m_reason,
                )
                if not ok:
                    st.error(err, icon="❌")
                else:
                    # Step 1: write the suppression. Direct in-process call
                    # — same lock the CLI uses, milliseconds.
                    suppression_ok = False
                    archive_ok = False
                    try:
                        from automation import suppressions as _supp  # noqa: WPS433
                        if _m_scope == "sector":
                            _supp.add_sector(canon, until,
                                              _m_reason or "muted from Review Queue")
                        else:
                            _supp.add_company(canon, until,
                                               _m_reason or "muted from Review Queue")
                        suppression_ok = True
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Mute failed: {exc}", icon="❌")

                    # Step 2: attempt archive ONLY if suppression succeeded.
                    if suppression_ok:
                        from safe_json import mutate_json as _mj2  # noqa: WPS433
                        from automation import tracker_ops as _tops2  # noqa: WPS433
                        try:
                            _mj2(
                                TRACKER,
                                lambda t: _tops2.archive(
                                    t, _rq_job_id,
                                    f"muted_{_m_scope}_{canon}",
                                ),
                                default={"jobs": [], "meta": {}},
                            )
                            load_tracker.clear()
                            archive_ok = True
                        except Exception as exc:  # noqa: BLE001
                            # Don't roll back the suppression — it's the
                            # load-bearing write. Queue the archive for
                            # retry; surface a yellow toast.
                            try:
                                _supp.queue_pending_archive(
                                    _rq_job_id,
                                    f"mute_partial_failure: {exc}",
                                )
                            except Exception:
                                pass
                            st.warning(
                                f"Mute saved; archive deferred — retry from "
                                f"the banner at the top of this page. ({exc})",
                                icon="⚠️",
                            )

                        if archive_ok:
                            until_msg = "permanent" if until is None else \
                                        f"until {until.isoformat()}"
                            # Toast carries an [Undo] in the success-flow
                            # state so the next render shows it as a chip
                            # at the top of the page.
                            st.toast(
                                f"🔇 Muted {_m_scope} {canon!r} ({until_msg}); "
                                f"job archived",
                                icon="🔇",
                            )
                            st.session_state["_rq_mute_undo"] = {
                                "scope": _m_scope, "name": canon,
                                "ts": datetime.now().isoformat(timespec="seconds"),
                            }
                            # Double-skip fix: the auto-archived card drops
                            # out of the queue on rerun; next card takes this
                            # index — don't advance _rq_idx.
                            st.session_state["_rq_session_acted"] = (
                                st.session_state.get("_rq_session_acted", 0) + 1
                            )
                    del st.session_state["_rq_mute_open"]
                    st.rerun()

            if _m_cancel:
                del st.session_state["_rq_mute_open"]
                st.rerun()

        # Navigation strip
    st.markdown("")
    _rq_n1, _rq_n2, _rq_n3 = st.columns([1, 3, 1])
    if _rq_n1.button("◄ Prev", disabled=(_rq_idx == 0)):
        st.session_state["_rq_idx"] = max(0, _rq_idx - 1)
        st.rerun()
    _rq_n2.caption(
        f"**{_rq_job.get('company')}** · {_rq_job.get('title')} · "
        f"ID `{_rq_job_id}` · found {_rq_job.get('date_found', 'n/a')}"
    )
    if _rq_n3.button("Next ►", disabled=(_rq_idx >= _rq_total - 1)):
        st.session_state["_rq_idx"] = min(_rq_total - 1, _rq_idx + 1)
        st.rerun()

    with st.expander("⚙️ Queue options"):
        st.caption(
            f"Queue contains **{_rq_total}** Found jobs sorted by fit score then urgency."
        )
        if st.button("\U0001f504 Restart from card 1"):
            st.session_state["_rq_idx"] = 0
            st.session_state["_rq_session_acted"] = 0
            st.rerun()
        st.caption(
            "Actioning a card (Watch / Shortlist / Expire) saves immediately to the tracker. "
            "Skip leaves the job unchanged for next session."
        )

    # Phase 3D — Archived rows expander. Lists rows where archived=True,
    # newest first. Each gets a per-row Restore button so the user can
    # recover from a misclick without leaving the page.
    _archived_jobs = [j for j in _rq_jobs if j.get("archived", False)]
    if _archived_jobs:
        # Sort by archived_at desc (most recent first), falling back to id.
        _archived_jobs.sort(
            key=lambda j: j.get("archived_at") or "", reverse=True,
        )
        with st.expander(f"🗂 Archived ({len(_archived_jobs)})", expanded=False):
            st.caption(
                "Archived rows are hidden from Review Queue, Today's brief, "
                "and Kanban active counts. The URL still blocks "
                "re-promotion. Restore brings the row back to active state."
            )
            # Phase 5 — context-aware Restore. If the row was archived as
            # part of a still-active mute, we surface a "(still muted ⚠)"
            # label and an inline confirm that lets the user lift the mute
            # in the same click. Avoids the "I clicked Restore and nothing
            # happened" trap (the row would just re-archive on next scan).
            try:
                from automation import suppressions as _rq_supp_mod  # noqa: WPS433
                _rq_supp_state = _rq_supp_mod.load_active()
            except Exception:  # noqa: BLE001
                _rq_supp_state = {"sectors": [], "companies": []}

            def _rq_active_mute_for(_reason: str) -> dict | None:
                """Return the live entry if this archive_reason still ties
                to an active mute, else None."""
                parsed = pipeline_state.parse_archive_reason(_reason)
                if not parsed:
                    return None
                _sc, _nm = parsed
                try:
                    if _sc == "sector":
                        from automation import sectors as _rq_sec  # noqa: WPS433
                        _ck_raw = _rq_sec.canonical(_nm)
                        _ck = _ck_raw.lower() if _ck_raw else _nm.lower()
                    else:
                        from automation import brand_aliases as _rq_ba  # noqa: WPS433
                        _ck = _rq_ba.canonical_brand(_nm).lower()
                except Exception:  # noqa: BLE001
                    _ck = _nm.lower()
                _scope_key = "sectors" if _sc == "sector" else "companies"
                for _entry in _rq_supp_state.get(_scope_key, []) or []:
                    if _entry.get("canonical_key") == _ck:
                        return _entry
                return None

            from datetime import date as _rq_date  # noqa: WPS433
            _rq_today = _rq_date.today()

            for _aj in _archived_jobs[:20]:
                _aj_id = _aj.get("id", "?")
                _ar_reason = _aj.get("archive_reason", "") or ""
                _live_mute = _rq_active_mute_for(_ar_reason)
                _ac1, _ac2, _ac3 = st.columns([5, 2, 1])
                _ac1.markdown(
                    f"**{_aj.get('company') or '?'}** — "
                    f"{_aj.get('title') or '?'} "
                    f"<span style='color:#94a3b8;font-size:11px'>"
                    f"({_aj.get('status') or '?'})</span>",
                    unsafe_allow_html=True,
                )
                _ac2.caption(
                    f"archived {_aj.get('archived_at', '?')[:10]} · "
                    f"{_ar_reason[:40]}"
                )
                _btn_label = (
                    "↩ Restore (still muted ⚠)" if _live_mute
                    else "↩ Restore"
                )
                if _ac3.button(_btn_label, key=f"_rq_restore_{_aj_id}"):
                    if _live_mute:
                        # Defer to inline confirm; let the user decide
                        # whether to also lift the mute.
                        st.session_state["_rq_restore_open"] = _aj_id
                        st.rerun()
                    else:
                        from safe_json import mutate_json as _mj_re  # noqa: WPS433
                        from automation import tracker_ops as _tops_re  # noqa: WPS433
                        try:
                            _mj_re(TRACKER,
                                    lambda t, _i=_aj_id:
                                        _tops_re.restore(t, _i),
                                    default={"jobs": [], "meta": {}})
                            load_tracker.clear()
                            st.toast(
                                f"↩ Restored {_aj.get('company') or '?'}",
                                icon="✅",
                            )
                        except Exception as _exc:  # noqa: BLE001
                            st.error(f"Restore failed: {_exc}")
                        st.rerun()

                # Inline confirm for "still muted" rows.
                if (st.session_state.get("_rq_restore_open") == _aj_id
                        and _live_mute):
                    parsed = pipeline_state.parse_archive_reason(_ar_reason)
                    _cf_scope, _cf_name = parsed if parsed else ("?", "?")
                    _cf_until = _live_mute.get("until")
                    _cf_until_lbl = pipeline_state.format_until_label(
                        _cf_until, _rq_today,
                    )
                    with st.container(border=True):
                        st.caption(
                            f"This row was archived as part of muting "
                            f"{_cf_scope} {_cf_name!r}, which is still "
                            f"active ({_cf_until_lbl}). Restore alone will "
                            f"bring this row back; future scans will still "
                            f"skip {_cf_scope} {_cf_name!r}."
                        )
                        _cf_lift = st.checkbox(
                            f"Also lift the {_cf_scope} mute on "
                            f"'{_cf_name}'",
                            value=False,
                            key=f"_rq_restore_lift_{_aj_id}",
                        )
                        _cf_b1, _cf_b2 = st.columns(2)
                        _cf_go = _cf_b1.button(
                            "↩ Restore", type="primary",
                            width='stretch',
                            key=f"_rq_restore_go_{_aj_id}",
                        )
                        _cf_cancel = _cf_b2.button(
                            "Cancel", width='stretch',
                            key=f"_rq_restore_cancel_{_aj_id}",
                        )
                        if _cf_go:
                            from safe_json import mutate_json as _mj_re  # noqa: WPS433
                            from automation import tracker_ops as _tops_re  # noqa: WPS433
                            _restore_ok = False
                            try:
                                _mj_re(TRACKER,
                                        lambda t, _i=_aj_id:
                                            _tops_re.restore(t, _i),
                                        default={"jobs": [], "meta": {}})
                                load_tracker.clear()
                                _restore_ok = True
                            except Exception as _exc:  # noqa: BLE001
                                st.error(f"Restore failed: {_exc}")
                            if _restore_ok and _cf_lift:
                                try:
                                    _rq_supp_mod.lift(_cf_scope, _cf_name)
                                    st.toast(
                                        f"↩ Restored & lifted "
                                        f"{_cf_scope} mute on "
                                        f"{_cf_name!r}", icon="🔓",
                                    )
                                except Exception as _exc:  # noqa: BLE001
                                    st.warning(
                                        f"Restored, but lift failed: "
                                        f"{_exc}", icon="⚠️",
                                    )
                            elif _restore_ok:
                                st.toast(
                                    f"↩ Restored {_aj.get('company') or '?'}"
                                    f" (mute remains active)",
                                    icon="✅",
                                )
                            st.session_state.pop("_rq_restore_open", None)
                            st.rerun()
                        if _cf_cancel:
                            st.session_state.pop("_rq_restore_open", None)
                            st.rerun()
            if len(_archived_jobs) > 20:
                st.caption(f"_(showing 20 of {len(_archived_jobs)} — older "
                            "rows accessible via Jobs Kanban inspector)_")

# ===========================================================================
# FOLLOW-UPS PAGE
# Triage applied jobs by follow-up due date — overdue, today, this week.
# ===========================================================================
elif page == "🔔 Follow-ups":
    st.title("🔔 Follow-ups")
    st.caption(
        "Track every application after you hit submit. "
        "Log each outreach touch so the cadence advances automatically. "
        "Overdue items are sorted most-overdue first."
    )

    _fu_all   = load_tracker()
    _fu_jobs  = _fu_all.get("jobs", [])
    _fu_bkts  = followup_buckets(_fu_jobs)

    _fu_overdue      = _fu_bkts["overdue"]        # [(days_overdue, job), ...]
    _fu_due_today    = _fu_bkts["due_today"]       # [job, ...]
    _fu_this_week    = _fu_bkts["due_this_week"]   # [(days_until, job), ...]
    _fu_upcoming     = _fu_bkts["upcoming"]         # [(days_until, job), ...]
    _fu_no_sched     = _fu_bkts["no_schedule"]     # [job, ...]

    _fu_total_due = len(_fu_overdue) + len(_fu_due_today)

    # KPI row
    _fk1, _fk2, _fk3, _fk4 = st.columns(4)
    _fk1.metric("Overdue",     len(_fu_overdue),   delta="past due" if _fu_overdue else None, delta_color="inverse")
    _fk2.metric("Due today",   len(_fu_due_today))
    _fk3.metric("This week",   len(_fu_this_week))
    _fk4.metric("No schedule", len(_fu_no_sched),  help="Applied but follow-up date not set")

    if _fu_total_due == 0 and not _fu_no_sched:
        st.success("🎉 All follow-ups are current — nothing overdue or due today!", icon="✅")

    st.markdown("---")

    def _fu_render_card(job, days_label, border_color):
        """Render a single follow-up card with log-outreach action."""
        _fj_job_obj = job  # keep full dict for AI helpers
        _fj_id      = job.get("id", "")
        _fj_co      = job.get("company", "?")
        _fj_title   = job.get("title", "?")
        _fj_applied = job.get("date_applied", "?")
        _fj_sched   = job.get("followup_schedule") or {}
        _fj_next    = _fj_sched.get("next_due", "?")
        _fj_log     = job.get("outreach_log") or []
        _fj_url     = job.get("url") or job.get("portal_url") or ""
        _fj_contact = (job.get("contact") or {})
        _fj_rec     = _fj_contact.get("recruiter_name") or ""

        with st.container(border=True):
            _fc1, _fc2 = st.columns([5, 1])
            with _fc1:
                st.markdown(
                    f"<span style='border-left:4px solid {border_color};"
                    f"padding-left:8px'>"
                    f"**{_fj_co}** — {_fj_title}</span>",
                    unsafe_allow_html=True
                )
                _fu_meta = f"Applied {_fj_applied}"
                if _fj_rec:
                    _fu_meta += f" · Recruiter: {_fj_rec}"
                st.caption(_fu_meta)

                # Cadence context — "Touch N of [3,10,21]d · last touch Xd · type"
                _fj_cadence = _fj_sched.get("cadence_days") or [3, 10, 21]
                _fj_touch_n = len(_fj_log)
                _fj_cadence_str = ",".join(str(d) for d in _fj_cadence)
                _cadence_parts = [f"Touch {_fj_touch_n} of [{_fj_cadence_str}]d cadence"]
                if _fj_log:
                    _last_entry = _fj_log[-1]
                    _last_d = parse_date(_last_entry.get("date"))
                    if _last_d:
                        _since = (date.today() - _last_d).days
                        _cadence_parts.append(f"last touch {_since}d ago")
                    _last_type = _last_entry.get("type", "")
                    if _last_type:
                        _cadence_parts.append(f"prior: {_last_type.replace('_', ' ')}")
                st.caption(" · ".join(_cadence_parts))

            with _fc2:
                st.markdown(
                    f"<div style='text-align:center;padding:6px;"
                    f"background:{border_color}22;border:1px solid {border_color};"
                    f"border-radius:8px;font-size:11px;color:{border_color};"
                    f"font-weight:700'>{days_label}</div>",
                    unsafe_allow_html=True
                )

            # Outreach history (compact)
            if _fj_log:
                with st.expander(f"📋 {len(_fj_log)} outreach touch{'es' if len(_fj_log)!=1 else ''} logged", expanded=False):
                    for _entry in reversed(_fj_log[-5:]):
                        _etype = _entry.get("type", "touch")
                        _edate = _entry.get("date", "?")
                        _enote = _entry.get("notes", "")
                        st.caption(f"**{_edate}** · {_etype}" + (f" — {_enote[:120]}" if _enote else ""))

            # Action row
            _fa1, _fa2, _fa3, _fa4 = st.columns([3, 3, 3, 2])

            # AI email drafter
            with _fa1.expander("✉️ Draft email"):
                _draft_touch = len(_fj_log) + 1
                _draft_key   = f"draft_{_fj_id}_{_draft_touch}"
                _tone_options = ["Standard follow-up", "Warm / brief nudge", "Value-add angle"]
                _tone_default = min(_draft_touch - 1, 2)
                _draft_type  = st.selectbox(
                    "Tone", _tone_options,
                    index=_tone_default,
                    key=f"dt_{_fj_id}"
                )
                if st.button("✨ Generate draft", key=f"gen_{_fj_id}",
                             disabled=not api_key.is_key_valid(),
                             help="Uses Claude Haiku (~$0.001)"):
                    with st.spinner("Drafting…"):
                        _prompt = _email_draft_prompt(_fj_job_obj, _draft_touch)
                        _generated = _ai_draft(_draft_key + _draft_type, _prompt)
                    st.session_state[_draft_key] = _generated
                _draft_text = st.session_state.get(_draft_key, "")
                if _draft_text:
                    _editable = st.text_area(
                        "Edit before sending", _draft_text,
                        height=220, key=f"dedit_{_fj_id}"
                    )
                    if st.button("💾 Save to outreach log", key=f"dsave_{_fj_id}"):
                        _td_d = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _jd2 in _td_d.get("jobs", []):
                            if _jd2.get("id") == _fj_id:
                                if not isinstance(_jd2.get("outreach_log"), list):
                                    _jd2["outreach_log"] = []
                                _jd2["outreach_log"].append({
                                    "date": date.today().isoformat(),
                                    "type": "email_draft",
                                    "notes": _editable[:500],
                                })
                                advance_followup(_jd2)
                                break
                        save_tracker(_td_d)
                        del st.session_state[_draft_key]
                        st.toast("💾 Draft saved and follow-up advanced!", icon="✅")
                        st.rerun()
                elif not api_key.is_key_valid():
                    st.caption("Set API key in the sidebar to enable AI drafts.")

            # Log outreach expander
            with _fa2.expander("✅ Log outreach"):
                with st.form(key=f"fu_log_{_fj_id}_{_fj_next}"):
                    _log_date  = st.date_input("Date", value=date.today(), key=f"fu_d_{_fj_id}")
                    _log_type  = st.selectbox("Type", ["email", "linkedin_message", "phone", "referral_nudge", "other"], key=f"fu_t_{_fj_id}")
                    _log_notes = st.text_input("Notes", placeholder="Brief message sent, follow-up in X days...", key=f"fu_n_{_fj_id}")
                    if st.form_submit_button("Save", type="primary"):
                        _td2 = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _j3 in _td2.get("jobs", []):
                            if _j3.get("id") == _fj_id:
                                if not isinstance(_j3.get("outreach_log"), list):
                                    _j3["outreach_log"] = []
                                _j3["outreach_log"].append({
                                    "date":  _log_date.isoformat(),
                                    "type":  _log_type,
                                    "notes": _log_notes,
                                })
                                advance_followup(_j3, _log_date)
                                break
                        save_tracker(_td2)
                        st.toast(f"✅ Outreach logged for {_fj_co}!", icon="📨")
                        st.rerun()

            # Got response
            with _fa3.expander("📨 Response"):
                with st.form(key=f"fu_resp_{_fj_id}"):
                    # Build progression options aligned with the tracker's actual status_enum.
                    # Filter out non-progression statuses (Found/Watch/Applied/Hired/Expired)
                    # and surface the rest with friendly labels.
                    _resp_enum = _fu_all.get("meta", {}).get("status_enum", [])
                    _resp_label_to_enum = [
                        ("Recruiter screen scheduled", "Recruiter_Screen"),
                        ("Phone screen scheduled",     "Phone_Screen"),
                        ("Take-home received",         "Take_Home"),
                        ("Onsite scheduled",           "Onsite"),
                        ("Interview scheduled",        "Onsite"),  # Interview not in enum; Onsite is closest active-interview parent
                        ("Offer received",             "Offer"),
                        ("Rejected",                   "Rejected"),
                        ("Ghosted / withdrawn",        "Withdrawn"),
                    ]
                    _status_map = {}
                    _resp_options = []
                    for _lbl, _target in _resp_label_to_enum:
                        # Use the target if it's in the enum; otherwise fall back to a sensible parent.
                        if _target in _resp_enum:
                            _status_map[_lbl] = _target
                        elif "Onsite" in _resp_enum:
                            _status_map[_lbl] = "Onsite"
                        else:
                            _status_map[_lbl] = _target  # last-resort: use the label's intended value as-is
                        _resp_options.append(_lbl)
                    _resp_type = st.selectbox(
                        "Outcome",
                        _resp_options,
                        key=f"fu_r_{_fj_id}"
                    )
                    _resp_note = st.text_input("Notes", key=f"fu_rn_{_fj_id}")
                    if st.form_submit_button("Save", type="primary"):
                        _td3 = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _j4 in _td3.get("jobs", []):
                            if _j4.get("id") == _fj_id:
                                _j4["status"] = _status_map.get(_resp_type, "Watch")
                                if not isinstance(_j4.get("outreach_log"), list):
                                    _j4["outreach_log"] = []
                                _j4["outreach_log"].append({
                                    "date":  date.today().isoformat(),
                                    "type":  "response",
                                    "notes": f"{_resp_type}" + (f" — {_resp_note}" if _resp_note else ""),
                                })
                                # Clear next_due only on terminal stages; otherwise let the cadence continue.
                                if _j4["status"] in ("Rejected", "Offer", "Withdrawn", "Hired"):
                                    _j4.setdefault("followup_schedule", {})["next_due"] = None
                                break
                        save_tracker(_td3)
                        st.toast(f"📨 Response recorded: {_resp_type}", icon="✅")
                        st.rerun()

            if _fj_url:
                with _fa4:
                    st.link_button("🔗 Open JD", _fj_url, width='stretch')

            # Tailored docs — show if jd_tailor has run for this job
            _fj_docs = _find_tailor_docs(job)
            if _fj_docs:
                with st.expander(f"📄 Tailored docs ({len(_fj_docs)})"):
                    for _doc in _fj_docs:
                        st.markdown(f"**{_doc.name}**")
                        _doc_text = _doc.read_text(encoding="utf-8", errors="replace")
                        _trunc_suffix = "\n\n*(truncated)*" if len(_doc_text) > 1500 else ""
                        st.markdown(_doc_text[:1500] + _trunc_suffix)
                        st.markdown("---")

            # Interview prep — available for any applied job, surfaced prominently for Interview status
            _fj_status = job.get("status", "")
            _prep_label = "🎯 Interview prep" if _fj_status == "Interview" else "📋 Prep notes"
            _prep_key   = f"prep_{_fj_id}"
            with st.expander(_prep_label, expanded=(_fj_status == "Interview")):
                if st.button("✨ Generate prep brief", key=f"prepbtn_{_fj_id}",
                             disabled=not api_key.is_key_valid(),
                             help="Uses Claude Haiku. Covers technical Qs, behavioural Qs, selling points."):
                    with st.spinner("Building prep brief…"):
                        _prep_prompt   = _interview_prep_prompt(job)
                        _prep_result   = _ai_draft(_prep_key, _prep_prompt)
                    st.session_state[_prep_key] = _prep_result
                _prep_text = st.session_state.get(_prep_key, "")
                if _prep_text:
                    st.markdown(_prep_text)
                    if st.button("💾 Save to job notes", key=f"prepsave_{_fj_id}"):
                        _td_p = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _jp in _td_p.get("jobs", []):
                            if _jp.get("id") == _fj_id:
                                _existing = (_jp.get("notes") or "")
                                _prep_header = f"### Interview Prep ({date.today().isoformat()})\n\n"
                                _jp["notes"] = _prep_header + _prep_text + "\n\n---\n\n" + _existing
                                break
                        save_tracker(_td_p)
                        st.toast("💾 Prep notes saved to job!", icon="✅")
                        st.rerun()
                elif not api_key.is_key_valid():
                    st.caption("Set API key in sidebar to generate prep notes.")

    # ── OVERDUE ───────────────────────────────────────────────────────────
    if _fu_overdue:
        st.markdown(f"### 🔴 Overdue ({len(_fu_overdue)})")
        for _days_over, _job in _fu_overdue:
            _fu_render_card(_job, f"{_days_over}d overdue", "#ef4444")

    # ── DUE TODAY ─────────────────────────────────────────────────────────
    if _fu_due_today:
        st.markdown(f"### 🟡 Due today ({len(_fu_due_today)})")
        for _job in _fu_due_today:
            _fu_render_card(_job, "Due today", "#f59e0b")

    # ── NO SCHEDULE ───────────────────────────────────────────────────────
    if _fu_no_sched:
        st.markdown(f"### ⚠️ No schedule ({len(_fu_no_sched)})")
        st.caption("These jobs are Applied but have no next follow-up date — seed one now.")
        for _job in _fu_no_sched:
            _fu_render_card(_job, "Needs schedule", "#94a3b8")

    # ── DUE THIS WEEK ─────────────────────────────────────────────────────
    if _fu_this_week:
        with st.expander(f"🟢 Due this week ({len(_fu_this_week)})", expanded=False):
            for _days_left, _job in _fu_this_week:
                _fu_render_card(_job, f"In {_days_left}d", "#10b981")

    # ── UPCOMING ─────────────────────────────────────────────────────────
    if _fu_upcoming:
        with st.expander(f"📅 Upcoming ({len(_fu_upcoming)})", expanded=False):
            for _days_left, _job in _fu_upcoming:
                _fu_render_card(_job, f"In {_days_left}d", "#6366f1")

    if not any([_fu_overdue, _fu_due_today, _fu_no_sched, _fu_this_week, _fu_upcoming]):
        st.info(
            "No applied jobs in the follow-up loop yet. "
            "Use the 📬 Review Queue to triage Found jobs and click ✅ Apply "
            "to start tracking applications."
        )
