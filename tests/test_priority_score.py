"""Recency-weighted Priority ranking for the Roles (Kanban) table.

Fit is intrinsic (scored once); Priority = fit × recency × tier is derived at
render time so a great-fit role that has sat on a board since December sinks
below fresh ones. These pin the curve, the combined score, and the table sort.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

import pytest  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402
import app as A  # noqa: E402  (ui/app.py)

TODAY = date(2026, 6, 5)


# ── recency_weight buckets ───────────────────────────────────────────────
@pytest.mark.parametrize("posted,expected", [
    ("2026-06-05", 1.00),   # today
    ("2026-06-04", 1.00),   # 1d  → ≤3
    ("2026-05-29", 0.95),   # 7d  → ≤7
    ("2026-05-22", 0.85),   # 14d → ≤14
    ("2026-05-06", 0.70),   # 30d → ≤30
    ("2026-04-06", 0.45),   # 60d → ≤60
    ("2026-03-07", 0.25),   # 90d → ≤90
    ("2025-12-10", 0.10),   # 177d → old
])
def test_recency_buckets(posted, expected):
    assert A.recency_weight(posted, TODAY) == expected


def test_recency_unknown_and_garbage():
    assert A.recency_weight(None, TODAY) == 0.60
    assert A.recency_weight("", TODAY) == 0.60
    assert A.recency_weight("not-a-date", TODAY) == 0.60


def test_recency_future_date_clamped():
    # A future posted_date must not exceed the fresh weight.
    assert A.recency_weight("2026-12-01", TODAY) == 1.00


# ── priority_score = fit × recency × tier ────────────────────────────────
def test_priority_buries_december_role():
    # The user's example: Canada Infra Director, fit 8, posted 2025-12-10, T1.
    assert A.priority_score(8, "2025-12-10", 1, TODAY) == 0.8


def test_priority_fresh_strong_fit_tops_out():
    assert A.priority_score(8, "2026-06-04", 1, TODAY) == 8.0
    assert A.priority_score(10, "2026-05-06", 1, TODAY) == 7.0   # 10×0.70×1.0


def test_priority_tier_nudge():
    # Same fit & freshness, lower tier → lower priority (gentle 0.64 at T4).
    fresh_t1 = A.priority_score(6, "2026-06-04", 1, TODAY)
    fresh_t4 = A.priority_score(6, "2026-06-04", 4, TODAY)
    assert fresh_t1 == 6.0 and fresh_t4 == round(6 * 0.64, 1)
    assert fresh_t4 < fresh_t1


def test_priority_fresh_beats_stale_even_with_lower_fit():
    fresh_mid = A.priority_score(7, "2026-06-03", 1, TODAY)     # 4d, fit 7
    stale_high = A.priority_score(9, "2025-12-10", 1, TODAY)    # 177d, fit 9
    assert fresh_mid > stale_high


def test_priority_aging_gem_beats_fresh_junk():
    # A 30-day dream-fit should still edge out a fresh junk-tier role.
    aging_gem = A.priority_score(9, "2026-05-06", 1, TODAY)     # 30d, fit 9, T1
    fresh_junk = A.priority_score(5, "2026-06-04", 4, TODAY)    # 1d, fit 5, T4
    assert aging_gem > fresh_junk


def test_priority_handles_bad_inputs():
    assert A.priority_score(None, "2026-06-04", 1, TODAY) == 0.0
    assert A.priority_score("x", None, "y", TODAY) >= 0.0   # no crash


# ── Table sort wires Priority as the default ranking ─────────────────────
def _kanban_df(at):
    for df in at.dataframe:
        cols = list(df.value.columns)
        if "company" in cols and "priority" in cols:
            return df.value
    return None


def test_kanban_table_sorts_by_priority_desc():
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.run()
    assert not [str(getattr(e, "value", e)) for e in at.exception]
    df = _kanban_df(at)
    assert df is not None, "Kanban table with a Priority column not found"
    pr = list(df["priority"])
    assert pr == sorted(pr, reverse=True), f"not priority-sorted: {pr[:8]}"
    # A months-old December role must not sit in the top few rows.
    top = df.head(5)
    assert not any("2025-12" in str(p) for p in top.get("posted_date", [])), \
        "a December posting leaked into the top 5"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
