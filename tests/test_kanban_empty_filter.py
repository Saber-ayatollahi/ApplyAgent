"""The Roles (Kanban) table must survive a filter/search that matches 0 rows.

Regression: the "draft" badge used DataFrame.apply(axis=1), which on an EMPTY
frame returns an empty DataFrame (pandas can't infer the row-wise output
shape); assigning that to one column raised
    ValueError: Cannot set a DataFrame with multiple columns to the single
    column draft
whenever the user's filters/search matched nothing ("Showing 0 of N (filtered)").
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_zero_match_search_renders_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.run()
    ti = next(t for t in at.text_input
              if "Search (company/title)" in (t.label or ""))
    ti.set_value("zzz-no-match-zzz")
    at.run()
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"empty-filter Kanban raised: {exc[:2]}"
    # The page must still show the (empty) result caption, not a stack trace.
    assert any("Showing 0 of" in (c.value or "") for c in at.caption)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
