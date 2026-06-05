"""Characterization tests for worklist.norm_url — the canonical-URL function
that dedup, the input-breadcrumb sha8, the scoring cache, and is_new_since_
last_score all key on. A subtle change here silently splits or merges postings,
so these pin its exact contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import worklist as W  # noqa: E402


def n(url):
    return W.norm_url({"link": url})


# ── LinkedIn tracking-redirect collapse ──────────────────────────────────
def test_linkedin_collapses_to_bare_job_id():
    a = n("https://ca.linkedin.com/jobs/view/4422035918?trk=foo&refId=bar")
    b = n("https://www.linkedin.com/jobs/view/4422035918/")
    assert a == b == "https://www.linkedin.com/jobs/view/4422035918"


# ── tracking params stripped, identity params preserved ──────────────────
def test_strips_tracking_params():
    assert n("https://x.com/careers/job/1?utm_source=li&trk=foo&ref=z") == \
        "https://x.com/careers/job/1"


def test_preserves_identity_params():
    # gh_jid distinguishes two Greenhouse-embedded postings on the same path.
    u1 = n("https://cib-bic.ca/en/jobs/?gh_jid=5022805008")
    u2 = n("https://cib-bic.ca/en/jobs/?gh_jid=5226270008")
    assert u1 != u2
    assert u1 == "https://cib-bic.ca/en/jobs?gh_jid=5022805008"


def test_identity_param_key_is_case_insensitive_and_sorted():
    # Keys lower-cased; multiple identity params sorted for determinism.
    assert n("https://x.com/j/9?JID=2&gh_jid=1") == \
        "https://x.com/j/9?gh_jid=1&jid=2"


# ── case / trailing-slash / fragment normalization ───────────────────────
def test_lowercases_and_strips_trailing_slash_and_fragment():
    assert n("https://X.COM/Careers/Job/55/#apply") == \
        "https://x.com/careers/job/55"


# ── same role via different tracking → one key; distinct roles → distinct ─
def test_same_role_different_tracking_dedups():
    assert n("https://x.com/job/7?utm_campaign=a") == \
           n("https://x.com/job/7?utm_campaign=b")


# ── Workday board-segment difference is NOT collapsed (why repair runs) ───
def test_workday_board_segment_not_collapsed():
    fixed = n("https://bmo.wd3.myworkdayjobs.com/External/job/Toronto/x_R1")
    broken = n("https://bmo.wd3.myworkdayjobs.com/job/Toronto/x_R1")
    assert fixed != broken   # norm_url can't fix this — worklist._add repairs it


# ── field precedence + empties ───────────────────────────────────────────
def test_reads_link_then_url_then_job_url():
    assert W.norm_url({"url": "https://x.com/a/"}) == "https://x.com/a"
    assert W.norm_url({"job_url": "https://x.com/b/"}) == "https://x.com/b"
    assert W.norm_url({"link": "https://x.com/c", "url": "https://x.com/d"}) \
        == "https://x.com/c"   # link wins


def test_empty_and_missing_return_empty_string():
    assert W.norm_url({}) == ""
    assert W.norm_url({"link": ""}) == ""
    assert W.norm_url({"link": "   "}) == ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
