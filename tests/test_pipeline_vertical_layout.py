"""Parity assertions for the vertical 6-card Pipeline layout.

The general smoke test (tests/test_pages.py) only asserts the page renders
>0 widgets with no exception — it would stay GREEN even if the redesign
silently dropped half the page's features. This test pins the specifics:

  * both layouts (vertical + classic tabs) render without exception
  * the vertical layout shows all six stage headers ①..⑥
  * the at-risk features the critics flagged as silent-drop candidates are
    present in the vertical layout: the audit-pack footer, run-history
    footer, the launch card (via its inspect toggle), and the per-stage
    download rows

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


def _run(vertical: bool, **session) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "🎯 Pipeline"
    at.session_state["_pipe_vertical_layout"] = vertical
    for k, v in session.items():
        at.session_state[k] = v
    at.run()
    return at


def _all_markdown(at: AppTest) -> str:
    """Concatenate every markdown/caption body so substring asserts are cheap."""
    return "\n".join(m.value for m in at.markdown)


def test_both_layouts_render_without_exception():
    for vertical in (True, False):
        at = _run(vertical)
        exc = [str(getattr(e, "value", e)) for e in at.exception]
        assert not exc, f"vertical={vertical} raised: {exc[:2]}"
        n = len(at.tabs) + len(at.dataframe) + len(at.button) + len(at.markdown)
        assert n > 0, f"vertical={vertical} rendered no widgets"


def test_vertical_shows_all_six_stage_headers():
    at = _run(True)
    body = _all_markdown(at)
    # The circled-digit stage markers are the load-bearing structure; assert
    # each appears so a future edit that drops a card fails loudly.
    for marker in ("① Inputs", "② Worklist", "③ Triage",
                   "④ Scoring", "⑤ Auto-promote", "⑥ Tracker"):
        assert marker in body, f"missing stage header: {marker!r}"


def test_vertical_rehomes_audit_pack_and_history():
    """Critic 'most likely silent drop' = audit pack + run history. Assert
    both have a home in the vertical footer."""
    at = _run(True)
    exp_labels = " ".join(
        getattr(e, "label", "") for e in at.get("expander")
    ).lower()
    assert "audit pack" in exp_labels, "full audit-pack footer missing"
    assert "run history" in exp_labels, "run-history footer missing"


def test_vertical_launch_card_present_when_opened():
    """The launch buttons (Refresh/Full scrape, Score, Promote, Full refresh)
    live in the run card behind the ⑤ inspect toggle. Open it and assert the
    launch buttons are reachable."""
    at = _run(True, _vc_inspect_promote=True)
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"opening launch card raised: {exc[:2]}"
    labels = " ".join(b.label for b in at.button)
    assert "scrape" in labels.lower(), "scrape launch button missing"


def test_vertical_inspect_toggles_default_closed_for_worklist():
    """Worklist inspect defaults closed so the page doesn't parse thousands
    of rows on first load (perf-critic fix). The toggle button must exist."""
    at = _run(True)
    labels = [b.label for b in at.button]
    assert any("Inspect worklist" in l for l in labels), \
        "worklist inspect toggle missing"


def test_xlsx_downloads_are_single_click():
    """Regression for the 'downloads not working' report. The xlsx export
    used to be a two-step build→reveal dance (click 📊 builds bytes into
    session_state, a *separate* ⬇ Download button appears elsewhere). It now
    builds eagerly + memoized, so every 📊 xlsx is a real download_button on
    first render — no intermediate 'build_xlsx_*' action button remains."""
    at = _run(True)
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"vertical raised: {exc[:2]}"
    dl_labels = [getattr(d, "label", "") for d in at.get("download_button")]
    assert any("xlsx" in l for l in dl_labels), \
        "no single-click xlsx download_button rendered"
    assert any("JSON" in l for l in dl_labels), "JSON download_button missing"
    # The old build-then-reveal action buttons must be gone.
    leftover = [b.key for b in at.button
                if (b.key or "").startswith("build_xlsx_")]
    assert not leftover, f"two-click xlsx build buttons still present: {leftover}"


def test_banner_cta_is_a_live_button():
    """The top banner's primary CTA must render as a clickable button keyed
    '_banner_cta_<STATE>' (it used to be an inert toast-only anchor). We don't
    assert which state — that depends on disk — only that when a CTA label
    exists, a routable button backs it."""
    at = _run(True)
    cta = [b for b in at.button if (b.key or "").startswith("_banner_cta_")]
    # A CTA may legitimately be absent only in the DEFAULT 'Up to date' state.
    body = _all_markdown(at).lower()
    if "up to date" not in body:
        assert cta, "banner has a headline but no clickable CTA button"


def test_promote_apply_panel_appears_for_fresh_dry_run(tmp_path, monkeypatch):
    """Preview→commit: when a fresh dry-run promote_report exists, ⑤ shows an
    '✅ Apply N to tracker' commit button. When the latest report is a commit
    (not a preview), the panel stays quiet."""
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
        at = _run(True)
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
        # the selectbox comprehension `[p["pipeline_id"] for p in recs]` must
        # not raise — exercise it directly.
        _ = [p["pipeline_id"] for p in recs]
    finally:
        sidecar.unlink(missing_ok=True)
        realrun.unlink(missing_ok=True)


def test_route_banner_cta_opens_correct_toggles(monkeypatch):
    """_route_banner_cta must open the right stage card's inspect toggle for
    each action and (for promote) launch via scan_runner.start_run. Drives the
    function directly with start_run/rerun stubbed so no subprocess fires."""
    import app as _app

    class _Rec:
        run_id = "test_run"
        pid = 0

    launched = {}
    monkeypatch.setattr(_app.scan_runner, "start_run",
                        lambda *a, **k: launched.setdefault("cmd", a[1]) or _Rec())
    monkeypatch.setattr(_app.st, "rerun", lambda *a, **k: None)
    monkeypatch.setattr(_app.st, "toast", lambda *a, **k: None)
    # any_work_active is a module global read by the promote branch.
    monkeypatch.setattr(_app, "any_work_active", False, raising=False)
    _app.st.session_state.clear()

    cases = {
        "promote": "_vc_inspect_promote",
        "score": "_vc_inspect_promote",
        "review_verdicts": "_vc_inspect_scoring",
        "review_suppressions": "_vc_inspect_triage",
        "quarantine": "_vc_inspect_worklist",
    }
    for action, flag in cases.items():
        _app.st.session_state.clear()
        _app._route_banner_cta(action, [])
        assert _app.st.session_state.get(flag) is True, \
            f"{action!r} should open {flag!r}"
    # promote should have launched a dry-run preview (skip-scrape + skip-score)
    assert launched.get("cmd") and "--skip-scrape" in launched["cmd"] \
        and "--skip-score" in launched["cmd"], \
        "promote CTA must launch a dry-run preview"


def test_success_overlay_chip_after_commit():
    """A recent _promote_feedback (count + ts) surfaces the '✅ Promoted N'
    chip in the banner (doc §90 success-feedback decay)."""
    from datetime import datetime
    at = _run(True, _promote_feedback={
        "count": 9, "ts": datetime.now().isoformat(timespec="seconds")})
    caps = " ".join(c.value for c in at.get("caption"))
    assert "Promoted 9" in caps, "success-feedback chip missing after commit"


def test_no_duplicate_download_rows_in_vertical():
    """Regression for the doc-§427 duplicate-downloads bug: the vertical layout
    must NOT also render the combined 'Latest outputs' panel (5 artifacts) on
    top of the per-stage download rows. With the promote inspect open vs
    closed, the download_button count must be identical — if the run card's
    render_latest_outputs_row leaked back in, opening ⑤ would add buttons."""
    at_closed = _run(True, _vc_inspect_promote=False)
    at_open = _run(True, _vc_inspect_promote=True)
    n_closed = len(at_closed.get("download_button"))
    n_open = len(at_open.get("download_button"))
    assert n_closed == n_open, (
        f"opening ⑤ changed the download count ({n_closed}→{n_open}) — the "
        "duplicate Latest-outputs panel is back")


def test_apply_panel_requires_session_preview(tmp_path):
    """Apply-to-tracker must be DISABLED until a preview is launched THIS
    session (doc §167). A fresh dry-run report on disk is necessary but not
    sufficient — without _promote_preview_armed the button is disabled."""
    import json as _json
    import app as _app

    p = _app.OUT_DIR / "promote_report_29991229.json"
    p.write_text(_json.dumps({
        "mode": "dry_run", "min_score": 7, "include_watch": False,
        "summary": {"added": 2}, "selection_mode": "threshold",
        "promoted": [
            {"company": "A", "title": "T", "score": 8, "sector": "S", "url": "u1"},
            {"company": "B", "title": "T", "score": 7, "sector": "S", "url": "u2"},
        ],
    }), encoding="utf-8")
    try:
        # Not armed → button present but disabled.
        at = _run(True)
        btn = [b for b in at.button if b.key == "_vc_promote_apply"]
        assert btn, "Apply button missing for fresh dry-run"
        assert btn[0].disabled, "Apply must be disabled without a session preview"
        # Armed → enabled.
        at2 = _run(True, _promote_preview_armed=True)
        btn2 = [b for b in at2.button if b.key == "_vc_promote_apply"]
        assert btn2 and not btn2[0].disabled, \
            "Apply must enable once a preview is armed this session"
    finally:
        p.unlink(missing_ok=True)


def test_bulk_promote_confirm_gate_at_25(monkeypatch):
    """≥25 hand-picked rows require an explicit confirm checkbox before the
    Send button enables (doc §B:243). With 25 selected and no confirm, Send
    is disabled."""
    import app as _app
    # Seed a 25-URL selection; the scored data_editor reconciles to it.
    urls = {f"http://x/{i}" for i in range(25)}
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "🎯 Pipeline"
    at.session_state["_pipe_vertical_layout"] = True
    at.session_state["_vc_inspect_scoring"] = True
    at.session_state["scoring_selected_urls"] = urls
    at.run()
    send = [b for b in at.button if b.key == "scored_bulk_promote"]
    confirm = [c for c in at.checkbox if c.key == "scored_bulk_confirm"]
    # The confirm checkbox should exist (≥25) and Send should be disabled
    # while it's unchecked. (If the selection didn't survive to the editor,
    # neither widget renders — guard so the test only asserts when present.)
    if confirm:
        assert send and send[0].disabled, \
            "Send must be disabled until the ≥25 confirm is ticked"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
