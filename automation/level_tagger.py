"""level_tagger.py — Infer a seniority LEVEL from a job title.

Salary is rarely posted (esp. Canadian roles), so title-based rank is the
reliable lever for filtering out too-junior roles / seeing the priority band.

Ordered, first-match-wins so compound titles resolve correctly:
"Associate Director" -> Director (senior), NOT Associate; "Senior Manager"
before "Manager"; "AVP" before "VP"; "Vice President" before "President".

level_for(title) -> label (str).  level_rank(title) -> int (higher = senior).
Titles with no level word -> "— Unspecified" (neutral mid rank, never filtered
as junior by default).
"""
from __future__ import annotations
import re

# (label, rank, pattern) — checked top to bottom, most senior / most specific first.
_RULES = [
    ("C-suite / Partner", 9, r"\b(chief|ceo|cfo|coo|cro|cio|cto|c-suite|partner)\b"),
    ("MD / Head",         8, r"\bmanaging director\b|\bmd\b|\bsvp\b|senior vice[\s-]?president|\bevp\b|executive vice[\s-]?president|\bhead\b|global head"),
    ("AVP / Director",    6, r"\bavp\b|assistant vice[\s-]?president|associate vice[\s-]?president|associate director|assistant director|deputy director"),
    ("VP / Sr Director",  7, r"\bvp\b|vice[\s-]?president|senior director|sr\.?\s?director|\bprincipal\b"),
    ("Director",          6, r"\bdirector\b"),
    ("Senior Manager",    5, r"senior manager|sr\.?\s?manager|senior mgr"),
    ("Manager",           4, r"\bmanager\b|\bmgr\b"),
    ("Senior Associate",  3, r"senior associate|sr\.?\s?associate"),
    ("Senior Analyst",    2, r"senior analyst|sr\.?\s?analyst|lead analyst"),
    ("Associate",         2, r"\bassociate\b"),
    ("Analyst",           1, r"\banalyst\b"),
    ("Intern / Co-op",    0, r"\bintern\b|internship|co[\s-]?op\b|\bstudent\b|new grad|graduate program"),
]
_COMPILED = [(lbl, rk, re.compile(pat, re.IGNORECASE)) for lbl, rk, pat in _RULES]

UNSPECIFIED = "— Unspecified"
_UNSPEC_RANK = 4  # neutral (Manager-ish) so unlevelled titles aren't treated as junior

# Junior→senior display order for filters.
LEVEL_ORDER = ["Intern / Co-op", "Analyst", "Senior Analyst", "Associate",
               "Senior Associate", "Manager", "Senior Manager", "Director",
               "AVP / Director", "VP / Sr Director", "MD / Head",
               "C-suite / Partner", UNSPECIFIED]

# Seniority bands OUTSIDE the target (Director) band — hidden by the triage
# "Focus band only" toggle. Too junior (Intern, plain Analyst/Associate) or
# exec (MD/Head, C-suite/Partner). KEPT: Senior Analyst & Senior Associate,
# Manager → VP/Sr Director, and Unspecified.
OUT_OF_BAND_LEVELS = frozenset({
    "Intern / Co-op", "Analyst", "Associate",
    "MD / Head", "C-suite / Partner",
})


def level_for(title: str | None) -> str:
    t = str(title or "")
    for lbl, _rk, rx in _COMPILED:
        if rx.search(t):
            return lbl
    return UNSPECIFIED


def level_rank(title: str | None) -> int:
    t = str(title or "")
    for _lbl, rk, rx in _COMPILED:
        if rx.search(t):
            return rk
    return _UNSPEC_RANK


if __name__ == "__main__":
    for t in ["Associate, Risk", "Senior Director, Total Portfolio Risk",
              "Associate Director, ALM Strategy", "Assistant Director — Modelling",
              "Manager, Market Risk", "Senior Manager, Risk Analytics & Modelling",
              "VP, Solutions Engineering (Aladdin)", "Analyst, Total Fund Management",
              "Model Validation Specialist", "Managing Director, Risk",
              "Principal, Overlay Management", "Quantitative Risk Analyst",
              "Senior Associate, Investment Engineering"]:
        print("  %-2d  %-20s <- %s" % (level_rank(t), level_for(t), t))
