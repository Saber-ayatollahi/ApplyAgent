"""ATS-API JD fallback for JS-SPA pages whose HTML scrape is an empty shell.

Workday job pages render the description in JavaScript, so fit_scorer.fetch_jd
gets <300 chars and would score title-only. _fetch_jd_via_api pulls the real
jobDescription from the CXS JSON API instead. These pin the dispatch + cleaning
without network (the live call is exercised manually).
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import pytest               # noqa: E402
import fit_scorer as F      # noqa: E402
import jd_scraper as J      # noqa: E402


# ── URL gating (pure, no network) ────────────────────────────────────────
def test_workday_jd_html_rejects_non_workday():
    assert J.workday_jd_html("https://boards.greenhouse.io/x/jobs/9") is None
    assert J.workday_jd_html("https://www.linkedin.com/jobs/view/1") is None
    assert J.workday_jd_html("") is None
    assert J.workday_jd_html(None) is None


def test_via_api_ignores_non_workday_hosts():
    assert F._fetch_jd_via_api("https://www.linkedin.com/jobs/view/123") == ""
    assert F._fetch_jd_via_api("https://boards.greenhouse.io/x/jobs/9") == ""
    assert F._fetch_jd_via_api("") == ""


# ── Workday path strips + cleans the API HTML ────────────────────────────
def test_via_api_strips_and_cleans_workday_html(monkeypatch):
    html = ("<div><h2>Responsibilities</h2><p>You will own IRRBB and ALM "
            "measurement, FTP, and balance-sheet risk analytics across the "
            "treasury book.</p><script>tracker()</script><style>.x{}</style>"
            "</div>") * 20
    monkeypatch.setattr(J, "workday_jd_html", lambda u, **k: html)
    out = F._fetch_jd_via_api(
        "https://bmo.wd3.myworkdayjobs.com/External/job/Toronto/x_R1")
    assert "IRRBB and ALM measurement" in out
    assert "balance-sheet risk analytics" in out
    assert "<script>" not in out and "tracker()" not in out and "<p>" not in out


def test_via_api_returns_empty_when_api_has_nothing(monkeypatch):
    monkeypatch.setattr(J, "workday_jd_html", lambda u, **k: None)
    assert F._fetch_jd_via_api(
        "https://bmo.wd3.myworkdayjobs.com/External/job/Toronto/x_R1") == ""


# ── LinkedIn guest job id extraction (pure) ──────────────────────────────
@pytest.mark.parametrize("url,want", [
    ("https://www.linkedin.com/jobs/collections/similar-jobs/?currentJobId=4415802327&referenceJobId=44", "4415802327"),
    ("https://www.linkedin.com/jobs/view/manager-market-risk-at-deloitte-4415802327", "4415802327"),
    ("https://ca.linkedin.com/jobs/view/4428110825", "4428110825"),
    ("https://www.linkedin.com/jobs/search/?keywords=alm", None),
    ("https://boards.greenhouse.io/x/jobs/9", None),
    ("", None),
])
def test_linkedin_job_id(url, want):
    assert J.linkedin_job_id(url) == want


def test_via_api_strips_linkedin_guest_html(monkeypatch):
    html = ("<div class='show-more-less-html__markup'>You will validate "
            "IRRBB and market-risk models, EVE/NII and VaR.<script>x</script>"
            "</div>") * 15
    monkeypatch.setattr(J, "linkedin_job_guest",
                        lambda u, **k: {"job_id": "1", "title": "Mgr",
                                        "company": "Deloitte", "jd_html": html})
    out = F._fetch_jd_via_api(
        "https://www.linkedin.com/jobs/view/x-4415802327")
    assert "IRRBB and market-risk models" in out
    assert "<script>" not in out and "show-more-less" not in out


def test_via_api_ignores_linkedin_search_urls():
    # No job id → linkedin_job_guest returns None → '' (no network).
    assert F._fetch_jd_via_api("https://www.linkedin.com/jobs/search/?k=alm") == ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
