"""Tests for repair_workday_urls — the Workday /<board>/ site-segment fix.

The scraper used to drop the site segment, producing
https://<host>/job/... which Workday 404s (browser → invalid-url). These
tests pin the rewrite logic; the tenant→board map is sourced from the live
TARGETS, so we only assert on its shape, not specific boards.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import repair_workday_urls as R  # noqa: E402


_TMAP = {"hoopp": "HOOPP", "td": "TD_Bank_Careers", "bmo": "External"}


def test_repairs_missing_board_segment():
    u = ("https://hoopp.wd10.myworkdayjobs.com/job/Toronto-Ontario-Canada/"
         "Vice-President--Private-Markets_JR102197")
    out = R.repair_url(u, _TMAP)
    assert out == ("https://hoopp.wd10.myworkdayjobs.com/HOOPP/job/"
                   "Toronto-Ontario-Canada/Vice-President--Private-Markets_JR102197")


def test_other_tenants_use_their_board():
    u = "https://td.wd3.myworkdayjobs.com/job/Toronto/Risk_R_123"
    assert R.repair_url(u, _TMAP) == \
        "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/Toronto/Risk_R_123"


def test_already_correct_url_untouched():
    # Already has a /<board>/ segment before /job/ → not the broken shape.
    u = "https://hoopp.wd10.myworkdayjobs.com/HOOPP/job/Toronto/X_JR1"
    assert R.repair_url(u, _TMAP) is None


def test_non_workday_url_untouched():
    assert R.repair_url("https://www.linkedin.com/jobs/view/12345", _TMAP) is None
    assert R.repair_url("https://boards.greenhouse.io/x/jobs/9?gh_jid=9", _TMAP) is None


def test_unknown_tenant_left_alone():
    u = "https://unknowntenant.wd99.myworkdayjobs.com/job/Toronto/X_JR1"
    assert R.repair_url(u, _TMAP) is None  # tenant not in map → no rewrite


def test_non_string_safe():
    assert R.repair_url(None, _TMAP) is None
    assert R.repair_url(12345, _TMAP) is None


def test_repair_obj_walks_nested_and_counts():
    data = {
        "jobs": [
            {"id": "a", "url": "https://hoopp.wd10.myworkdayjobs.com/job/T/X_JR1"},
            {"id": "b", "url": "https://www.linkedin.com/jobs/view/9"},  # untouched
            {"id": "c", "link": "https://td.wd3.myworkdayjobs.com/job/T/Y_R2"},
        ],
        "meta": {"note": "not a url"},
    }
    n = R.repair_obj(data, _TMAP)
    assert n == 2
    assert data["jobs"][0]["url"].startswith(
        "https://hoopp.wd10.myworkdayjobs.com/HOOPP/job/")
    assert data["jobs"][1]["url"] == "https://www.linkedin.com/jobs/view/9"
    assert data["jobs"][2]["link"].startswith(
        "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/")


def test_live_tenant_board_map_has_known_entries():
    m = R.build_tenant_board_map()
    assert m.get("hoopp") == "HOOPP"
    assert m.get("td") == "TD_Bank_Careers"
    assert len(m) >= 10  # plenty of Workday tenants configured
