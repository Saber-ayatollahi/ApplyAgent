"""Tests for posting-date capture, propagation, display-feed, and backfill.

Covers the four-part fix for "tracker shows no posting date":
  1. jd_scraper._workday_cxs_url  — public URL → CXS detail endpoint (pure).
  2. jd_scraper._normalize_workday_posted — relative → ISO, incl. the 30+ floor.
  3. auto_promote.make_entry — now carries posted_date from the worklist row
     (the regression that blanked every tracker row).
  4. backfill_posted_dates._to_origin / best_date — earliest-origin recovery,
     with the live CXS startDate taking precedence when reachable.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import jd_scraper as J        # noqa: E402
import auto_promote as P      # noqa: E402
import backfill_posted_dates as B  # noqa: E402


# ── 1. CXS URL derivation ────────────────────────────────────────────────
def test_cxs_url_standard():
    link = ("https://cppib.wd10.myworkdayjobs.com/cppinvestments/job/"
            "Toronto/Senior-Associate--Dynamic-PM_JR00401")
    durl, host, board_path = J._workday_cxs_url(link)
    assert durl == ("https://cppib.wd10.myworkdayjobs.com/wday/cxs/cppib/"
                    "cppinvestments/job/Toronto/Senior-Associate--Dynamic-PM_JR00401")
    assert host == "cppib.wd10.myworkdayjobs.com"
    assert board_path.startswith("cppinvestments/job/")


def test_cxs_url_locale_prefix():
    # A locale segment before the board must not be mistaken for the board.
    link = ("https://bmo.wd3.myworkdayjobs.com/en-US/External/job/"
            "Toronto-ON-CAN/Director--Model-Validation_R260010757")
    durl, _host, _bp = J._workday_cxs_url(link)
    assert "/wday/cxs/bmo/External/job/" in durl


def test_cxs_url_rejects_non_workday():
    assert J._workday_cxs_url("https://www.linkedin.com/jobs/view/123") is None
    assert J._workday_cxs_url("https://boards.greenhouse.io/x/jobs/9") is None
    assert J._workday_cxs_url("") is None
    assert J._workday_cxs_url(None) is None


# ── 2. Relative → ISO normalization, incl. the 30+ floor ─────────────────
_TODAY = date(2026, 6, 5)


def test_normalize_precise_relative():
    assert J._normalize_workday_posted("Posted Today", _TODAY) == "2026-06-05"
    assert J._normalize_workday_posted("Posted Yesterday", _TODAY) == "2026-06-04"
    assert J._normalize_workday_posted("Posted 6 Days Ago", _TODAY) == "2026-05-30"
    assert J._normalize_workday_posted("Posted 1 Week Ago", _TODAY) == "2026-05-29"


def test_normalize_30plus_floors_to_30():
    # This is the inaccuracy the CXS lookup exists to fix: 30+ floors to 30.
    assert J._normalize_workday_posted("Posted 30+ Days Ago", _TODAY) == "2026-05-06"


def test_normalize_passthrough_and_empty():
    assert J._normalize_workday_posted("2026-05-03", _TODAY) == "2026-05-03"
    assert J._normalize_workday_posted("", _TODAY) == ""
    assert J._normalize_workday_posted("garbage", _TODAY) == ""


# ── 3. Promotion now propagates posted_date (the core regression) ─────────
def _row(**over):
    r = {"company": "CPP Investments",
         "title": "Senior Associate, Dynamic Portfolio Management",
         "link": "https://cppib.wd10.myworkdayjobs.com/cppinvestments/job/Toronto/x_JR1",
         "source": "scrape",
         "fit": {"fit_verdict": "apply_now", "fit_score": 8,
                 "applicable_resume_variants": ["risk"]}}
    r.update(over)
    return r


def test_make_entry_carries_posted_date():
    e = P.make_entry(_row(posted_date="2026-05-03"))
    assert e["posted_date"] == "2026-05-03"


def test_make_entry_truncates_to_iso_day():
    e = P.make_entry(_row(posted_date="2026-05-03T12:34:56Z"))
    assert e["posted_date"] == "2026-05-03"


def test_make_entry_none_when_missing():
    e = P.make_entry(_row())          # no posted_date key
    assert e["posted_date"] is None
    e2 = P.make_entry(_row(posted_date=""))
    assert e2["posted_date"] is None


# ── 4. Backfill recovery logic ───────────────────────────────────────────
def test_to_origin_iso_passthrough():
    assert B._to_origin("2026-05-03", date(2026, 6, 2)) == "2026-05-03"


def test_to_origin_relative_uses_reference():
    # "17 days ago" as seen on 2026-05-18 pins origin to 2026-05-01.
    assert B._to_origin("Posted 17 Days Ago", date(2026, 5, 18)) == "2026-05-01"


def test_best_date_prefers_live_cxs(monkeypatch):
    monkeypatch.setattr(B, "workday_precise_date", lambda u: "2026-04-13")
    hist = {B._canon("https://x.wd3.myworkdayjobs.com/External/job/a_JR9"):
            {"2026-05-01", "2026-05-03"}}
    got, src = B.best_date(
        "https://x.wd3.myworkdayjobs.com/External/job/a_JR9", hist)
    assert got == "2026-04-13" and src == "live-cxs"


def test_best_date_falls_back_to_earliest_history(monkeypatch):
    # Live unreachable (unlisted/403) → earliest scan-history origin wins,
    # because the 30+ floor only ever biases later than truth.
    monkeypatch.setattr(B, "workday_precise_date", lambda u: None)
    url = "https://cppib.wd10.myworkdayjobs.com/cppinvestments/job/Toronto/x_JR1"
    hist = {B._canon(url): {"2026-05-01", "2026-05-03"}}
    got, src = B.best_date(url, hist)
    assert got == "2026-05-01" and src == "scan-history"


def test_best_date_none_when_nothing(monkeypatch):
    monkeypatch.setattr(B, "workday_precise_date", lambda u: None)
    got, src = B.best_date("https://acme.example/careers/123", {})
    assert got is None and src == "none"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
