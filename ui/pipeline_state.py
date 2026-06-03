"""pipeline_state.py — pure-function banner state machine for the Pipeline page.

Computes a single primary CTA from on-disk artifacts, never from stale
session-state flags. Lives outside `ui/app.py` so it can be unit-tested
without Streamlit. **Stdlib + automation modules only — no streamlit imports.**

The state machine is the priority ladder from `docs/pipeline_redesign.md`
§ "Banner state machine":

    1. SAFETY                 quarantine_ratio > 0.5
    2. ACTIVE                 any active_runs
    3. RECENT                 fail within 30min on bottleneck stage
    4. PROMOTE                promotable_count >= 1
    5. REVIEW                 just scored, 0 promotable, ≥1 verdict
    6. SCORE                  billable + reusable_filtered > 0 AND api_key_valid
    7. REFRESH                max_input_age > 24h
    8. EMPTY                  no worklist
    8.5 SUPPRESS-AWARE-EMPTY  scoring done, every promotable hit a mute
    8.5 SUPPRESS-EXPIRED      a mute lapsed within last 7d
    8.6 SUPPRESS-INVALID      registry contains a sector name not in sectors.KNOWN
    9. DEFAULT                up-to-date

All functions are pure dicts → dicts. The Streamlit caller is responsible
for translating `Banner` into widgets and shelling out actions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Banner / chip data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chip:
    """A small status chip composed onto the banner — never the banner alone.

    Examples: `🔑 API key invalid`, `⚙️ Gmail not connected`, `✅ Promoted 3`.
    Chips never block the primary CTA; they decorate it. See design-doc
    § 'Chips, not states'."""
    icon: str
    label: str
    severity: str = "info"  # one of: info | warn | error | success


@dataclass(frozen=True)
class Banner:
    """The single primary CTA at the top of the Pipeline page.

    `state` is one of the priority-ladder rule names; `cta_label` is what
    the button reads; `cta_action` is a stable string the caller can route
    on (e.g., 'promote' → shell auto_promote.py)."""
    state: str
    icon: str
    headline: str
    cta_label: str | None = None
    cta_action: str | None = None
    detail: str = ""
    severity: str = "info"  # info | warn | error | success
    chips: tuple[Chip, ...] = field(default_factory=tuple)


# Status-pill levels from § "Stage card layout".
PILL_HEALTHY = "🟢"
PILL_STALE = "🟡"
PILL_FAILED = "🔴"
PILL_EMPTY = "⏸"
PILL_REVIEW = "⏵"
PILL_QUARANTINE = "⚠️"


# ---------------------------------------------------------------------------
# State derivation helpers
# ---------------------------------------------------------------------------

def _file_age_h(path: Path) -> float | None:
    """Mtime-based age in hours. None if the file is missing."""
    try:
        if not path.exists():
            return None
        return (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    except OSError:
        return None


def _content_age_h(path: Path) -> float | None:
    """Read the canonical 'when was this run produced' timestamp from inside
    the artifact. Falls back to mtime for legacy artifacts.

    File mtime can lag REAL run time when:
      - a repair script rewrites the file (mtime jumps forward, content stale)
      - a sync tool touches the file (mtime jumps but content unchanged)
    Mirrors the helper in `ui/app.py` so banner ages match card ages.
    """
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _file_age_h(path)
    for key in ("scored_at", "rebuilt_at", "scan_timestamp"):
        v = d.get(key)
        if not v:
            continue
        try:
            ts = datetime.fromisoformat(
                v.replace("Z", "+00:00") if v.endswith("Z") else v
            )
            if ts.tzinfo is None:
                age = (datetime.now() - ts).total_seconds() / 3600
            else:
                from datetime import timezone as _tz
                age = (datetime.now(_tz.utc) - ts).total_seconds() / 3600
            return max(age, 0.0)
        except (ValueError, TypeError):
            continue
    sd = d.get("scan_date")
    if isinstance(sd, str) and len(sd) == 8:
        try:
            ts = datetime.strptime(sd, "%Y%m%d")
            return (datetime.now() - ts).total_seconds() / 3600
        except ValueError:
            pass
    return _file_age_h(path)


def _latest(glob_dir: Path, pattern: str,
            exclude: tuple[str, ...] = ()) -> Path | None:
    if not glob_dir.exists():
        return None
    files = [p for p in glob_dir.glob(pattern)
             if not any(ex in p.name for ex in exclude)]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _safe_load(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tracker_url_set(tracker_path: Path) -> set[str]:
    t = _safe_load(tracker_path) or {}
    out: set[str] = set()
    for j in t.get("jobs", []) or []:
        u = j.get("url")
        if isinstance(u, str) and u:
            out.add(u)
    return out


# ---------------------------------------------------------------------------
# Snapshot — the input to `compute_next_action`
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    """Everything `compute_next_action` reads. Build via `derive_snapshot(...)`
    against real files, or instantiate directly in tests."""
    scrape_age_h: float | None = None
    gmail_age_h: float | None = None
    worklist_total: int = 0
    triage_passed: int = 0
    triage_dropped: int = 0
    billable_count: int = 0
    cached_count: int = 0
    reusable_count: int = 0
    promotable_count: int = 0
    suppressed_promotable_count: int = 0  # would-be-promotable but for a mute
    quarantine_count: int = 0
    recent_promote_count: int = 0
    last_promote_age_h: float | None = None
    scored_age_h: float | None = None
    active_runs: tuple[dict, ...] = field(default_factory=tuple)
    last_failure: dict | None = None  # {"stage", "age_h", "pipeline_id"}
    api_key_valid: bool = True
    gmail_connected: bool = True
    suppression_invalid_names: tuple[str, ...] = field(default_factory=tuple)
    suppression_recently_expired: tuple[dict, ...] = field(default_factory=tuple)


    @property
    def quarantine_ratio(self) -> float:
        denom = self.quarantine_count + self.worklist_total
        return self.quarantine_count / denom if denom else 0.0

    @property
    def freshest_input_age_h(self) -> float | None:
        """Age of the most recently updated input source (min over ages).

        REFRESH fires only when the FRESHEST source is older than 24h —
        i.e., every source is stale. If Gmail just synced an hour ago,
        scrape being 72h old doesn't justify telling the user to refresh."""
        ages = [a for a in (self.scrape_age_h, self.gmail_age_h) if a is not None]
        return min(ages) if ages else None


# ---------------------------------------------------------------------------
# Cross-stage consistency — "does the scored snapshot still match the
# current worklist?". Pairs with fit_scorer._input_breadcrumb, which writes
# the input fingerprint into every output artifact. Lets the UI tell the
# user "scoring is stale relative to triage" — the disconnect that caused
# the 512/739 mismatch in the funnel.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageConsistency:
    """Freshness/consistency of one downstream stage vs the current worklist.

    `is_consistent` is the boolean the UI rendering code branches on:
    True  → stage's headline numbers describe the current worklist
    False → stage's headline numbers describe a previous worklist (or
            the stage was written before breadcrumbs existed and we
            can't prove it's current)."""
    exists: bool = False
    mtime: float | None = None             # epoch seconds, for age calcs
    primary_count: int = 0                  # stage's headline number
    input_sha8: str | None = None           # breadcrumb from the file
    input_rows: int | None = None           # row count it was built against
    is_consistent: bool = False             # input_sha8 == current worklist sha8
    source_path: str = ""                   # filename, for help text


@dataclass(frozen=True)
class PipelineConsistency:
    """Cross-stage consistency view. Computed in ONE pass over disk.

    Every Pipeline-page widget that displays a downstream-stage number
    should read from this — that's how we kill the bug class where two
    widgets render disagreeing numbers because they read different files."""
    worklist_exists: bool = False
    worklist_rows: int = 0
    worklist_sha8: str | None = None
    worklist_mtime: float | None = None
    triage: StageConsistency = field(default_factory=StageConsistency)
    scored: StageConsistency = field(default_factory=StageConsistency)

    @property
    def global_state(self) -> str:
        """One word the banner copy keys off of.

        Values (priority order; first match wins):
          empty             — no worklist (nothing to be consistent with)
          mixed_drift       — BOTH triage AND scoring have breadcrumbs and
                              both drifted (proven mismatch on both sides)
          drift_at_triage   — triage has a breadcrumb that doesn't match;
                              scoring is either absent, consistent, or
                              breadcrumb-less (proven mismatch wins)
          drift_at_scoring  — scoring has a breadcrumb that doesn't match;
                              triage is either absent, consistent, or
                              breadcrumb-less (proven mismatch wins)
          no_breadcrumb     — at least one existing stage lacks a breadcrumb
                              (legacy artifact from before this fix). We
                              CAN'T prove drift, but we also can't claim
                              ✅; banner says "consistency unknown".
          ok                — every existing downstream stage has a
                              breadcrumb AND all match the current worklist.

        Drift beats no_breadcrumb on purpose: if scored.sha is wrong we
        want to TELL the user to re-score, not hand-wave it as legacy."""
        if not self.worklist_exists:
            return "empty"
        # Proven drift — only when the stage has a breadcrumb to compare.
        triage_drifted = (self.triage.exists
                         and self.triage.input_sha8 is not None
                         and not self.triage.is_consistent)
        scored_drifted = (self.scored.exists
                         and self.scored.input_sha8 is not None
                         and not self.scored.is_consistent)
        if triage_drifted and scored_drifted:
            return "mixed_drift"
        if triage_drifted:
            return "drift_at_triage"
        if scored_drifted:
            return "drift_at_scoring"
        # No proven drift. Now check whether anything is breadcrumb-less.
        # Any existing stage without a breadcrumb means we can't honestly
        # paint everything green — surface as no_breadcrumb so the banner
        # tells the user "re-run to enable drift detection."
        triage_unproven = self.triage.exists and self.triage.input_sha8 is None
        scored_unproven = self.scored.exists and self.scored.input_sha8 is None
        if triage_unproven or scored_unproven:
            return "no_breadcrumb"
        # Everything that exists has a breadcrumb and matches.
        return "ok"


def _canonicalize_link(url: str) -> str:
    """Canonical form used for the consistency sha8 — MUST match
    `fit_scorer._canonicalize_url` (the writer side).

    Trying to maintain two independent implementations of "canonical URL"
    is how we got the 7556b1ba ≠ 791ca5b1 bug: a worklist of identical
    row counts hashed to different sha8s because the writer used
    `worklist.norm_url` (which preserves Greenhouse's gh_jid query param)
    and the reader stripped all queries. Single-implementation rule:
    delegate to worklist.norm_url, with the SAME fallback the writer has.

    Imports worklist lazily — automation modules are on sys.path when
    the UI runs (ui/app.py adds them); when run from tests, the
    automation dir is also added. If norm_url is genuinely unavailable
    (extracted to a separate package, etc.), the fallback path matches
    the writer's fallback path; sha8s still agree."""
    if not url:
        return ""
    try:
        from worklist import norm_url  # type: ignore
    except ImportError:
        try:
            from .worklist import norm_url  # type: ignore
        except Exception:
            norm_url = None  # type: ignore
    if norm_url is not None:
        try:
            n = norm_url({"link": url})
            if n:
                return n
        except Exception:
            pass
    # Fallback — identical to fit_scorer._canonicalize_url's fallback so
    # writer and reader still agree when norm_url is unreachable.
    return str(url).split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()


def _worklist_sha8(rows: list[dict]) -> str | None:
    """Same hash formula as fit_scorer._input_breadcrumb. See _canonicalize_link
    docstring for the synchronization contract."""
    urls = sorted({
        _canonicalize_link(r.get("link") or r.get("url") or "")
        for r in rows
        if (r.get("link") or r.get("url"))
    })
    if not urls:
        return None
    return hashlib.sha256("\n".join(urls).encode("utf-8")).hexdigest()[:8]


def derive_consistency(out_dir: "Path") -> PipelineConsistency:
    """Read worklist + downstream artifacts ONCE and return their consistency.

    Pure: no streamlit, no caching, no session-state reads. The Pipeline
    page caller invokes this at the top of its render and threads the
    result through every downstream widget.

    Pairs with `fit_scorer._input_breadcrumb`. Artifacts written before
    breadcrumbs were introduced lack the `input` block; those stages
    show `input_sha8=None` and the banner reports `no_breadcrumb` instead
    of crying drift (don't punish the user for legacy files)."""
    wl_path = out_dir / "worklist.json"
    tr_path = out_dir / "worklist_triage.json"
    sc_path = out_dir / "worklist_scored.json"

    wl = _safe_load(wl_path) or {}
    wl_rows = wl.get("results") or []
    wl_sha = _worklist_sha8(wl_rows) if wl_rows else None
    try:
        wl_mtime = wl_path.stat().st_mtime if wl_path.exists() else None
    except OSError:
        wl_mtime = None

    def _stage(path: "Path", primary_key: str) -> StageConsistency:
        if not path.exists():
            return StageConsistency(exists=False)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return StageConsistency(exists=False)
        data = _safe_load(path) or {}
        inp = data.get("input") or {}
        input_sha = inp.get("sha8")
        input_rows = inp.get("rows")
        # Consistent iff both sides have a sha AND they match. Missing
        # breadcrumb → input_sha is None → is_consistent stays False, but
        # global_state reports `no_breadcrumb` rather than `drift` so the
        # banner copy doesn't accuse the user's old files of being wrong.
        consistent = bool(wl_sha and input_sha and wl_sha == input_sha)
        return StageConsistency(
            exists=True,
            mtime=mtime,
            primary_count=int(data.get(primary_key) or 0),
            input_sha8=input_sha,
            input_rows=input_rows,
            is_consistent=consistent,
            source_path=path.name,
        )

    return PipelineConsistency(
        worklist_exists=wl_path.exists() and bool(wl_rows),
        worklist_rows=len(wl_rows),
        worklist_sha8=wl_sha,
        worklist_mtime=wl_mtime,
        triage=_stage(tr_path, "stage1_passed"),
        scored=_stage(sc_path, "stage2_scored"),
    )


def consistency_banner_copy(c: PipelineConsistency) -> tuple[str, str, str]:
    """Translate a PipelineConsistency into (severity, headline, detail).

    severity: one of `success` | `warn` | `info` — UI maps to st.success /
              st.warning / st.info / etc.
    headline: short phrase for the banner row.
    detail:   one explanatory sentence the user can act on.

    The headline ALWAYS names the specific stage(s) involved — never
    "snapshot files" or "downstream stages" in the abstract. The whole
    point of the consistency view is to direct the user's attention;
    a vague banner forces them to hunt for which stage is stale."""
    gs = c.global_state
    if gs == "empty":
        return ("info", "No worklist yet",
                "Run a scrape or Gmail fetch to build the worklist first.")

    if gs == "no_breadcrumb":
        # Identify exactly which stage(s) lack a breadcrumb and which are
        # fresh, so the user knows what to re-run AND what they can trust.
        legacy = []
        proven_fresh = []
        if c.triage.exists and c.triage.input_sha8 is None:
            legacy.append(("triage", "🎯 Run triage"))
        elif c.triage.exists and c.triage.is_consistent:
            proven_fresh.append("triage")
        if c.scored.exists and c.scored.input_sha8 is None:
            legacy.append(("scoring", "🤖 Score worklist"))
        elif c.scored.exists and c.scored.is_consistent:
            proven_fresh.append("scoring")

        legacy_names = ", ".join(name for name, _ in legacy)
        # If only one stage is legacy, name the specific action button.
        if len(legacy) == 1:
            action = legacy[0][1]
            head = (f"{legacy_names.capitalize()} snapshot is legacy "
                    f"(no input fingerprint)")
            detail_parts = []
            if proven_fresh:
                detail_parts.append(
                    f"{'/'.join(proven_fresh).capitalize()} is current with "
                    f"the {c.worklist_rows:,}-row worklist "
                    f"(sha `{(c.worklist_sha8 or '')[:8]}`).")
            detail_parts.append(
                f"Click **{action}** once to embed a fingerprint and "
                f"enable drift detection going forward.")
            return ("info", head, " ".join(detail_parts))
        else:
            # Both stages legacy — generic but still names them.
            return ("info",
                    "Triage and scoring snapshots are legacy "
                    "(no input fingerprint)",
                    "Re-run 🎯 Triage and 🤖 Score worklist once each "
                    "to embed fingerprints — after that, drift between "
                    "stages will be flagged automatically.")

    if gs == "ok":
        rows = c.worklist_rows
        sha = (c.worklist_sha8 or "")[:8]
        return ("success",
                f"All stages consistent — built from the current "
                f"{rows:,}-row worklist (sha `{sha}`).",
                "Funnel numbers across triage / scoring / promote all "
                "describe the same run.")

    # Drift cases — name which stage is stale and what to do.
    drifted = []
    if gs in ("drift_at_triage", "mixed_drift") and c.triage.exists \
            and c.triage.input_sha8 is not None:
        drifted.append(
            f"triage was built against {c.triage.input_rows or '?'} rows "
            f"(sha `{(c.triage.input_sha8 or '')[:8]}`)")
    if gs in ("drift_at_scoring", "mixed_drift") and c.scored.exists \
            and c.scored.input_sha8 is not None:
        drifted.append(
            f"scoring was built against {c.scored.input_rows or '?'} rows "
            f"(sha `{(c.scored.input_sha8 or '')[:8]}`)")
    drift_list = "; ".join(drifted) or "downstream stages do not match worklist"
    if gs == "mixed_drift":
        # Both triage AND scoring lag the worklist. Re-scoring runs triage
        # first in this pipeline, so a single 🤖 Score worklist refreshes
        # both — but say so explicitly rather than implying only scoring
        # was stale.
        fix = ("Re-score the worklist (the scoring run re-runs triage "
               "first, refreshing both stages)")
    elif gs == "drift_at_scoring":
        fix = "Re-score the worklist"
    else:
        fix = "Re-run triage"
    return ("warn",
            f"Mixed freshness: current worklist has {c.worklist_rows:,} rows "
            f"(sha `{(c.worklist_sha8 or '')[:8]}`), but {drift_list}.",
            f"{fix} to bring downstream numbers in line with the current "
            "worklist.")


# ---------------------------------------------------------------------------
# Compute — the priority ladder
# ---------------------------------------------------------------------------

def _chip_set(s: Snapshot) -> tuple[Chip, ...]:
    """Decoration only. Never blocks the primary CTA."""
    chips: list[Chip] = []
    if not s.api_key_valid:
        chips.append(Chip("🔑", "API key invalid", "warn"))
    if not s.gmail_connected:
        chips.append(Chip("⚙️", "Gmail not connected", "warn"))
    if s.recent_promote_count > 0 and \
            s.last_promote_age_h is not None and s.last_promote_age_h < 0.2:
        # ~12-min decay window for success-feedback overlay.
        chips.append(Chip("✅", f"Promoted {s.recent_promote_count}", "success"))
    return tuple(chips)


def compute_next_action(s: Snapshot) -> Banner:
    """Pure function: snapshot → Banner. The Streamlit caller renders.

    Priority ladder is exhaustive; every snapshot resolves to exactly one rule.
    Order matters — rule 1 wins over rule 2, etc."""
    chips = _chip_set(s)

    # ── Rule 1 — SAFETY ────────────────────────────────────────────────────
    if s.quarantine_ratio > 0.5:
        return Banner(
            state="SAFETY",
            icon=PILL_QUARANTINE,
            headline=f"Most rows quarantined ({s.quarantine_count}/"
                     f"{s.quarantine_count + s.worklist_total}) — investigate",
            cta_label="Open Quarantine",
            cta_action="quarantine",
            severity="error",
            detail="Quarantine ratio > 50% indicates a parser regression "
                   "or upstream-source schema change. Don't promote until "
                   "you've inspected.",
            chips=chips,
        )

    # ── Rule 2 — ACTIVE ────────────────────────────────────────────────────
    if s.active_runs:
        first = s.active_runs[0]
        label = str(first.get("label") or "run")
        pct = first.get("pct")
        n = len(s.active_runs)
        suffix = f"  (+{n - 1} other)" if n > 1 else ""
        pct_str = f" — {int(pct)}%" if isinstance(pct, (int, float)) else ""
        return Banner(
            state="ACTIVE",
            icon=PILL_STALE,
            headline=f"Running: {label}{pct_str}{suffix}",
            cta_label="Stop",
            cta_action="stop_run",
            severity="info",
            detail="A pipeline run is in progress. Stop is reversible "
                   "(intermediate artifacts persist).",
            chips=chips,
        )

    # ── Rule 3 — RECENT failure (only when no usable downstream work) ──────
    # Failed scrape with usable worklist → green CTA wins (continue Promote/Score).
    fail = s.last_failure
    if fail and isinstance(fail.get("age_h"), (int, float)) and \
            fail["age_h"] < 0.5:
        bottleneck_blocks = (
            s.promotable_count == 0
            and (s.billable_count + s.reusable_count) == 0
            and s.worklist_total == 0
        )
        if bottleneck_blocks:
            stage = fail.get("stage") or "stage"
            return Banner(
                state="RECENT",
                icon=PILL_FAILED,
                headline=f"Recent failure in {stage}",
                cta_label=f"Retry {stage}",
                cta_action=f"retry_{stage}",
                severity="error",
                detail=f"Last failure: {fail.get('pipeline_id', '?')}. "
                       "No downstream work available, so the failure is the "
                       "active blocker.",
                chips=chips,
            )

    # ── Rule 4 — PROMOTE ──────────────────────────────────────────────────
    if s.promotable_count >= 1:
        return Banner(
            state="PROMOTE",
            icon=PILL_REVIEW,
            headline=f"{s.promotable_count} ready to promote (after suppressions)",
            cta_label=f"Promote {s.promotable_count}",
            cta_action="promote",
            severity="success",
            detail="Promote is fast, free, and deterministic. Adds new "
                   "tracker rows to act on now. Scoring can wait.",
            chips=chips,
        )

    # ── Rule 5 — REVIEW (just scored, nothing crossed threshold) ──────────
    # "Just scored" = scored_age_h < 24h. ≥1 verdict means we're not in
    # the "everything dropped at triage" state.
    if (
        s.promotable_count == 0
        and s.scored_age_h is not None and s.scored_age_h < 24
        and s.triage_passed > 0
    ):
        # SUPPRESS-AWARE-EMPTY (8.5) wins over a generic REVIEW when the
        # only reason promotable=0 is suppression.
        if s.suppressed_promotable_count > 0:
            return Banner(
                state="SUPPRESS-AWARE-EMPTY",
                icon=PILL_EMPTY,
                headline=f"All scored rows suppressed "
                         f"({s.suppressed_promotable_count} hidden by mutes)",
                cta_label="Review suppressions",
                cta_action="review_suppressions",
                severity="info",
                detail="Scoring completed; every above-threshold row matched "
                       "an active mute. Lift a mute to surface them, or "
                       "wait for the next scan.",
                chips=chips,
            )
        return Banner(
            state="REVIEW",
            icon=PILL_REVIEW,
            headline="Scoring complete — review verdicts",
            cta_label="Open Scoring card",
            cta_action="review_verdicts",
            severity="info",
            detail="No row hit the threshold. Inspect verdicts to "
                   "hand-pick or lower --min-score.",
            chips=chips,
        )

    # ── Rule 6 — SCORE ────────────────────────────────────────────────────
    score_candidate_n = s.billable_count + s.reusable_count
    if score_candidate_n > 0:
        if not s.api_key_valid:
            # API key invalid downgrades SCORE to a soft prompt; doesn't
            # block. Promote/Refresh paths still work without the key.
            return Banner(
                state="SCORE-BLOCKED",
                icon=PILL_STALE,
                headline=f"{score_candidate_n} unscored — API key invalid",
                cta_label="Set API key",
                cta_action="set_api_key",
                severity="warn",
                detail=f"{s.billable_count} billable + {s.reusable_count} "
                       "free re-score available, but scoring needs a valid "
                       "ANTHROPIC_API_KEY. Promote works without one.",
                chips=chips,
            )
        cost_split = (
            f"{s.billable_count} billable + {s.reusable_count} free re-score"
            if s.reusable_count else f"{s.billable_count} billable"
        )
        return Banner(
            state="SCORE",
            icon=PILL_REVIEW,
            headline=f"{score_candidate_n} unscored",
            cta_label=f"Score {score_candidate_n}",
            cta_action="score",
            severity="info",
            detail=f"Cost split: {cost_split}.",
            chips=chips,
        )

    # ── Rule 7 — REFRESH ──────────────────────────────────────────────────
    if s.freshest_input_age_h is not None and s.freshest_input_age_h > 24:
        return Banner(
            state="REFRESH",
            icon=PILL_STALE,
            headline=f"Inputs are stale ({_humanize_h(s.freshest_input_age_h)})",
            cta_label="Refresh inputs",
            cta_action="refresh",
            severity="info",
            detail="Both scrape and Gmail haven't run in 24h+. New roles "
                   "may have appeared.",
            chips=chips,
        )

    # ── Rule 8 — EMPTY ────────────────────────────────────────────────────
    if s.worklist_total == 0:
        return Banner(
            state="EMPTY",
            icon=PILL_EMPTY,
            headline="No worklist yet",
            cta_label="Set up Gmail + scrape",
            cta_action="setup",
            severity="info",
            detail="Run scrape and connect Gmail to populate the pool.",
            chips=chips,
        )

    # ── Rule 8.5 — SUPPRESS-EXPIRED ──────────────────────────────────────
    # 7-day window per § "lazy TTL expiry on read".
    if s.suppression_recently_expired:
        first = s.suppression_recently_expired[0]
        name = first.get("name", "(unnamed)")
        return Banner(
            state="SUPPRESS-EXPIRED",
            icon=PILL_EMPTY,
            headline=f"Suppression {name!r} expired",
            cta_label="Lift / Extend / Replace",
            cta_action="review_suppressions",
            severity="info",
            detail=f"{len(s.suppression_recently_expired)} mute(s) lapsed "
                   "within the last 7 days. Decide whether to renew, lift, "
                   "or let them stay expired.",
            chips=chips,
        )

    # ── Rule 8.6 — SUPPRESS-INVALID ──────────────────────────────────────
    if s.suppression_invalid_names:
        names = ", ".join(s.suppression_invalid_names[:3])
        more = f" (+{len(s.suppression_invalid_names) - 3} more)" \
            if len(s.suppression_invalid_names) > 3 else ""
        return Banner(
            state="SUPPRESS-INVALID",
            icon=PILL_QUARANTINE,
            headline=f"Suppression(s) reference unknown sectors: {names}{more}",
            cta_label="Open Triage card",
            cta_action="review_suppressions",
            severity="warn",
            detail="A sector name in suppressions.json is no longer in "
                   "sectors.KNOWN — likely renamed. Lift the bad entry or "
                   "replace it with the new name.",
            chips=chips,
        )

    # ── Rule 9 — DEFAULT ──────────────────────────────────────────────────
    return Banner(
        state="DEFAULT",
        icon=PILL_HEALTHY,
        headline="Up to date",
        cta_label=None,
        cta_action=None,
        severity="success",
        detail="No pending action. Next nightly run will pick up new roles.",
        chips=chips,
    )


def _humanize_h(h: float) -> str:
    if h < 1:
        return f"{int(h * 60)}m"
    if h < 48:
        return f"{int(h)}h"
    return f"{int(h / 24)}d"


# ---------------------------------------------------------------------------
# Coverage stats for the Triage card's `Active suppressions` table
# ---------------------------------------------------------------------------

def coverage_for_entry(entry: dict, rows: list[dict]) -> dict:
    """Wrapper around `suppressions.coverage` that adds an unsectored count
    even for company-scope entries. Format expected by the UI:
        {matched, total, unsectored}
    """
    # Lazy-import to keep this module stdlib-only at import time.
    from automation import suppressions  # noqa: WPS433
    cov = suppressions.coverage(entry["scope"], entry["name"], rows)
    if entry["scope"] == "company":
        unsectored = sum(
            1 for r in rows if not str(r.get("sector") or "").strip()
        )
        cov["unsectored"] = unsectored
    return cov


# ---------------------------------------------------------------------------
# derive_snapshot — production wiring against on-disk artifacts
# ---------------------------------------------------------------------------

def derive_snapshot(
    *,
    out_dir: Path,
    fit_cache_dir: Path,
    tracker_path: Path,
    suppressions_state: dict | None = None,
    suppressions_recently_expired: list[dict] | None = None,
    api_key_valid: bool = True,
    gmail_connected: bool = True,
    active_runs: Iterable[dict] | None = None,
    min_score: int = 7,
    now: datetime | None = None,
) -> Snapshot:
    """Read every input the banner needs from disk in one pass.

    The Streamlit caller passes `out_dir` (= `automation/outputs/`),
    `fit_cache_dir`, and `tracker_path`; everything else is derived here.
    Suppression state is passed in (don't re-load — caller already loaded
    it for the Triage card)."""
    now = now or datetime.now()

    # ── Inputs ──
    scrape_path = _latest(out_dir, "scan_*.json", exclude=("_scored", "_stderr", "_gmail"))
    gmail_path = _latest(out_dir, "scan_gmail_*.json")
    scrape_age = _content_age_h(scrape_path) if scrape_path else None
    gmail_age = _content_age_h(gmail_path) if gmail_path else None

    # ── Worklist + Scored ──
    worklist = _safe_load(out_dir / "worklist.json") or {}
    worklist_results = worklist.get("results") or []
    worklist_total = len(worklist_results)
    quarantine_count = len(worklist.get("quarantine") or [])

    scored_path = out_dir / "worklist_scored.json"
    scored = _safe_load(scored_path) or {}
    triage_passed = int(scored.get("stage1_passed") or 0)
    triage_dropped = int(scored.get("stage1_dropped") or 0)
    scored_age = _content_age_h(scored_path) if scored_path.exists() else None

    # ── Prefer the fresh standalone triage when it's newer than the
    # LLM-scored snapshot. The free 🎯 Run triage button writes
    # `worklist_triage.json` (a separate file precisely so it doesn't
    # clobber paid LLM scores) — but that means the Triage card was
    # silently showing stale numbers from worklist_scored.json (e.g.
    # "512 passed" while a fresh triage said "739 passed"). When the
    # standalone triage is newer than the last scoring run, use ITS
    # numbers; the scored file's stage1_* are by definition older.
    triage_path = out_dir / "worklist_triage.json"
    if triage_path.exists():
        try:
            tr_mtime = triage_path.stat().st_mtime
            sc_mtime = scored_path.stat().st_mtime if scored_path.exists() else 0
        except OSError:
            tr_mtime = sc_mtime = 0
        if tr_mtime > sc_mtime:
            tr_data = _safe_load(triage_path) or {}
            # Use `is not None`, not `or` — a fresh triage that legitimately
            # passed 0 rows (everything dropped) must override the stale
            # scored count, not fall back to it. Matches the app.py funnel
            # override site, which already guards on None.
            _tp = tr_data.get("stage1_passed")
            _td = tr_data.get("stage1_dropped")
            if _tp is not None:
                triage_passed = int(_tp)
            if _td is not None:
                triage_dropped = int(_td)

    # ── Billable / cached / reusable ──
    worklist_urls = {
        r.get("url") or r.get("link") for r in worklist_results
        if (r.get("url") or r.get("link"))
    }
    scored_results = scored.get("results") or []
    scored_urls = {
        r.get("url") or r.get("link") for r in scored_results
        if (r.get("url") or r.get("link"))
    }

    cache_urls: set[str] = set()
    if fit_cache_dir.exists():
        # The cache directory holds `<sha>.v2.json` files keyed by URL hash;
        # we can't reverse the hash, so this estimate counts files, not URL
        # overlap. The exact URL∩cache check is done by fit_scorer at run time.
        cache_urls = {p.stem for p in fit_cache_dir.glob("*.v2.json")}

    billable_count = max(len(worklist_urls - scored_urls) - len(cache_urls), 0)
    cached_count = len(cache_urls)
    reusable_count = sum(
        1 for r in scored_results
        if not _is_bad_placeholder(r)
        and (r.get("url") or r.get("link")) in worklist_urls
    )

    # ── Promotable ──
    tracker_urls = _tracker_url_set(tracker_path)
    suppressed_promotable_count = 0
    promotable_count = 0
    snapshot_state = suppressions_state if suppressions_state is not None else \
        {"sectors": [], "companies": []}
    for r in scored_results:
        score = _row_score(r)
        if score is None or score < min_score:
            continue
        url = r.get("url") or r.get("link")
        if not url or url in tracker_urls:
            continue
        if _row_suppressed(r, snapshot_state):
            suppressed_promotable_count += 1
            continue
        promotable_count += 1

    # ── Last failure ──
    last_failure = _read_last_failure(out_dir / "pipelines", now=now)

    # ── Suppression validity ──
    invalid_names = _suppression_invalid_names(snapshot_state)

    return Snapshot(
        scrape_age_h=scrape_age,
        gmail_age_h=gmail_age,
        worklist_total=worklist_total,
        triage_passed=triage_passed,
        triage_dropped=triage_dropped,
        billable_count=billable_count,
        cached_count=cached_count,
        reusable_count=reusable_count,
        promotable_count=promotable_count,
        suppressed_promotable_count=suppressed_promotable_count,
        quarantine_count=quarantine_count,
        recent_promote_count=0,  # caller injects from session state if available
        last_promote_age_h=None,
        scored_age_h=scored_age,
        active_runs=tuple(active_runs or ()),
        last_failure=last_failure,
        api_key_valid=api_key_valid,
        gmail_connected=gmail_connected,
        suppression_invalid_names=tuple(invalid_names),
        suppression_recently_expired=tuple(suppressions_recently_expired or ()),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_bad_placeholder(row: dict) -> bool:
    """Match the design-doc filter: `bad_verdict | bad_score | bad_reasons`
    placeholders should not count toward `reusable_count` (overstates 'free').

    Tolerates both `fit_score`/`fit_verdict` (the production schema written
    by fit_scorer) and `score`/`verdict` (the abbreviated form used by
    test fixtures here)."""
    fit = row.get("fit") or {}
    if not isinstance(fit, dict):
        return True
    verdict = (fit.get("fit_verdict") or fit.get("verdict") or "").lower()
    if verdict.startswith("bad_") or verdict in ("error", "api_error", "skipped_bad"):
        return True
    score_raw = fit.get("fit_score") if "fit_score" in fit else fit.get("score")
    if score_raw in (None, "", "bad_score"):
        return True
    reasons = fit.get("top_3_reasons") or fit.get("reasons") or []
    if isinstance(reasons, list) and len(reasons) == 1 and \
            isinstance(reasons[0], str) and reasons[0].startswith("bad_"):
        return True
    return False


def _row_score(row: dict) -> int | None:
    """Tolerates both `fit_score` (production) and `score` (compact) schemas."""
    fit = row.get("fit") or {}
    if not isinstance(fit, dict):
        return None
    raw = fit.get("fit_score") if "fit_score" in fit else fit.get("score")
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _row_suppressed(row: dict, state: dict) -> bool:
    """Lightweight version of `suppressions.is_suppressed` that only cares
    about boolean. Avoids importing the module at file-load time."""
    if not state:
        return False
    sectors_list = state.get("sectors") or []
    companies_list = state.get("companies") or []
    if not sectors_list and not companies_list:
        return False
    # Lazy import — keeps this module stdlib-only at import time.
    from automation import suppressions  # noqa: WPS433
    suppressed, _ = suppressions.is_suppressed(row, snapshot=state)
    return suppressed


def _read_last_failure(pipelines_dir: Path,
                        now: datetime) -> dict | None:
    """Find the most recent failed-stage entry in the pipeline status dir.

    Returns `{stage, age_h, pipeline_id}` or None. Only looks at files
    modified within last 24h to bound the I/O."""
    if not pipelines_dir.exists():
        return None
    cutoff = now.timestamp() - 24 * 3600
    candidates = [
        p for p in pipelines_dir.glob("pipeline_*.json")
        if p.stat().st_mtime >= cutoff
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        d = _safe_load(p)
        if not d:
            continue
        stages = d.get("stages") or {}
        for name, info in stages.items():
            if (info or {}).get("state") == "failed":
                age_h = (now.timestamp() - p.stat().st_mtime) / 3600
                return {
                    "stage": name,
                    "age_h": age_h,
                    "pipeline_id": d.get("pipeline_id", p.stem),
                }
    return None


def _suppression_invalid_names(state: dict) -> list[str]:
    """Names in suppressions.sectors that aren't in sectors.KNOWN."""
    if not state:
        return []
    names = [e.get("name") for e in state.get("sectors") or []
             if isinstance(e, dict) and e.get("name")]
    if not names:
        return []
    from automation import sectors  # noqa: WPS433
    return [n for n in names if not sectors.is_known(n)]


# ---------------------------------------------------------------------------
# Phase 3B — Scoring-card selection helpers (pure functions)
#
# `apply_selection_edit` and `compute_preflight_breakdown` are extracted from
# the Streamlit caller so they can be unit-tested without Streamlit. The
# Streamlit code in ui/app.py is the thin wrapper that wires st.session_state
# into these.
# ---------------------------------------------------------------------------

def apply_selection_edit(
    *,
    selection: set[str],
    visible_urls: Iterable[str],
    ticked_urls: Iterable[str],
) -> set[str]:
    """Reconcile the selection set against an `st.data_editor` callback.

    The Streamlit data_editor returns the entire edited frame, but the user
    can only have ticked/unticked rows that were ON SCREEN. Rows hidden by
    the current filters must be left alone — they may be ticked from a
    previous filter context. Pattern:

        new_selection = (selection - visible) | ticked_in_visible

    This is equivalent to a per-row XOR: for each visible row, set the
    selection bit to whatever the data_editor reports. Crucially, this
    means:
      - Filtering is NON-DESTRUCTIVE (state for hidden URLs preserved).
      - Toggling a row off the screen has no effect (correct — user can't
        see/touch what's off-screen).

    Returns a NEW set; does not mutate `selection`.
    """
    visible = set(visible_urls)
    ticked = set(ticked_urls)
    # Defense: ticked URLs must be a subset of visible. If not, the caller
    # is feeding us an inconsistent edited frame; silently restrict to
    # visible to avoid promoting URLs the user can't actually see.
    ticked &= visible
    return (selection - visible) | ticked


def compute_preflight_breakdown(
    *,
    selection: set[str],
    scored_rows: list[dict],
    suppressions_state: dict | None = None,
    min_score: int = 7,
    tracker_urls: set[str] | None = None,
) -> dict:
    """Pre-flight breakdown for the `[Send N selected]` caption.

    Phase-2 contract reminders (mirrored from auto_promote.py docstrings):
      - `--only-urls` BYPASSES `--min-score` — below-threshold rows still
        promote (they get `selection_mode: manual_below_threshold`).
      - Manual selection of a suppressed row PROMOTES with
        `manual_override_suppression`. It does NOT skip.
      - Geo gate is a hard correctness boundary that still applies.
      - Rows already in tracker are silently dropped by dedupe.

    So the caption is informational, not prescriptive: "you'll send N, of
    which K are below fit≥7, M override an active mute, P are already in
    tracker (will dedupe)". Empty buckets are dropped from the output.

    Returns:
        {
          "total": int,
          "below_threshold": int,    # below --min-score (will still promote)
          "override_mute": int,      # would-be-suppressed (will still promote)
          "already_tracked": int,    # in tracker (will dedupe)
          "missing_in_scored": int,  # selected URLs not in the scored file
        }
    """
    if not selection:
        return {"total": 0, "below_threshold": 0, "override_mute": 0,
                "already_tracked": 0, "missing_in_scored": 0}

    tracker_urls = tracker_urls or set()
    state = suppressions_state or {"sectors": [], "companies": []}
    has_mutes = bool(state.get("sectors") or state.get("companies"))

    # Build URL → row index for fast look-up.
    by_url: dict[str, dict] = {}
    for r in scored_rows:
        u = r.get("url") or r.get("link")
        if isinstance(u, str) and u:
            by_url[u] = r

    below_threshold = 0
    override_mute = 0
    already_tracked = 0
    missing = 0

    for url in selection:
        row = by_url.get(url)
        if row is None:
            missing += 1
            continue
        if url in tracker_urls:
            already_tracked += 1
        score = _row_score(row)
        if score is not None and score < min_score:
            below_threshold += 1
        if has_mutes and _row_suppressed(row, state):
            override_mute += 1

    return {
        "total": len(selection),
        "below_threshold": below_threshold,
        "override_mute": override_mute,
        "already_tracked": already_tracked,
        "missing_in_scored": missing,
    }


# ---------------------------------------------------------------------------
# Phase 3C — Suppression admin helpers (pure functions)
# ---------------------------------------------------------------------------

def format_until_label(until_iso: Any, today: "date | None" = None) -> str:
    """Human-readable expiry label for a suppression entry.

    Returns:
      - 'permanent' for None / null until
      - '5d left (until 2026-06-01)' for active TTL
      - 'expired' for an already-passed date (lazy expiry hasn't run yet)
    """
    from datetime import date as _date  # local import keeps top-level light
    if until_iso in (None, "", "null"):
        return "permanent"
    today = today or _date.today()
    try:
        target = _date.fromisoformat(str(until_iso)[:10])
    except (ValueError, TypeError):
        return f"until {until_iso}"  # pathological — surface raw value
    delta = (target - today).days
    if delta < 0:
        return "expired"
    if delta == 0:
        return f"expires today ({target.isoformat()})"
    return f"{delta}d left (until {target.isoformat()})"


def parse_archive_reason(reason: str) -> tuple[str, str] | None:
    """Decode 'muted_sector_X' / 'muted_company_Y' → (scope, name).

    Returns None for any other reason string (e.g., 'manual_review_queue',
    'manual_kanban', empty, non-string). Used by the context-aware Restore
    button to detect rows that were archived as part of a still-active mute,
    so the UI can offer to lift the mute alongside the restore.

    The name returned is the display-form name written by the Mute & archive
    form (e.g., 'Canadian Big 6 Banks' for sectors, 'Acme Corp' for companies).
    Callers that want to look the entry up in `suppressions.load_active()`
    should canonicalize it via `sectors.canonical(name).lower()` /
    `brand_aliases.canonical_brand(name).lower()` to match the
    `canonical_key` field stored on the entry.
    """
    if not isinstance(reason, str) or not reason:
        return None
    if reason.startswith("muted_sector_"):
        name = reason[len("muted_sector_"):].strip()
        if not name:
            return None
        return ("sector", name)
    if reason.startswith("muted_company_"):
        name = reason[len("muted_company_"):].strip()
        if not name:
            return None
        return ("company", name)
    return None


def validate_suppression_form(
    *,
    scope: str,
    name: str,
    ttl_days: int | None = None,
    until_str: str | None = None,
    reason: str = "",
) -> tuple[bool, str | None, "date | None", str]:
    """Validate inputs for the [+ Add suppression] form.

    Returns (ok, error_message, parsed_until, canonical_name).

    Rules:
    - scope must be 'sector' or 'company'.
    - name must be non-empty after strip.
    - For sector scope, name must canonicalize via sectors.canonical()
      (so the form's sector dropdown — populated from sectors.KNOWN —
      always passes; free-typed sectors fail loudly).
    - For company scope, brand_aliases.canonical_brand() must produce a
      non-empty key.
    - ttl_days and until_str are mutually exclusive. Both None is valid
      (= permanent mute) but the caller is expected to surface this as
      a yellow warning per the design doc.
    - ttl_days must be positive when present.
    - until_str must parse as YYYY-MM-DD when present.
    """
    from datetime import date as _date, timedelta as _td

    if scope not in ("sector", "company"):
        return False, f"invalid scope: {scope!r}", None, ""
    if not isinstance(name, str) or not name.strip():
        return False, "name is required", None, ""

    name_stripped = name.strip()
    canonical_name: str
    if scope == "sector":
        from automation import sectors  # noqa: WPS433
        canon = sectors.canonical(name_stripped)
        if canon is None:
            return False, (
                f"unknown sector: {name_stripped!r}. Known sectors: "
                f"{', '.join(sectors.KNOWN[:5])}…"
            ), None, ""
        canonical_name = canon
    else:
        from automation import brand_aliases  # noqa: WPS433
        canon_key = brand_aliases.canonical_brand(name_stripped).strip()
        if not canon_key:
            return False, (
                f"could not canonicalize company: {name_stripped!r}"
            ), None, ""
        canonical_name = name_stripped  # company keeps user-entered display

    if ttl_days is not None and until_str:
        return False, "ttl_days and until_str are mutually exclusive", None, canonical_name
    if ttl_days is not None:
        if not isinstance(ttl_days, int) or ttl_days <= 0:
            return False, "ttl_days must be a positive integer", None, canonical_name
        return True, None, _date.today() + _td(days=ttl_days), canonical_name
    if until_str:
        try:
            target = _date.fromisoformat(until_str)
        except (ValueError, TypeError) as exc:
            return False, f"until must be YYYY-MM-DD ({exc})", None, canonical_name
        if target <= _date.today():
            return False, "until must be a future date", None, canonical_name
        return True, None, target, canonical_name
    # No TTL → permanent mute (caller renders yellow chip).
    return True, None, None, canonical_name


def normalize_drop_reason(rr: str) -> tuple[str, str | None]:
    """Bucket a raw rule_reasons string into (category, detail).

    Categories used by the Drops sub-tab histogram:
      - 'neg_title_match'      : raw "neg:intern" → detail = "intern"
      - 'suppressed_sector'    : "suppressed_sector_60d" → detail = "60d"
      - 'suppressed_company'   : "suppressed_company_30d" → detail = "30d"
      - everything else        : split on '=' (collapse hit-list reasons)

    Stable category names mean the histogram doesn't fragment when a TTL
    changes — `suppressed_sector_60d` and `suppressed_sector_30d` collapse
    into one row labeled `suppressed_sector`."""
    if not isinstance(rr, str) or not rr:
        return ("unknown", None)
    if rr.startswith("neg:"):
        return ("neg_title_match", rr[4:])
    if rr.startswith("suppressed_sector_"):
        return ("suppressed_sector", rr[len("suppressed_sector_"):])
    if rr.startswith("suppressed_company_"):
        return ("suppressed_company", rr[len("suppressed_company_"):])
    return (rr.split("=", 1)[0], None)


def categorize_drop_reasons(drops: list[dict]) -> dict:
    """Histogram of drop reasons grouped via normalize_drop_reason.

    Returns:
      {
        "by_category":      {"suppressed_sector": 47, ...},
        "neg_terms":        {"intern": 12, ...},
        "suppressed_total": int,                    # both sector + company
      }
    """
    from collections import Counter
    by_category: Counter = Counter()
    neg_terms: Counter = Counter()
    suppressed_total = 0
    for d in drops or []:
        for rr in d.get("rule_reasons") or []:
            category, detail = normalize_drop_reason(rr)
            by_category[category] += 1
            if category == "neg_title_match" and detail:
                neg_terms[detail] += 1
            if category in ("suppressed_sector", "suppressed_company"):
                suppressed_total += 1
    return {
        "by_category": dict(by_category.most_common()),
        "neg_terms": dict(neg_terms.most_common()),
        "suppressed_total": suppressed_total,
    }


def filter_drops_by_category(
    drops: list[dict],
    category: str | None,
) -> list[dict]:
    """Return drops where any rule_reason maps to `category`.

    Used by the Drops sub-tab's category filter. category=None passes
    everything through (no filter applied)."""
    if not category:
        return list(drops or [])
    out: list[dict] = []
    for d in drops or []:
        for rr in d.get("rule_reasons") or []:
            cat, _ = normalize_drop_reason(rr)
            if cat == category:
                out.append(d)
                break
    return out


def format_preflight_caption(breakdown: dict) -> str:
    """Render the breakdown dict as the user-facing caption string.

    Always shows total. Other fields appear only when non-zero. Pattern:
        "Will send 27 — 4 below fit≥7 (still promote), 1 overrides
         active mute, 2 already in tracker (dedupe)"
    """
    total = breakdown.get("total", 0)
    if total <= 0:
        return "Nothing selected."
    parts: list[str] = []
    if breakdown.get("below_threshold"):
        parts.append(
            f"{breakdown['below_threshold']} below fit≥7 (still promote)"
        )
    if breakdown.get("override_mute"):
        parts.append(
            f"{breakdown['override_mute']} overrides active mute"
        )
    if breakdown.get("already_tracked"):
        parts.append(
            f"{breakdown['already_tracked']} already in tracker (dedupe)"
        )
    if breakdown.get("missing_in_scored"):
        parts.append(
            f"{breakdown['missing_in_scored']} URL(s) not in scored file"
        )
    suffix = f" — {', '.join(parts)}" if parts else ""
    return f"Will send {total}{suffix}."
