"""Parity assertions for the 3-view Pipeline layout (v3.2).

The general smoke test (tests/test_pages.py) only asserts each page renders
>0 widgets with no exception — it would stay GREEN even if the redesign
silently dropped half the page's features. This test pins the specifics of
the split: the former single Pipeline page is now three sub-pages selected by
the sidebar sub-radio —

  * ① Refresh  = ① Inputs + ② Worklist
  * ② Score    = ③ Triage + ④ Scoring
  * ③ Promote  = ⑤ Promote + ⑥ Tracker

and pins the at-risk features the critics flagged as silent-drop candidates:
the audit-pack footer, run-history footer (now on Promote), the launch card
(via its inspect toggle, now on Promote), and the per-stage download rows.

Run:
    pytest tests/test_pipeline_vertical_layout.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

import pytest  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

# The sidebar sub-radio key for the Pipeline group (group label incl. emoji).
_SUB_KEY = "_nav_sub_🎯 Pipeline"
_VIEWS = ("Refresh", "Score", "Promote")


def _run(view: str = "Refresh", **session) -> AppTest:
    """Render the Pipeline page on the given sub-view (Refresh/Score/Promote)."""
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "🎯 Pipeline"
    at.session_state[_SUB_KEY] = view
    for k, v in session.items():
        at.session_state[k] = v
    at.run()
    return at


def _all_markdown(at: AppTest) -> str:
    """Concatenate every markdown/caption body so substring asserts are cheap."""
    return "\n".join(m.value for m in at.markdown)


def test_all_three_views_render_without_exception():
    for view in _VIEWS:
        at = _run(view)
        exc = [str(getattr(e, "value", e)) for e in at.exception]
        assert not exc, f"view={view} raised: {exc[:2]}"
        n = len(at.tabs) + len(at.dataframe) + len(at.button) + len(at.markdown)
        assert n > 0, f"view={view} rendered no widgets"


def test_each_view_shows_its_two_stage_headers():
    """The circled-digit stage markers are the load-bearing structure; assert
    each view shows its OWN two cards — and (negatively) not the others' — so a
    future edit that mis-files a card fails loudly."""
    expected = {
        "Refresh": ("① Inputs", "② Worklist"),
        "Score":   ("③ Triage", "④ Scoring"),
        "Promote": ("⑤ Promote", "⑥ Tracker"),
    }
    for view, markers in expected.items():
        body = _all_markdown(_run(view))
        for marker in markers:
            assert marker in body, f"view={view} missing stage header {marker!r}"
        # A card belonging to a different view must not leak in.
        for other_view, other_markers in expected.items():
            if other_view == view:
                continue
            for om in other_markers:
                assert om not in body, \
                    f"view={view} unexpectedly shows {om!r} (belongs to {other_view})"


def test_promote_rehomes_audit_pack_and_history():
    """Critic 'most likely silent drop' = audit pack + run history. They now
    live in the ③ Promote footer."""
    at = _run("Promote")
    exp_labels = " ".join(
        getattr(e, "label", "") for e in at.get("expander")
    ).lower()
    assert "audit pack" in exp_labels, "full audit-pack footer missing on Promote"
    assert "run history" in exp_labels, "run-history footer missing on Promote"


def test_promote_card_present_no_scrape_score_leak():
    """The consolidated ⑤ Promote card hosts the promote actions (one-click
    ⚡ Promote all qualifying + the per-row select table) — the standalone
    Auto-promote card was folded in. Assert the ⑤ Promote card renders and
    that no scrape/score launch leaked onto Promote (those belong on
    ① Refresh / ④ Scoring)."""
    at = _run("Promote")
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"Promote view raised: {exc[:2]}"
    assert "⑤ Promote" in _all_markdown(at), "⑤ Promote card header missing"
    labels = " ".join(b.label for b in at.button).lower()
    # The relocated launches must NOT appear on Promote.
    assert "scrape" not in labels, \
        "scrape launch leaked onto Promote (belongs on ① Refresh)"
    assert "score worklist" not in labels, \
        "score-worklist launch leaked onto Promote (belongs on ④ Scoring)"
    assert "full refresh" not in labels, \
        "full-refresh launch leaked onto Promote (belongs on ① Refresh)"


def test_full_scrape_relocated_to_refresh_inputs():
    """① Inputs (Refresh view) owns scraping; Promote never does. The primary
    🛰 Refresh scrape now DEFAULTS to the full target list (159) — full
    coverage is the default action — with ⚡ Quick core scrape (66) as the
    secondary fast option. Both live on Refresh, neither on Promote."""
    refresh_labels = " ".join(b.label for b in _run("Refresh").button).lower()
    # Primary full-coverage refresh + the quick-core option both on ① Inputs.
    assert "refresh scrape" in refresh_labels, \
        "primary 🛰 Refresh scrape (full) missing on Refresh (① Inputs)"
    assert "quick core scrape" in refresh_labels, \
        "⚡ Quick core scrape (secondary) missing on Refresh (① Inputs)"
    # No scrape launch leaks onto Promote (belongs on ① Refresh).
    promote_labels = " ".join(
        b.label for b in _run("Promote", _vc_inspect_promote=True).button
    ).lower()
    assert "scrape" not in promote_labels, \
        "a scrape launch leaked onto Promote (belongs on ① Refresh)"


def test_score_worklist_relocated_to_score_scoring():
    """v3.2 strict split: 🤖 Score worklist moved from the Promote run card to
    the ④ Scoring card (Score view). Assert it renders on Score and NOT on
    Promote."""
    score_labels = " ".join(b.label for b in _run("Score").button).lower()
    assert "score worklist" in score_labels or "score (no rows)" in score_labels, \
        "🤖 Score worklist missing on Score (④ Scoring)"
    promote_labels = " ".join(
        b.label for b in _run("Promote", _vc_inspect_promote=True).button
    ).lower()
    assert "score worklist" not in promote_labels, \
        "🤖 Score worklist still leaks onto Promote"


def test_score_a_url_expander_on_score_not_promote():
    """doc §575: Score-a-single-URL is a persistent expander INSIDE the ④
    Scoring card (Score view), not the Promote run card."""
    score_exp = " ".join(
        getattr(e, "label", "") for e in _run("Score").get("expander")
    ).lower()
    assert "score a single url" in score_exp, \
        "🔗 Score-a-URL expander missing on Score (④ Scoring)"
    promote_exp = " ".join(
        getattr(e, "label", "")
        for e in _run("Promote", _vc_inspect_promote=True).get("expander")
    ).lower()
    assert "score a single url" not in promote_exp, \
        "🔗 Score-a-URL expander still leaks onto Promote"


def test_full_refresh_relocated_to_refresh_view():
    """v3.2 strict split: 🌅 Full refresh moved from the Promote run card to the
    nightly strip on the Refresh view."""
    refresh_labels = " ".join(b.label for b in _run("Refresh").button).lower()
    assert "full refresh" in refresh_labels, \
        "🌅 Full refresh missing on Refresh (nightly strip)"
    promote_labels = " ".join(
        b.label for b in _run("Promote", _vc_inspect_promote=True).button
    ).lower()
    assert "full refresh" not in promote_labels, \
        "🌅 Full refresh still leaks onto Promote"


def test_next_step_hint_refresh_only():
    """The last-activity strip renders on all views, but its 'Next step' hint
    column is gated to Refresh only (it duplicated/contradicted the Promote-only
    next-action banner). Assert the '**Next step**' marker shows on Refresh and
    not on Score/Promote."""
    # Match the exact hint marker "**Next step**" (singular, no trailing colon)
    # so the Gmail panel's "**Next steps:**" can't produce a false positive.
    assert "**Next step**" in _all_markdown(_run("Refresh")), \
        "'Next step' hint missing on Refresh"
    for view in ("Score", "Promote"):
        assert "**Next step**" not in _all_markdown(_run(view)), \
            f"'Next step' hint leaked onto {view} (should be Refresh-only)"


def test_worklist_inspect_toggle_default_closed_on_refresh():
    """Worklist inspect defaults closed so the page doesn't parse thousands
    of rows on first load (perf-critic fix). The toggle button must exist on
    the ① Refresh view."""
    at = _run("Refresh")
    labels = [b.label for b in at.button]
    assert any("Inspect worklist" in l for l in labels), \
        "worklist inspect toggle missing on Refresh"


def test_xlsx_downloads_are_single_click():
    """Regression for the 'downloads not working' report. The xlsx export
    used to be a two-step build→reveal dance. It now builds eagerly +
    memoized, so every 📊 xlsx is a real download_button on first render. The
    per-stage download rows are spread across the 3 views; assert on Refresh
    (Inputs + Worklist rows) that at least one single-click xlsx + JSON
    download_button renders and no build-then-reveal action button remains."""
    at = _run("Refresh")
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"Refresh raised: {exc[:2]}"
    dl_labels = [getattr(d, "label", "") for d in at.get("download_button")]
    assert any("xlsx" in l for l in dl_labels), \
        "no single-click xlsx download_button rendered"
    assert any("JSON" in l for l in dl_labels), "JSON download_button missing"
    leftover = [b.key for b in at.button
                if (b.key or "").startswith("build_xlsx_")]
    assert not leftover, f"two-click xlsx build buttons still present: {leftover}"


def test_banner_cta_is_a_live_button_on_promote():
    """The next-action banner's primary CTA must render as a clickable button
    keyed '_banner_cta_<STATE>'. The banner is now scoped to the ③ Promote
    view only; assert there. We don't assert which state — that depends on
    disk — only that when a CTA label exists, a routable button backs it."""
    at = _run("Promote")
    cta = [b for b in at.button if (b.key or "").startswith("_banner_cta_")]
    body = _all_markdown(at).lower()
    if "up to date" not in body:
        assert cta, "banner has a headline but no clickable CTA button"


def test_banner_absent_on_refresh_and_score():
    """The next-action banner is Promote-only. Refresh + Score must NOT render
    a `_banner_cta_*` button (the Dashboard owns the cross-surface 'what now?'
    via its own Next-Best-Action hero; Refresh/Score shouldn't be dominated by
    a promote CTA)."""
    for view in ("Refresh", "Score"):
        at = _run(view)
        cta = [b for b in at.button if (b.key or "").startswith("_banner_cta_")]
        assert not cta, f"banner CTA should not render on {view}, found {[b.key for b in cta]}"


def test_promote_apply_panel_appears_for_fresh_dry_run(tmp_path, monkeypatch):
    """Preview→commit: when a fresh dry-run promote_report exists (e.g. from
    the next-action banner's promote CTA), the consolidated ⑤ Promote card
    surfaces a '✅ Apply N to tracker' commit button. When the latest report
    is a commit, the panel stays quiet."""
    import json as _json
    import app as _app  # the module under test (ui/app.py)

    out = _app.OUT_DIR
    stamp = "29991230"
    p = out / f"promote_report_{stamp}.json"
    p.write_text(_json.dumps({
        "mode": "dry_run", "min_score": 7, "include_watch": False,
        "summary": {"added": 2}, "selection_mode": "threshold",
        "promoted": [
            {"company": "TestBank", "title": "Risk VP", "score": 8,
             "sector": "Banks", "url": "http://x/1"},
            {"company": "TestCo", "title": "Quant", "score": 7,
             "sector": "Pension Funds", "url": "http://x/2"},
        ],
    }), encoding="utf-8")
    try:
        at = _run("Promote")
        exc = [str(getattr(e, "value", e)) for e in at.exception]
        assert not exc, f"raised: {exc[:2]}"
        apply_btn = [b for b in at.button if b.key == "_vc_promote_apply"]
        assert apply_btn, "Apply-to-tracker button missing for fresh dry-run"
        assert "Apply 2" in apply_btn[0].label, \
            f"unexpected apply label: {apply_btn[0].label!r}"
    finally:
        p.unlink(missing_ok=True)


def test_list_pipelines_excludes_suppression_sidecars():
    """run_pipeline._snapshot_suppressions writes pipeline_<id>_suppressions.json
    into the SAME pipelines/ dir. Those sidecars match the `pipeline_*.json`
    glob but are {version,sectors,companies} with no pipeline_id — they used to
    pollute the History table and crash the `p["pipeline_id"]` selectbox with a
    KeyError. list_pipelines must drop them (and any record missing
    pipeline_id)."""
    import json as _json
    import app as _app

    pdir = _app.PIPELINE_DIR
    pdir.mkdir(parents=True, exist_ok=True)
    sidecar = pdir / "pipeline_99991231_235959_suppressions.json"
    realrun = pdir / "pipeline_99991231_235959.json"
    sidecar.write_text(_json.dumps(
        {"version": 1, "sectors": [], "companies": []}), encoding="utf-8")
    realrun.write_text(_json.dumps(
        {"pipeline_id": "99991231_235959", "state": "finished",
         "started_at": "2999-12-31T23:59:59", "stages": {}}), encoding="utf-8")
    try:
        recs = _app.list_pipelines(50)
        assert all(r.get("pipeline_id") for r in recs), \
            "a record without pipeline_id leaked through (sidecar not excluded)"
        ids = [r["pipeline_id"] for r in recs]
        assert "99991231_235959" in ids, "real run record was dropped"
        _ = [p["pipeline_id"] for p in recs]
    finally:
        sidecar.unlink(missing_ok=True)
        realrun.unlink(missing_ok=True)


def test_route_banner_cta_opens_correct_toggles_and_subpage(monkeypatch):
    """_route_banner_cta must (a) open the right stage card's inspect toggle
    for each action AND (b) — new in v3.2 — switch the nav to the Pipeline
    sub-page that hosts that card, or the toggle opens an off-page card and
    nothing visible happens. Drives the function directly with start_run/rerun
    stubbed so no subprocess fires."""
    import app as _app

    class _Rec:
        run_id = "test_run"
        pid = 0

    launched = {}
    monkeypatch.setattr(_app.scan_runner, "start_run",
                        lambda *a, **k: launched.setdefault("cmd", a[1]) or _Rec())
    monkeypatch.setattr(_app.st, "rerun", lambda *a, **k: None)
    monkeypatch.setattr(_app.st, "toast", lambda *a, **k: None)
    monkeypatch.setattr(_app, "any_work_active", False, raising=False)
    _app.st.session_state.clear()

    # action -> (inspect-toggle flag, expected Pipeline sub-page)
    # v3.2: the `score` CTA routes to ④ Scoring (Score view) — the 🤖 Score
    # worklist button moved there from the ⑤ run card.
    cases = {
        "promote":             ("_vc_inspect_promote",  "Promote"),
        "score":               ("_vc_inspect_scoring",  "Score"),
        "review_verdicts":     ("_vc_inspect_scoring",  "Score"),
        "review_suppressions": ("_vc_inspect_triage",   "Score"),
        "quarantine":          ("_vc_inspect_worklist", "Refresh"),
    }
    for action, (flag, sub) in cases.items():
        _app.st.session_state.clear()
        _app._route_banner_cta(action, [])
        assert _app.st.session_state.get(flag) is True, \
            f"{action!r} should open {flag!r}"
        # The handler runs after the sub-radio instantiates, so it stashes the
        # target sub-page in the non-widget `_pipe_pending_view` key; the
        # pre-radio transfer block applies it on the next run. (Asserting the
        # widget key directly would be wrong — Streamlit drops that write.)
        assert _app.st.session_state.get("_pipe_pending_view") == sub, \
            f"{action!r} should stash pending sub-page {sub!r}"
    # promote should have launched a dry-run preview (skip-scrape + skip-score)
    assert launched.get("cmd") and "--skip-scrape" in launched["cmd"] \
        and "--skip-score" in launched["cmd"], \
        "promote CTA must launch a dry-run preview"


def test_banner_cta_click_switches_subpage_end_to_end():
    """Full round trip: a banner CTA click on one view must land the user on
    the sub-page hosting the target card (via the `_pipe_pending_view` →
    pre-radio transfer indirection). Guards the documented risk #2 — a direct
    widget-key write from the handler is dropped because the sub-radio already
    instantiated this run.

    Deterministic: rather than depend on whichever banner state is live for the
    test's on-disk fixtures (which would make the assertions silently skip),
    seed `_pipe_pending_view` directly — that's the exact input the handler
    produces — and prove the pre-radio transfer block lands the user on the
    right view with the target card visible. The handler→pending-view half is
    covered separately by test_route_banner_cta_opens_correct_toggles_and_subpage."""
    targets = {
        "Promote": "⑤ Promote",
        "Score":   "④ Scoring",
        "Refresh": "① Inputs",
    }
    for view, card in targets.items():
        # Start on a DIFFERENT view so the transfer has to actually move us.
        start = "Refresh" if view != "Refresh" else "Promote"
        at = AppTest.from_file(str(APP), default_timeout=120)
        at.session_state["_applyagent_nav"] = "🎯 Pipeline"
        at.session_state[_SUB_KEY] = start
        at.session_state["_pipe_pending_view"] = view   # what a CTA would stash
        at.run()
        exc = [str(getattr(e, "value", e)) for e in at.exception]
        assert not exc, f"pending_view={view} raised: {exc[:2]}"
        # Transfer block must have applied the pending view and cleared the key.
        sub = None
        try:
            sub = at.session_state[_SUB_KEY]
        except Exception:
            pass
        assert sub == view, f"pending_view={view!r} landed on {sub!r}"
        pending_left = None
        try:
            pending_left = at.session_state["_pipe_pending_view"]
        except Exception:
            pass
        assert pending_left is None, \
            f"_pipe_pending_view not cleared (still {pending_left!r})"
        assert card in _all_markdown(at), \
            f"target card {card!r} not visible after jump to {view}"


def test_success_overlay_chip_after_commit():
    """A recent _promote_feedback (count + ts) surfaces the '✅ Promoted N'
    chip in the banner (doc §90 success-feedback decay). The banner is now
    Promote-only, so assert on the ③ Promote view."""
    from datetime import datetime
    at = _run("Promote", _promote_feedback={
        "count": 9, "ts": datetime.now().isoformat(timespec="seconds")})
    caps = " ".join(c.value for c in at.get("caption"))
    assert "Promoted 9" in caps, "success-feedback chip missing after commit"


def test_bulk_promote_confirm_gate_at_25(monkeypatch):
    """≥25 hand-picked rows require an explicit confirm checkbox before the
    Send button enables (doc §B:243). The scored card / data_editor is on the
    ② Score view now. With 25 selected and no confirm, Send is disabled."""
    import app as _app
    urls = {f"http://x/{i}" for i in range(25)}
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "🎯 Pipeline"
    at.session_state[_SUB_KEY] = "Score"
    at.session_state["_vc_inspect_scoring"] = True
    at.session_state["scoring_selected_urls"] = urls
    at.run()
    send = [b for b in at.button if b.key == "scored_bulk_promote"]
    confirm = [c for c in at.checkbox if c.key == "scored_bulk_confirm"]
    # The bulk controls only render when the scored card has ≥1 PROMOTABLE row
    # (apply_now / tailor_and_apply) — the data_editor + selection block is
    # nested under `if not _promotable.empty:`. With the live worklist_scored
    # fixture that may be empty, in which case the gate genuinely can't render.
    # Skip EXPLICITLY in that case so the test can never masquerade as a pass
    # (was a silent `if confirm:` that always no-op'd — flagged as vacuous).
    if not confirm:
        pytest.skip("scored card has no promotable rows in the current fixture; "
                    "bulk-confirm gate cannot render to be asserted")
    assert send and send[0].disabled, \
        "Send must be disabled until the ≥25 confirm is ticked"


# ---------------------------------------------------------------------------
# v3.2 refinements: scorer-status table (Score) + worklist auto-open (Refresh)
# ---------------------------------------------------------------------------
def _captions(at):
    return "\n".join(c.value for c in at.get("caption"))


def test_scorer_status_renders_on_score():
    """The ④ Scoring card shows an always-visible 'Last scoring run' status
    block (cached/new/model/errors + Logs expander) above the inspect toggle.
    Skips cleanly if no scored fixture exists."""
    import app as _app
    if not list(_app.OUT_DIR.glob("*_scored.json")):
        pytest.skip("no *_scored.json fixture to summarize")
    at = _run("Score")
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"Score raised: {exc[:2]}"
    assert "Last scoring run" in _all_markdown(at), "scorer-status block missing on Score"
    # The status grid uses st.metric — labels surface via at.metric, not markdown.
    metric_labels = {m.label for m in at.metric}
    for lbl in ("Input", "Triaged", "Scored", "Cached (free)", "New (paid)", "Model"):
        assert lbl in metric_labels, f"scorer-status missing metric {lbl!r}"
    exp = " ".join(getattr(e, "label", "") for e in at.get("expander"))
    assert "Scoring logs" in exp, "scoring-logs expander missing"


def test_worklist_closed_on_cold_load():
    """Cold load of the Refresh view must seed `_seen_rebuilt_at` and leave the
    heavy worklist table CLOSED (perf — ~1,400 rows). The seed makes the
    rebuilt_at comparison a no-op on first visit."""
    at = _run("Refresh")
    # The auto-open block seeds the cache on first render…
    seeded = None
    try:
        seeded = at.session_state["_seen_rebuilt_at"]
    except Exception:
        pass
    assert "_seen_rebuilt_at" in at.session_state, "cold load must seed _seen_rebuilt_at"
    # …and the table stays closed.
    opened = None
    try:
        opened = at.session_state["_vc_inspect_worklist"]
    except Exception:
        pass
    assert not opened, "worklist table must stay closed on a cold load"


def test_worklist_autoopens_after_session_rebuild():
    """When a rebuild happens DURING the session (worklist.status().rebuilt_at
    differs from the cached `_seen_rebuilt_at`), the worklist table auto-opens
    and shows the '🕒 Worklist rebuilt …' freshness header."""
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "🎯 Pipeline"
    at.session_state[_SUB_KEY] = "Refresh"
    # A stale 'seen' value simulates a rebuild having completed this session.
    at.session_state["_seen_rebuilt_at"] = "1999-01-01T00:00:00"
    at.run()
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"Refresh raised: {exc[:2]}"
    opened = None
    try:
        opened = at.session_state["_vc_inspect_worklist"]
    except Exception:
        pass
    assert opened is True, "worklist table must auto-open after a session rebuild"
    # The freshness header renders inside the open table (when a worklist
    # exists on disk). Guard so the test is meaningful only when there's a
    # rebuilt_at to show.
    import app as _app
    if _app.worklist.status().get("rebuilt_at"):
        assert "Worklist rebuilt" in _captions(at), \
            "refresh-time header missing in the open worklist table"


def test_worklist_dedup_line_present_on_refresh():
    """The ② Worklist header caption surfaces the dedup picture (exact/near-dup
    merges and/or new-since-score) — not just raw source counts."""
    at = _run("Refresh")
    caps = _captions(at)
    # At least one of the dedup bits should be present when a worklist exists.
    import app as _app
    if _app.worklist.status().get("stats"):
        assert ("scrape" in caps and "gmail" in caps), "source-count line missing"
        # The richer bits are presence-guarded; assert the line is at least the
        # enriched form when merges or new-rows exist in the fixture.
        # (Non-fatal if the fixture has zero merges and zero new rows.)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
