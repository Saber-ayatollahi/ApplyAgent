"""Regression tests for the 2026-06 duplicate-promote bug.

24 roles landed in the tracker twice: each was promoted on 06-04 (un-suffixed
id) and again on 06-05 (a -8/-9 suffixed id). Root cause: at 06-05 promote
time the freshly-scored Workday URL carried the board segment
(`.../External/job/...`) while the existing tracker row's URL did not
(`.../job/...`) — or vice-versa — so worklist.norm_url produced two different
keys for the SAME posting and URL-only dedup missed.

auto_promote now dedups on a SET of identity keys: norm_url PLUS a Workday
host+requisition-id key that survives board-segment / path drift. These tests
pin both the pure key helpers and the end-to-end promote behaviour so the
duplicate can't come back.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))  # for `import automation.*`
sys.path.insert(0, str(AUTO))          # for un-namespaced imports

import auto_promote  # noqa: E402
import worklist  # noqa: E402


# --- pure helpers -----------------------------------------------------------

BOARDLESS = ("https://bmo.wd3.myworkdayjobs.com/job/Toronto-ON-CAN/"
             "Director--Model-Validation_R260010757-1")
BOARDFULL = ("https://bmo.wd3.myworkdayjobs.com/External/job/Toronto-ON-CAN/"
             "Director--Model-Validation_R260010757-1")


def test_norm_url_alone_misses_the_drift():
    """Documents WHY the bug happened: norm_url gives two keys for one job."""
    assert worklist.norm_url({"url": BOARDLESS}) != worklist.norm_url({"url": BOARDFULL})


def test_workday_reqid_key_is_stable_across_board_drift():
    a = auto_promote._workday_reqid_key(BOARDLESS)
    b = auto_promote._workday_reqid_key(BOARDFULL)
    assert a is not None and a == b
    assert a == "wd::bmo.wd3.myworkdayjobs.com::r260010757"


def test_workday_reqid_key_variants():
    f = auto_promote._workday_reqid_key
    # letter+digit id with posting-index facet -> facet stripped
    assert f("https://x.wd10.myworkdayjobs.com/HOOPP/job/Toronto/"
             "Principal--Total-Portfolio_JR102327").endswith("::jr102327")
    # id whose digits ARE the id behind a hyphen -> NOT stripped
    assert f("https://omers.wd3.myworkdayjobs.com/OMERS_External/job/T/"
             "Analyst--Risk-Analytics_JR-7887").endswith("::jr-7887")
    # bare numeric id (CIBC)
    assert f("https://cibc.wd3.myworkdayjobs.com/search/job/T/"
             "Senior-Director--Funding_2610965").endswith("::2610965")
    # non-Workday -> None
    assert f("https://www.linkedin.com/jobs/view/4415802327") is None
    # Workday but no req id in last segment -> None
    assert f("https://x.wd3.myworkdayjobs.com/External/job/Toronto") is None


def test_identity_keys_share_workday_key_but_not_norm_url():
    ka = auto_promote._identity_keys({"url": BOARDLESS}, worklist.norm_url)
    kb = auto_promote._identity_keys({"url": BOARDFULL}, worklist.norm_url)
    assert ka != kb                       # norm_urls differ
    assert ka & kb                        # but they overlap on the reqid key


def test_linkedin_identity_falls_back_to_norm_url():
    a = "https://www.linkedin.com/jobs/view/4415802327"
    b = ("https://www.linkedin.com/jobs/collections/similar-jobs/"
         "?currentJobId=4415802327")  # different posting (id in query)
    ka = auto_promote._identity_keys({"url": a}, worklist.norm_url)
    # LinkedIn has no Workday key; identity is exactly norm_url.
    assert ka == {worklist.norm_url({"url": a})}
    assert ka != auto_promote._identity_keys({"url": b}, worklist.norm_url)


# --- end-to-end promote -----------------------------------------------------

def _scored_row(url: str, *, company="BMO", title="Director, Model Validation",
                fit_score=8) -> dict:
    return {
        "company": company, "title": title, "link": url, "url": url,
        "location": "Toronto, ON", "sector": "Canadian Big 6 Banks",
        "source": "scrape", "_jd_len": 1500,
        "fit": {"fit_score": fit_score, "fit_verdict": "apply_now", "tier": 1,
                "summary": "synthetic", "top_3_reasons": ["r1", "r2", "r3"],
                "skill_gaps": [], "applicable_resume_variants": ["risk"]},
    }


def _tracker_row(url: str, *, company="BMO",
                 title="Director, Model Validation", fit=8) -> dict:
    return {
        "id": "auto-bmo-director-model-validation", "company": company,
        "title": title, "url": url, "status": "Found", "tier": 1,
        "fit_score_numeric": fit, "archived": False, "source": "scraper+fit_scorer",
        "posted_date": "2026-04-13", "date_found": "2026-06-04",
    }


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    out_dir = tmp_path / "outputs"; out_dir.mkdir()
    data_dir = tmp_path / "data"; data_dir.mkdir()
    tracker = data_dir / "job_tracker_data.json"
    monkeypatch.setattr(auto_promote, "OUT_DIR", out_dir)
    monkeypatch.setattr(auto_promote, "TRACKER", tracker)
    # Isolate from real suppressions — treat every row as not-suppressed.
    monkeypatch.setattr(auto_promote, "_suppressions", None)
    return {"out_dir": out_dir, "tracker": tracker}


def _write_scored(out_dir: Path, name: str, results: list[dict]) -> None:
    (out_dir / name).write_text(
        json.dumps({"scan_date": "2026-06-05", "results": results}),
        encoding="utf-8")


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["auto_promote.py", *argv])
    return auto_promote.main()


def test_promote_dedups_board_segment_drift(isolated, monkeypatch):
    """The exact bug: existing row board-LESS, scored row board-FULL → no dup."""
    isolated["tracker"].write_text(
        json.dumps({"meta": {"schema_version": 3}, "jobs": [_tracker_row(BOARDLESS)]}),
        encoding="utf-8")
    _write_scored(isolated["out_dir"], "scan_x_scored.json", [_scored_row(BOARDFULL)])

    rc = _run(monkeypatch, ["--scan", "scan_x_scored.json", "--commit",
                            "--min-score", "7"])
    assert rc == 0
    jobs = json.loads(isolated["tracker"].read_text(encoding="utf-8"))["jobs"]
    bmo = [j for j in jobs if j["title"] == "Director, Model Validation"]
    assert len(bmo) == 1, f"expected 1 row after dedup, got {len(bmo)}: {[j['id'] for j in bmo]}"
    assert bmo[0]["id"] == "auto-bmo-director-model-validation"  # original kept


def test_promote_dedups_within_a_single_scan(isolated, monkeypatch):
    """Two scored rows for the same posting (drifted URLs) in ONE scan → one row."""
    isolated["tracker"].write_text(
        json.dumps({"meta": {"schema_version": 3}, "jobs": []}), encoding="utf-8")
    _write_scored(isolated["out_dir"], "scan_x_scored.json",
                  [_scored_row(BOARDLESS), _scored_row(BOARDFULL)])

    rc = _run(monkeypatch, ["--scan", "scan_x_scored.json", "--commit",
                            "--min-score", "7"])
    assert rc == 0
    jobs = json.loads(isolated["tracker"].read_text(encoding="utf-8"))["jobs"]
    assert len(jobs) == 1, f"within-scan dedup failed: {[j['id'] for j in jobs]}"


def test_promote_upgrade_applies_across_drift(isolated, monkeypatch):
    """A higher-scoring drifted scored row upgrades the existing row in place
    (rather than adding a second), even though norm_url differs."""
    isolated["tracker"].write_text(
        json.dumps({"meta": {"schema_version": 3},
                    "jobs": [_tracker_row(BOARDLESS, fit=6)]}),
        encoding="utf-8")
    _write_scored(isolated["out_dir"], "scan_x_scored.json",
                  [_scored_row(BOARDFULL, fit_score=9)])

    rc = _run(monkeypatch, ["--scan", "scan_x_scored.json", "--commit",
                            "--min-score", "7"])
    assert rc == 0
    jobs = json.loads(isolated["tracker"].read_text(encoding="utf-8"))["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["fit_score_numeric"] == 9  # upgraded, not duplicated


# --- repost guard: same role, different board ------------------------------
# 2026-07 bug: HOOPP JR102444 was applied to on Workday, then kept coming back
# as a "new" candidate because LinkedIn carries a different URL *and* spells
# the employer differently ("HOOPP" vs the legal entity on the ATS). No URL key
# can bridge that, so the company+title repost guard has to — which means the
# company side must be brand-canonical and the title HTML-unescaped.

HOOPP_WD = ("https://hoopp.wd10.myworkdayjobs.com/HOOPP/job/"
            "Toronto-Ontario-Canada/Senior-Manager--Risk-Analytics---"
            "Modelling_JR102444")
HOOPP_LI = ("https://ca.linkedin.com/jobs/view/senior-manager-risk-analytics-"
            "modelling-at-hoopp-healthcare-of-ontario-pension-plan-4426379280")
HOOPP_ENTITY = "Healthcare of Ontario Pension Plan Trust Fund Company"


def test_company_title_key_collapses_brand_and_legal_entity():
    """'HOOPP' (LinkedIn) and the legal entity (Workday) are one employer."""
    k_ats = auto_promote._company_title_key(
        {"company": HOOPP_ENTITY, "title": "Senior Manager, Risk Analytics &amp; Modelling"})
    k_li = auto_promote._company_title_key(
        {"company": "HOOPP", "title": "Senior Manager, Risk Analytics & Modelling"})
    assert k_ats == k_li, f"{k_ats!r} != {k_li!r}"


def test_company_title_key_still_separates_distinct_roles():
    """The guard must not collapse two different openings at one employer."""
    a = auto_promote._company_title_key(
        {"company": "HOOPP", "title": "Senior Manager, Risk Analytics & Modelling"})
    b = auto_promote._company_title_key(
        {"company": "HOOPP", "title": "Manager, Market Risk"})
    assert a != b


def test_repost_of_applied_role_is_not_re_added(isolated, monkeypatch):
    """Applied on Workday → the LinkedIn repost must NOT become a second row.

    Shares no URL key with the tracker row, so only the repost guard can catch
    it. Without the brand canonicalization this added a duplicate and the role
    reappeared in the promote list forever.
    """
    isolated["tracker"].write_text(json.dumps({
        "meta": {"schema_version": 3},
        "jobs": [{
            "id": "auto-hoopp-senior-manager-risk-analytics",
            "company": HOOPP_ENTITY,
            "title": "Senior Manager, Risk Analytics &amp; Modelling",
            "url": HOOPP_WD, "status": "Applied", "tier": 1,
            "fit_score_numeric": 8, "archived": False,
            "date_applied": "2026-07-08", "date_found": "2026-07-01",
        }],
    }), encoding="utf-8")
    _write_scored(isolated["out_dir"], "scan_x_scored.json", [
        _scored_row(HOOPP_LI, company="HOOPP",
                    title="Senior Manager, Risk Analytics & Modelling"),
    ])

    rc = _run(monkeypatch, ["--scan", "scan_x_scored.json", "--commit",
                            "--min-score", "7"])
    assert rc == 0
    jobs = json.loads(isolated["tracker"].read_text(encoding="utf-8"))["jobs"]
    assert len(jobs) == 1, (
        f"repost was re-added: {[(j['company'], j['title']) for j in jobs]}")
    assert jobs[0]["status"] == "Applied"  # untouched


def test_new_role_at_applied_employer_still_promotes(isolated, monkeypatch):
    """The guard is title-scoped — a genuinely different HOOPP role still lands."""
    isolated["tracker"].write_text(json.dumps({
        "meta": {"schema_version": 3},
        "jobs": [{
            "id": "auto-hoopp-senior-manager-risk-analytics",
            "company": HOOPP_ENTITY,
            "title": "Senior Manager, Risk Analytics &amp; Modelling",
            "url": HOOPP_WD, "status": "Applied", "tier": 1,
            "fit_score_numeric": 8, "archived": False,
            "date_applied": "2026-07-08", "date_found": "2026-07-01",
        }],
    }), encoding="utf-8")
    _write_scored(isolated["out_dir"], "scan_x_scored.json", [
        _scored_row("https://www.linkedin.com/jobs/view/4426379999",
                    company="HOOPP", title="Director, Fundamental Credit Risk"),
    ])

    rc = _run(monkeypatch, ["--scan", "scan_x_scored.json", "--commit",
                            "--min-score", "7"])
    assert rc == 0
    jobs = json.loads(isolated["tracker"].read_text(encoding="utf-8"))["jobs"]
    titles = {j["title"] for j in jobs}
    assert "Director, Fundamental Credit Risk" in titles, titles


# --- standalone runner ------------------------------------------------------

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
