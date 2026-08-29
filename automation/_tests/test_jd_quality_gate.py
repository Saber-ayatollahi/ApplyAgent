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

    def test_long_unusual_jd_stays_ok(self):
        # No standard section headers and no boilerplate markers, but long
        # enough to be a real (if oddly-formatted) posting — benefit of the
        # doubt, so it is scored normally.
        weird = ("The team models liquidity across horizons using Python. "
                 "You bring deep treasury analytics knowledge. " * 45)
        assert len(weird) >= fit_scorer._JD_LONG_CHARS
        assert _jd_quality(weird) == "ok"

    def test_short_text_with_no_content_marker_is_flagged(self):
        # Deliberate tightening (measured: only 1.0% of 4,016 real cached
        # JDs carry no content marker at all). Such rows become `refetch` —
        # retried and reported, never silently rejected.
        weird = ("The team models liquidity across horizons using Python. "
                 "You bring deep treasury analytics knowledge. " * 10)
        assert len(weird) < fit_scorer._JD_LONG_CHARS
        assert _jd_quality(weird) == "boilerplate"

    def test_cache_gate_follows_quality(self):
        assert _should_cache_jd(REAL_JD) is True
        assert _should_cache_jd(BOILERPLATE) is False
        assert _should_cache_jd("") is False


class TestBoilerplateWithoutKnownMarkers:
    """Regression: the first version of _jd_quality required a POSITIVE
    boilerplate marker, so BMO's Workday salary/About-Us footer — which
    matches none of the standard phrasings — passed as 'ok' and was scored
    as a real JD. Absence of any content marker is now the primary signal."""

    BMO_FOOTER = (
        "the role, and may include a commission structure. Salaries for "
        "part-time roles will be pro-rated based on number of hours regularly "
        "worked. BMO Financial Group's total compensation package will vary "
        "based on the pay type of the position and may include performance-"
        "based incentives, discretionary bonuses, as well as other perks and "
        "rewards. BMO also offers health insurance, tuition reimbursement, "
        "accident and life insurance, and retirement savings plans. "
        "About Us. At BMO we are driven by a shared Purpose. "
        "BMO is committed to an inclusive, equitable and accessible workplace."
    )

    def test_unrecognised_boilerplate_is_flagged(self):
        assert _jd_quality(self.BMO_FOOTER) == "boilerplate"
        assert _should_cache_jd(self.BMO_FOOTER) is False

    def test_long_unusual_text_without_markers_gets_benefit_of_doubt(self):
        # >= _JD_LONG_CHARS and no boilerplate markers → stays 'ok' so a real
        # but oddly-formatted (often non-English) posting is still scored.
        odd = ("Le titulaire du poste contribue aux travaux de modelisation "
               "du risque de taux et participe aux analyses de bilan. " * 60)
        assert len(odd) >= fit_scorer._JD_LONG_CHARS
        assert _jd_quality(odd) == "ok"


class TestExtractSectionsWindowing:
    """Regression: _extract_sections took the earliest hit ANYWHERE, so the
    bare P1 hint "the role" matched incidental prose in a compensation
    footer ("...the role, and may include a commission structure") ~6.4 KB
    into an 8.2 KB JD — returning only the 1.7 KB tail. The LLM then scored
    that tail as "JD incomplete" and the pipeline filed it as a rejection."""

    HEAD = ("Performs validation of models and assesses model risk to confirm "
            "model appropriateness. Leads model testing and independent "
            "challenge across the portfolio. ")
    FOOTER = ("the role, and may include a commission structure. Salaries "
              "for part-time roles will be pro-rated. About Us. We are "
              "committed to an inclusive workplace. ")

    def test_incidental_prose_does_not_win_over_document_head(self):
        # Mirrors the real BMO shape: ~8 KB of body, a ~1.7 KB footer whose
        # prose contains the bare hint "the role", scored against the real
        # 8000-char cap. The tail is below the min-tail floor, so the footer
        # must not be selected.
        body = self.HEAD * 60                      # ~8 KB of real content
        doc = body + self.FOOTER * 10              # ~1.7 KB tail
        assert len(doc) > 8000 * 1.25, "doc must be past the head shortcut"
        out = fit_scorer._extract_sections(doc, 8000)
        assert "Performs validation of models" in out, \
            "must not slice to the compensation footer"

    def test_barely_over_cap_returns_head(self):
        doc = "A" * 900
        assert fit_scorer._extract_sections(doc, 800) == doc[:800]

    def test_under_cap_is_untouched(self):
        doc = "short jd"
        assert fit_scorer._extract_sections(doc, 8000) == doc

    def test_anchored_header_still_wins_on_long_docs(self):
        # A real line-anchored header far into a long doc SHOULD be selected
        # over marketing at the top.
        doc = ("About Us. We are a great place to work. " * 200
               + "\nResponsibilities:\n"
               + "Own the ALM model validation process. " * 200)
        out = fit_scorer._extract_sections(doc, 2000)
        assert out.lstrip().lower().startswith("responsibilities")


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


class TestDeterministicVerdictPredicate:
    """The French hard-reject and the det gate decide a row for free and
    deliberately never write fit_cache. Any "still needs scoring" count that
    keys off cache-file existence must exclude them, or it never reaches zero
    and the scorer looks stuck after finishing (22-French-rows, 2026-08-28)."""

    def test_french_verdict_is_deterministic(self):
        fit = {"fit_verdict": "skip", "fit_score": 0,
               "top_3_reasons": ["lang:french_required:bilingualism is required"]}
        assert fit_scorer.is_deterministic_verdict(fit) is True

    def test_det_gate_verdict_is_deterministic(self):
        fit = {"fit_verdict": "skip", "fit_score": 0,
               "top_3_reasons": ["det_gate:zero_skill_coverage"]}
        assert fit_scorer.is_deterministic_verdict(fit) is True

    def test_real_llm_skip_is_not_deterministic(self):
        fit = {"fit_verdict": "skip", "fit_score": 3,
               "top_3_reasons": ["Role is wealth-operations, not ALM"]}
        assert fit_scorer.is_deterministic_verdict(fit) is False

    def test_refetch_is_not_deterministic(self):
        # refetch means "retry next run" — genuinely outstanding work.
        fit = {"fit_verdict": "refetch", "fit_score": 0,
               "top_3_reasons": ["jd_refetch_needed:boilerplate"]}
        assert fit_scorer.is_deterministic_verdict(fit) is False

    def test_abort_placeholder_is_not_deterministic(self):
        fit = {"fit_verdict": "skip", "fit_score": 0,
               "top_3_reasons": ["aborted_fatal_api_error"]}
        assert fit_scorer.is_deterministic_verdict(fit) is False

    def test_malformed_input_is_safe(self):
        for bad in (None, {}, {"top_3_reasons": None}, "nonsense", []):
            assert fit_scorer.is_deterministic_verdict(bad) is False


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
