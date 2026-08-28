"""JD-quality gate tests — the "non-evaluable ≠ rejected" guard.

Covers the 2026-08-25 audit findings:
  1. _jd_quality classifies thin / boilerplate / real JD text correctly.
  2. _should_cache_jd blocks poisoned cache writes (the BMO JS-shell bug).
  3. score_with_llm returns verdict `refetch` — never `skip` — for
     non-evaluable JDs, without touching the LLM or fit_cache.
  4. The det gate is bypassed for rows whose stage-1 triage had a STRONG
     title hit (extractor blind spot ≠ junk role).
  5. Extractor vocabulary recovers the Scotia Medicus class (pension
     funding / stewardship JDs no longer read as zero-coverage).
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))

import fit_scorer  # type: ignore
from fit_scorer import _jd_quality, _should_cache_jd  # type: ignore


# Mimics the cached BMO Workday JS-shell fallback: long enough to clear the
# old 300-char cache bar, all benefits/EEO/nav noise, zero job content.
BOILERPLATE = (
    "We're here to help. At BMO we are driven by a shared Purpose. "
    "Total Rewards! We celebrate our people. Equal opportunity employer. "
    "Accommodation is available upon request. Join our Talent Community "
    "to receive job alerts. Apply now. Similar jobs you may like. "
    "Privacy policy and cookie settings. Sign in to your profile. "
) * 6  # ~1.9KB, comparable to the real 1,728-char poisoned entries

REAL_JD = (
    "What will you do? Perform validation of credit risk models and assess "
    "model risk. Key responsibilities include independent review, "
    "benchmarking, and documentation. Qualifications: 5+ years of "
    "experience in model validation; proficiency in Python and SQL. "
    "Is this role right for you? "
) * 4


class TestJdQuality:
    def test_empty_is_thin(self):
        assert _jd_quality("") == "thin"
        assert _jd_quality(None) == "thin"

    def test_short_scrap_is_thin(self):
        assert _jd_quality("Director, Risk. Toronto. Apply now.") == "thin"

    def test_boilerplate_shell_is_flagged(self):
        assert _jd_quality(BOILERPLATE) == "boilerplate"

    def test_real_jd_is_ok(self):
        assert _jd_quality(REAL_JD) == "ok"

    def test_unusual_but_real_jd_stays_ok(self):
        # No standard section headers AND no boilerplate markers — must NOT
        # be flagged (precision-first: both conditions are required).
        weird = ("The team models liquidity across horizons using Python. "
                 "You bring deep treasury analytics knowledge. " * 20)
        assert _jd_quality(weird) == "ok"

    def test_cache_gate_follows_quality(self):
        assert _should_cache_jd(REAL_JD) is True
        assert _should_cache_jd(BOILERPLATE) is False
        assert _should_cache_jd("") is False


class TestRefetchVerdict:
    ROLE = {"link": "https://example.com/jobs/nonexistent-refetch-test",
            "company": "TestCo", "title": "Director, ALM"}

    def _fresh_role(self, tmp_path):
        # Point the fit cache at a temp dir so no cached verdict interferes
        # and nothing we do here persists.
        return dict(self.ROLE)

    def test_boilerplate_jd_returns_refetch(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        out = fit_scorer.score_with_llm(client=None, role=self._fresh_role(tmp_path),
                                        jd_text=BOILERPLATE)
        assert out["fit_verdict"] == "refetch"
        assert out["fit_score"] == 0
        assert any("jd_refetch_needed" in r for r in out["top_3_reasons"])

    def test_thin_jd_returns_refetch(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        out = fit_scorer.score_with_llm(client=None, role=self._fresh_role(tmp_path),
                                        jd_text="")
        assert out["fit_verdict"] == "refetch"

    def test_refetch_not_written_to_fit_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        fit_scorer.score_with_llm(client=None, role=self._fresh_role(tmp_path),
                                  jd_text=BOILERPLATE)
        assert list(tmp_path.glob("*.json")) == []

    def test_cached_verdict_beats_refetch_gate(self, monkeypatch, tmp_path):
        """A good cached verdict must be served even when today's fetch
        failed — the gate runs after the cache check."""
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        import json as _json
        cached = {"fit_score": 8, "fit_verdict": "tailor_and_apply",
                  "top_3_reasons": ["cached"], "skill_gaps": [], "tier": 1,
                  "summary": "cached verdict"}
        cache_path = fit_scorer._cache_path_fit(self.ROLE["link"])
        cache_path.write_text(_json.dumps(cached), encoding="utf-8")
        out = fit_scorer.score_with_llm(client=None, role=dict(self.ROLE),
                                        jd_text="")
        assert out["fit_verdict"] == "tailor_and_apply"


class TestDetGateStrongTitleBypass:
    def test_strong_hit_bypasses_gate_reaches_llm_path(self, monkeypatch, tmp_path):
        """Zero coverage + STRONG stage-1 title hit must NOT det-gate: the
        row must proceed to the LLM call. With a None client every attempt
        fails inside the retry loop, so the sentinel for 'the API was
        actually attempted' is an LLM_failure error verdict — NOT the det
        gate's zero-coverage skip."""
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        monkeypatch.setattr(
            fit_scorer, "_compute_deterministic_analysis",
            lambda jd: {"coverage_pct": 0, "gap_phrases": [], "_prompt_block": ""})
        role = {"link": "https://example.com/jobs/strong-bypass-test",
                "company": "TestCo", "title": "Senior Manager, Model Validation",
                "_triage": {"hits_breakdown": {"strong": ["model validation"]}}}
        out = fit_scorer.score_with_llm(client=None, role=role, jd_text=REAL_JD)
        assert "det_gate:zero_skill_coverage" not in (out.get("top_3_reasons") or [])
        assert out.get("fit_verdict") != "skip"

    def test_no_strong_hit_still_gated(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fit_scorer, "FIT_CACHE", tmp_path)
        monkeypatch.setattr(
            fit_scorer, "_compute_deterministic_analysis",
            lambda jd: {"coverage_pct": 0, "gap_phrases": [], "_prompt_block": ""})
        role = {"link": "https://example.com/jobs/gate-test",
                "company": "TestCo", "title": "Office Coordinator",
                "_triage": {"hits_breakdown": {"strong": []}}}
        out = fit_scorer.score_with_llm(client=None, role=role, jd_text=REAL_JD)
        assert out["fit_verdict"] == "skip"
        assert "det_gate:zero_skill_coverage" in out["top_3_reasons"]


class TestExtractorVocabulary:
    """The Scotia Medicus class: pension funding/stewardship vocabulary."""

    SCOTIA_STYLE_JD = (
        "The Director, Funding & Investments leads funding, investments, and "
        "financial stewardship for the Pension Plan. Support the "
        "Administrative Board in overseeing investment strategy, including "
        "asset allocation, investment performance, and compliance with the "
        "Statement of Investment Policies and Procedures (SIPP). Oversee "
        "actuarial valuations, assumptions, and funding strategy in "
        "partnership with the Plan Actuary. Evaluate funding risks and "
        "regulatory compliance. Qualifications: 10+ years of leadership in "
        "pension funding, investments, finance, or actuarial oversight."
    )

    def test_pension_stewardship_jd_has_coverage(self):
        from jd_skill_extract import extract  # type: ignore
        r = extract(self.SCOTIA_STYLE_JD)
        assert r.coverage_pct > 0, "pension-funding JD must not be zero-coverage"
        assert len(r.skill_ids_matched) >= 3

    def test_treasury_liquidity_vocab_matches(self):
        from jd_skill_extract import extract  # type: ignore
        jd = ("Requirements: experience in corporate treasury, liquidity risk "
              "management, and intraday liquidity monitoring within Group "
              "Treasury. Responsibilities include treasury management and "
              "stress testing.")
        r = extract(jd)
        assert "sk_alm" in r.skill_ids_matched
        assert "sk_liquidity_gap" in r.skill_ids_matched
