"""End-to-end UI smoke test using Streamlit's AppTest harness.

Drives every nav page in ui/app.py and asserts no Python exception was
raised during render. Catches regressions HTTP probes miss (the server
returns 200 for the bootstrap shell even when the script crashed mid-run).

Usage:
    python tests/test_pages.py        # standalone — exits non-zero on failure
    pytest tests/test_pages.py        # via pytest

Notes:
    * st.error() banners are NOT failures — many are intentional UX (missing
      API key, destructive-action warning). Only Python exceptions during
      page render are treated as test failures.
    * Each page run is ~1s; full suite is ~12s.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"

# Make sibling automation/ and ui/ importable for AppTest's bare-mode run.
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = [
    "🏠 Dashboard",
    "🎯 Pipeline · Refresh",
    "🎯 Pipeline · Score",
    "🎯 Pipeline · Promote",
    "📥 Outcome Inbox",
    "📊 Analytics",
    "🔔 Follow-ups",
    "📬 Review Queue",
    "📋 Jobs Kanban",
    "🤝 Recruiter CRM",
    "📅 Weekly Plan",
    "📝 Content & Memory",
    "📜 Scan History",
    "⚙️ Admin",
]


def _ascii(s: str) -> str:
    """Strip non-ASCII for cp1252 consoles. Page names contain emoji."""
    return s.encode("ascii", "replace").decode("ascii")


def _run_one(page: str) -> dict:
    t0 = time.time()
    out: dict = {
        "page": page, "ok": False, "elapsed_s": 0.0,
        "exceptions": [], "n_widgets": 0,
    }
    try:
        at = AppTest.from_file(str(APP), default_timeout=90)
        at.session_state["_applyagent_nav"] = page
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


def run_all() -> tuple[int, list[dict]]:
    print(f"E2E AppTest run - {len(PAGES)} pages")
    results = []
    failures = 0
    for p in PAGES:
        r = _run_one(p)
        results.append(r)
        marker = "OK  " if r["ok"] else "FAIL"
        label = _ascii(p).strip("? ").strip() or p
        print(
            f"  [{marker}] {label:<26s} {r['elapsed_s']:>5.1f}s "
            f"- widgets={r['n_widgets']:>3} "
            f"- exceptions={len(r['exceptions'])}"
        )
        for ex in r["exceptions"][:3]:
            print(f"        ! {_ascii(str(ex))[:240]}")
        if not r["ok"]:
            failures += 1
    return failures, results


# ---------------------------------------------------------------------------
# Pytest entrypoint — one test per page so failures are isolated in output.
# ---------------------------------------------------------------------------
try:
    import pytest

    @pytest.mark.parametrize("page", PAGES)
    def test_page_renders(page):
        r = _run_one(page)
        assert not r["exceptions"], (
            f"{page} raised: {r['exceptions'][0][:400]}"
        )
        assert r["n_widgets"] > 0, f"{page} rendered no widgets"
except ImportError:
    pass


if __name__ == "__main__":
    failures, results = run_all()
    out_path = ROOT / "logs" / "e2e_apptest_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str),
                         encoding="utf-8")
    print(f"\nResults: {len(results) - failures}/{len(results)} pages OK")
    print(f"Wrote: {out_path}")
    sys.exit(0 if failures == 0 else 1)
