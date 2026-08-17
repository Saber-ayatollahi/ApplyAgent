"""Hard-reject gate for French/bilingual language requirements.

Saber is not bilingual, so any role that REQUIRES French is an automatic
no regardless of fit score — see _requires_french() in fit_scorer.py.
Two checkpoints share this detector: rule_triage() (title-level, before
any JD fetch) and score_one() (JD-body-level, after fetch but before the
LLM call). Deliberately precision-leaning: fires only on clear requirement
phrasing and backs off when French is framed as an asset/nice-to-have,
since "bilingualism is considered an asset" is real Toronto-market
phrasing for "optional" and must NOT hard-reject a good-fit role.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import pytest  # noqa: E402
from fit_scorer import _requires_french, rule_triage  # noqa: E402


# ── True positives — must hard-reject ────────────────────────────────────
@pytest.mark.parametrize("text", [
    "This role is Bilingual (English/French) and requires daily client interaction in Quebec.",
    "The successful candidate must be fluent in French and English.",
    "Bilingualism (English and French) is required for this position.",
    "Proficiency in both English and French is required.",
    "You must speak French and English fluently to support our Quebec clients.",
    "Ability to communicate effectively in both English and French is essential.",
    "This position requires French language skills.",
    "Bilingualism English and French (frequent interactions with PSP employees based in Quebec)",
    "For candidates located in Quebec, bilingualism (French – English) is required considering the necessity to interact regularly.",
    "Is bilingual (French and English), both spoken and written. Language requirement (Bill 96).",
])
def test_requires_french_true_positives(text):
    assert _requires_french(text) is not None


# ── False-positive traps — must NOT reject (asset / nice-to-have / absent) ──
@pytest.mark.parametrize("text", [
    "Bilingualism (English/French) is considered a strong asset.",
    "French is an asset but not required for this role.",
    "Knowledge of French would be an asset.",
    "Fluency in French is nice-to-have but not mandatory for this Toronto-based role.",
    "We are a fully English-speaking Toronto team focused on risk analytics.",
    "Strong communication skills required for this senior manager role.",
    "Bilingualism English/French is highly desirable.",
    "French language skills would be beneficial but are not a requirement.",
    "",
    "No language requirements mentioned anywhere in this JD.",
])
def test_requires_french_false_positive_traps(text):
    assert _requires_french(text) is None


# ── rule_triage() title-level checkpoint ─────────────────────────────────
def test_rule_triage_hard_rejects_bilingual_title():
    tri = rule_triage("Bilingual (English/French) Client Service Manager")
    assert tri["stage1_pass"] is False
    assert any(r.startswith("lang:french_required") for r in tri["rule_reasons"])


def test_rule_triage_does_not_reject_french_as_asset_title():
    # Title alone rarely carries asset-framing, but confirm a French mention
    # without requirement language doesn't trip the title-level gate.
    tri = rule_triage("Senior Manager, Enterprise Risk (French an asset)")
    reasons = tri.get("rule_reasons", [])
    assert not any(r.startswith("lang:french_required") for r in reasons)
