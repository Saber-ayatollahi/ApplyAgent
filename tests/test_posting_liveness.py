"""Pre-submit posting-liveness guard.

_classify_liveness is the pure heuristic core (no network): Workday removals
bounce to community.workday.com/invalid-url, LinkedIn keeps HTTP 200 but shows
the closed-job banner, hard 4xx/5xx are dead, near-empty 200s are unknown
(JS shell). The drawer exposes it as an on-demand "🔍 Verify posting is live"
button on every ready card.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

import pytest  # noqa: E402
import app as A  # noqa: E402


@pytest.mark.parametrize("status,final_url,body,want", [
    (404, "https://x.com/job/1", "x" * 1000, "dead"),            # hard 404
    (500, "https://x.com/job/1", "", "dead"),
    (200, "https://community.workday.com/invalid-url", "x" * 1000, "dead"),
    (200, "https://bmo.wd3.myworkdayjobs.com/External/job/x", "x" * 1000, "live"),
    (200, "https://www.linkedin.com/jobs/view/1",
     "<div class='closed-job__flavor--closed'>No longer accepting applications</div>" + "x" * 1000,
     "dead"),                                                     # LI closed banner
    (200, "https://x.com/job/1", "tiny", "unknown"),              # JS shell
    (200, "https://x.com/job/1", "x" * 1000, "live"),
])
def test_classify_liveness(status, final_url, body, want):
    verdict, _detail = A._classify_liveness(status, final_url, body)
    assert verdict == want


def test_posting_liveness_handles_no_url():
    assert A._posting_liveness("")[0] == "unknown"


def test_ready_card_has_liveness_button():
    """The drawer's ready card must expose the verify button."""
    import json
    from streamlit.testing.v1 import AppTest
    tracker = json.loads((ROOT / "data" / "job_tracker_data.json")
                         .read_text(encoding="utf-8"))
    ready = next((j["id"] for j in tracker["jobs"]
                  if j.get("resume_file") and j.get("url")), None)
    assert ready, "test data: need a tracker job with resume_file + url"
    at = AppTest.from_file(str(APP), default_timeout=140)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.session_state["_tailor_runs"] = {ready: None}
    at.run()
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc
    btns = [b for b in at.button if "Verify posting is live" in (b.label or "")]
    assert btns, "liveness button missing from the ready card"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
