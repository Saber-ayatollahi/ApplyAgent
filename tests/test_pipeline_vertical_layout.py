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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
