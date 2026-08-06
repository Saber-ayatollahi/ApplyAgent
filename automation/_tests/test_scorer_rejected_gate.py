"""Rejected-repost gate — rule_triage drops a role whose brand-canonical
company+title matches a terminal-status tracker entry BEFORE the LLM call, so a
role the user already passed on that is reposted under a NEW url (which the
URL-keyed fit cache can't catch) doesn't burn tokens re-scoring it.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import fit_scorer as fs  # noqa: E402
import worklist as W  # noqa: E402


def _rej_index(*co_titles):
    return {W._ct_key(c, t) for c, t in co_titles}


def test_repost_of_rejected_dropped_pre_llm():
    idx = _rej_index(("HOOPP", "Manager, Market Risk"))
    # Reposted under a NEW url AND the full legal company name.
    row = {
        "company": "Healthcare of Ontario Pension Plan Trust Fund Company",
        "title": "Manager, Market Risk",
        "link": "https://hoopp.wd10.myworkdayjobs.com/HOOPP/job/x/Manager--Market-Risk_JR999999",
    }
    tri = fs.rule_triage(row["title"], row=row, rejected_ct_index=idx)
    assert tri["stage1_pass"] is False
    assert "already_rejected" in tri["rule_reasons"]


def test_brand_variants_match():
    # The gate matches across brand-name variants — why _ct_key canonicalizes.
    assert W._ct_key("HOOPP", "Manager, Market Risk") == W._ct_key(
        "Healthcare of Ontario Pension Plan Trust Fund Company",
        "Manager, Market Risk")


def test_different_title_not_gated():
    idx = _rej_index(("HOOPP", "Manager, Market Risk"))
    row = {"company": "HOOPP",
           "title": "Senior Manager, Risk Analytics & Modelling",
           "link": "https://x/y_JR1"}
    tri = fs.rule_triage(row["title"], row=row, rejected_ct_index=idx)
    assert "already_rejected" not in tri["rule_reasons"]


def test_no_index_is_backward_compatible():
    row = {"company": "HOOPP", "title": "Manager, Market Risk",
           "link": "https://x/z_JR2"}
    assert "already_rejected" not in fs.rule_triage(
        row["title"], row=row, rejected_ct_index=None)["rule_reasons"]
    assert "already_rejected" not in fs.rule_triage(
        row["title"], row=row, rejected_ct_index=set())["rule_reasons"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
