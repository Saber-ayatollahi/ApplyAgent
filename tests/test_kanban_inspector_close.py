"""The Jobs Kanban Inspect/edit panel must be dismissable.

The panel is driven by st.session_state["_kb_sel_id"] (set when a table row is
clicked). It had no close affordance, and Streamlit retains a dataframe's
selection under its widget key across reruns — so after a terminal action
(❌ Won't apply / 🚫 Archive) the panel stayed pinned open on the acted-on row
(user report: "the UI is not closing the modal").

Fix: a ✖ Close button + auto-close after terminal actions, both routed through
_kb_close_inspector(), which pops the selection AND bumps a nonce baked into
the table's widget key so the table remounts with an empty selection. This
test pins the Close path (non-mutating — no tracker write) and that the
terminal-action buttons render alongside it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

from streamlit.testing.v1 import AppTest  # noqa: E402


def _an_active_job_id() -> str:
    tracker = json.loads((ROOT / "data" / "job_tracker_data.json")
                         .read_text(encoding="utf-8"))
    for j in tracker.get("jobs", []):
        if not j.get("archived") and j.get("status") not in ("Rejected",):
            return j["id"]
    return tracker["jobs"][0]["id"]


def _open_inspector_on(job_id: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=140)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.session_state["_kb_sel_id"] = job_id
    at.run()
    assert not at.exception, f"kanban raised: {[str(e) for e in at.exception][:2]}"
    return at


def test_inspector_renders_close_and_terminal_actions():
    job_id = _an_active_job_id()
    at = _open_inspector_on(job_id)
    labels = {b.label for b in at.button}
    assert "✖ Close" in labels, "selected row must show a ✖ Close button"
    # The 'stop pursuing' terminal actions render in the same panel.
    assert "❌ Won't apply" in labels
    assert "🚫 Archive" in labels


def _nonce(at) -> int:
    # AppTest.session_state maps attribute access to keys, so `.get` is not
    # available — read via membership + subscript.
    return at.session_state["_kb_table_nonce"] \
        if "_kb_table_nonce" in at.session_state else 0


def test_close_button_clears_selection_and_remounts_table():
    job_id = _an_active_job_id()
    at = _open_inspector_on(job_id)
    nonce_before = _nonce(at)

    close = [b for b in at.button if b.label == "✖ Close"]
    assert close, "no ✖ Close button to click"
    close[0].click().run()
    assert not at.exception

    # Selection cleared → inspector collapses to the 'click a row' hint.
    assert "_kb_sel_id" not in at.session_state, \
        "_kb_sel_id should be popped after Close"
    # Nonce bumped → the dataframe remounts with an empty selection so the
    # retained click can't silently reopen the panel.
    assert _nonce(at) == nonce_before + 1
    # The Close button is gone now that nothing is selected.
    assert "✖ Close" not in {b.label for b in at.button}
    # And the empty-state hint is shown.
    assert any("Click any row" in (i.value or "") for i in at.info), \
        "expected the 'click a row' hint after closing the inspector"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
