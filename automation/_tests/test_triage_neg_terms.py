"""Word-boundary matching for triage negative terms.

The stage-1 triage hard-fails a title if any NEG_TITLE_TERMS term appears in
it. That check used naive substring matching, so the bare term "intern"
matched inside "Internal" / "International" and killed legit senior roles
("Senior Manager, Enterprise Risk - Internal Audit", "...International Banking
Treasury"). _neg_hit now matches bare single words on letter boundaries while
leaving crafted multi-word/punctuation patterns on plain substring.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import pytest  # noqa: E402
from fit_scorer import _neg_hit, rule_triage, NEG_TITLE_TERMS  # noqa: E402


# ── _neg_hit boundary behaviour ──────────────────────────────────────────
@pytest.mark.parametrize("term,title,expected", [
    ("intern", "internal audit", False),          # the bug
    ("intern", "international banking", False),    # the bug
    ("intern", "summer intern", True),            # real intern still caught
    ("intern", "intern, risk", True),
    ("intern", "interns", False),                 # plural not listed; ok to miss
    ("coop", "cooperative housing analyst", False),   # substring guard
    ("coop", "coop placement", True),
    ("marketing", "marketing manager", True),
])
def test_neg_hit_word_boundary(term, title, expected):
    assert _neg_hit(term, title) is expected


def test_neg_hit_multiword_substring_preserved():
    # Crafted patterns keep substring semantics (they're already specific).
    assert _neg_hit("senior software engineer", "senior software engineer ii")
    assert _neg_hit("sre ", "sre developer")      # trailing-space pattern
    assert _neg_hit(".net developer", "senior .net developer")


# ── rule_triage end-to-end: the four formerly-killed roles ───────────────
def test_internal_international_roles_recovered():
    r1 = rule_triage("Senior Manager, Enterprise Risk - Internal Audit & Controls",
                     row={"title": "x"})
    assert r1["stage1_pass"] is True          # enterprise risk = STRONG
    r2 = rule_triage("Senior Manager, International Banking Treasury",
                     row={"title": "x"})
    assert r2["stage1_pass"] is True          # treasury = MEDIUM


def test_real_interns_still_dropped():
    for ti in ("Summer Intern, Risk Management",
               "Risk Analyst Intern",
               "Internship - Treasury Analytics"):   # caught by 'internship'
        r = rule_triage(ti, row={"title": ti})
        assert r["stage1_pass"] is False, ti
        assert any(rr.startswith("neg:") for rr in r["rule_reasons"]), ti


def test_vocab_gap_recoveries():
    """False-negatives surfaced by the full drop audit — title-only vocab
    gaps for genuine risk/treasury/credit roles. Each must now pass stage-1."""
    for ti in ("Central Funding & Securitized Products Quants",          # securitized
               "Manager, Loss Forecasting",                              # loss forecast
               "Senior Analyst, Global Corporate Funding"):              # corporate funding
        r = rule_triage(ti, row={"title": ti})
        assert r["stage1_pass"] is True, ti


def test_no_neg_term_self_breaks():
    # Every bare-word neg term must still fire on its own exact word — the
    # boundary fix must not stop a term from matching itself.
    for n in NEG_TITLE_TERMS:
        if n.isalpha():
            assert _neg_hit(n, f"senior {n} specialist"), n


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
