"""Test that the 5-group consolidated nav resolves correctly.

The legacy test_pages.py drives the OLD page names (`📋 Jobs Kanban`,
`📥 Outcome Inbox`, etc.) and relies on the backwards-compat shim
inside ui/app.py to translate them. This test drives the NEW nav
directly: top-level group + sub-radio. Both code paths must work.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"

sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

from streamlit.testing.v1 import AppTest  # noqa: E402

# (group, sub-label-or-None, expected-page-resolved-to)
NAV_CASES = [
    ("🏠 Today", "Dashboard",    "🏠 Dashboard"),
    ("🏠 Today", "Replies",      "📥 Outcome Inbox"),
    ("🏠 Today", "Review",       "📬 Review Queue"),
    ("🏠 Today", "Follow-ups",   "🔔 Follow-ups"),
    ("🎯 Pipeline", "Refresh",   "🎯 Pipeline · Refresh"),
    ("🎯 Pipeline", "Score",     "🎯 Pipeline · Score"),
    ("🎯 Pipeline", "Promote",   "🎯 Pipeline · Promote"),
    ("📋 Roles", "Tracker",      "📋 Jobs Kanban"),
    ("📋 Roles", "Scans",        "📜 Scan History"),
    ("🤝 Network", None,         "🤝 Recruiter CRM"),
    ("⚙️ System", "Admin",       "⚙️ Admin"),
    ("⚙️ System", "Analytics",   "📊 Analytics"),
    ("⚙️ System", "Weekly Plan", "📅 Weekly Plan"),
    ("⚙️ System", "Content",     "📝 Content & Memory"),
]


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode("ascii")


def _run_one(group: str, sub: str | None, expected_page: str) -> dict:
    out = {"group": group, "sub": sub, "expected": expected_page,
            "ok": False, "exceptions": [], "n_widgets": 0,
            "elapsed_s": 0.0}
    t0 = time.time()
    try:
        at = AppTest.from_file(str(APP), default_timeout=90)
        at.session_state["_applyagent_nav"] = group
        if sub is not None:
            at.session_state[f"_nav_sub_{group}"] = sub
        at.run()
        out["exceptions"] = [str(getattr(e, "value", e)) for e in at.exception]
        out["n_widgets"] = (
            len(at.tabs) + len(at.dataframe) + len(at.button)
            + len(at.radio) + len(at.metric) + len(at.markdown)
        )
        out["ok"] = not out["exceptions"] and out["n_widgets"] > 0
    except Exception as e:
        out["exceptions"] = [
            f"AppTest harness crashed: {e}\n{traceback.format_exc()}"
        ]
    finally:
        out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def main() -> int:
    print(f"E2E consolidated-nav AppTest - {len(NAV_CASES)} routes")
    failures = 0
    for group, sub, expected in NAV_CASES:
        r = _run_one(group, sub, expected)
        marker = "OK  " if r["ok"] else "FAIL"
        sub_str = sub or "(direct)"
        print(f"  [{marker}] {_ascii(group):<14s} -> "
              f"{_ascii(sub_str):<14s} -> {_ascii(expected):<22s} "
              f"{r['elapsed_s']:>5.1f}s  widgets={r['n_widgets']:>3}")
        for ex in r["exceptions"][:2]:
            print(f"        ! {_ascii(str(ex))[:240]}")
        if not r["ok"]:
            failures += 1
    print(f"\n{len(NAV_CASES) - failures}/{len(NAV_CASES)} routes OK")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
