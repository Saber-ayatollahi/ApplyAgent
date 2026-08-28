"""Seniority-floor policy tests (user policy, 2026-08-28).

Below Saber's Senior Manager / Associate Director band → hard drop at triage:
  - Analyst-level titles, any company (incl. Senior/Principal Analyst, Analyste)
  - Associate-level titles, any company (Associate Director / AVP exempt)
  - Bare "Manager" titles at bank sectors only (Senior Manager stays;
    non-bank Managers stay)
Also asserts the UI-facing TRIAGE_POLICIES registry stays in sync.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))

from fit_scorer import (_below_grade_reason, rule_triage,  # type: ignore
                        TRIAGE_POLICIES)

BANK = {"sector": "Canadian Big 6 Banks"}
MIDBANK = {"sector": "Mid Canadian Banks"}
USBANK = {"sector": "US Banks (Toronto)"}
PENSION = {"sector": "Canadian Pension Funds"}
INSURER = {"sector": "Canadian Insurers"}
NOSECTOR = {"sector": ""}


class TestAnalystDrop:
    def test_plain_analyst(self):
        assert _below_grade_reason("Analyst, Global Risk", BANK) == "below_grade:analyst"

    def test_senior_analyst_any_company(self):
        assert _below_grade_reason(
            "Senior Analyst, Portfolio Analytics", PENSION) == "below_grade:analyst"

    def test_principal_analyst_still_drops(self):
        # "principal" is deliberately NOT an exemption token — a Principal
        # Analyst is a senior IC, still an analyst role.
        assert _below_grade_reason(
            "Principal Analyst, Market Risk", BANK) == "below_grade:analyst"

    def test_french_analyste(self):
        assert _below_grade_reason(
            "Analyste principal, Actuariat", INSURER) == "below_grade:analyst"

    def test_analytics_is_not_analyst(self):
        # Word boundary: "Analytics" must never trip the analyst rule.
        assert _below_grade_reason(
            "Senior Manager, Risk Analytics", BANK) is None


class TestAssociateDrop:
    def test_senior_associate(self):
        assert _below_grade_reason(
            "Senior Associate, Total Portfolio Rebalancing",
            PENSION) == "below_grade:associate"

    def test_associate_portfolio_manager(self):
        assert _below_grade_reason(
            "Associate Portfolio Manager, Public Credit",
            PENSION) == "below_grade:associate"

    def test_associate_director_exempt(self):
        assert _below_grade_reason(
            "Associate Director, Enterprise Model Risk Management",
            BANK) is None

    def test_associate_vice_president_exempt(self):
        assert _below_grade_reason(
            "Associate Vice President, Model Risk", BANK) is None
        assert _below_grade_reason("AVP, Central Actuarial", INSURER) is None


class TestBankManagerDrop:
    def test_bare_manager_at_big6(self):
        assert _below_grade_reason(
            "Manager, Model Validation & Approval", BANK) == "below_grade:bank_manager"

    def test_bare_manager_at_midbank_and_usbank(self):
        assert _below_grade_reason(
            "Manager, Liquidity & Funding Management",
            MIDBANK) == "below_grade:bank_manager"
        assert _below_grade_reason(
            "Group Manager, Insider Risk", USBANK) == "below_grade:bank_manager"

    def test_senior_manager_stays_at_bank(self):
        assert _below_grade_reason(
            "Senior Manager, Model Validation", BANK) is None
        assert _below_grade_reason("Sr. Manager, Treasury Analytics", BANK) is None

    def test_non_bank_manager_stays(self):
        # A pension Portfolio Manager is a live target class.
        assert _below_grade_reason(
            "Portfolio Manager, Portfolio Construction & Risk", PENSION) is None
        assert _below_grade_reason("Manager, Capital Management", INSURER) is None

    def test_blank_sector_is_not_a_bank(self):
        assert _below_grade_reason("Manager, Risk Analytics", NOSECTOR) is None
        assert _below_grade_reason("Manager, Risk Analytics", None) is None

    def test_managing_director_exempt(self):
        assert _below_grade_reason(
            "Managing Director, Risk Governance", BANK) is None


class TestRuleTriageIntegration:
    def test_triage_drops_below_grade_with_tagged_reason(self):
        row = {"sector": "Canadian Big 6 Banks", "company": "BMO",
               "title": "Manager, Model Validation", "source": "scrape"}
        out = rule_triage("Manager, Model Validation", row=row)
        assert out["stage1_pass"] is False
        assert out["rule_reasons"] == ["below_grade:bank_manager"]

    def test_triage_keeps_associate_director(self):
        row = {"sector": "Canadian Big 6 Banks", "company": "RBC",
               "title": "Associate Director, Enterprise Model Risk Management",
               "source": "scrape"}
        out = rule_triage(row["title"], row=row)
        assert out["stage1_pass"] is True

    def test_triage_drops_senior_analyst_before_safety_net(self):
        # Even at a target company (scrape source), the floor wins over the
        # single-token safety net.
        row = {"sector": "Canadian Pension Funds", "company": "OMERS",
               "title": "Senior Analyst, Portfolio Risk", "source": "scrape"}
        out = rule_triage(row["title"], row=row)
        assert out["stage1_pass"] is False
        assert out["rule_reasons"] == ["below_grade:analyst"]


class TestPolicyRegistry:
    def test_registry_covers_the_floor_tags(self):
        tags = {p["tag"] for p in TRIAGE_POLICIES}
        assert {"below_grade:analyst", "below_grade:associate",
                "below_grade:bank_manager"} <= tags

    def test_registry_rows_have_ui_columns(self):
        for p in TRIAGE_POLICIES:
            for col in ("policy", "action", "scope", "tag", "why"):
                assert p.get(col), (p, col)
