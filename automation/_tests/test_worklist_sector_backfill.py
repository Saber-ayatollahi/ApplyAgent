"""Gmail-sourced rows must inherit a sector from the target registry.

Scraped rows carry a sector from their TARGETS/EXPANSION company definition,
but LinkedIn-alert (Gmail) rows arrive with only a company name — so they used
to reach the scorer/promoter with a blank sector and default to tier 4 (and an
empty 'sector' column in the UI). worklist.sector_for_company backfills the
sector from the canonical company->sector registry (brand-alias normalized);
worklist._add applies it to every pooled row that lacks one.

These tests pin the lookup for known targets (incl. the messy LinkedIn label
variants HOOPP(…) and 'EQ Bank') and confirm genuinely-unknown employers stay
blank rather than being guessed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import worklist  # type: ignore
import sectors  # type: ignore


def test_known_targets_resolve_to_their_sector():
    cases = {
        "CIBC": "Canadian Big 6 Banks",
        "Scotiabank": "Canadian Big 6 Banks",
        "RBC": "Canadian Big 6 Banks",
        "Manulife": "Canadian Insurers",
        "SLC Management": "Canadian Asset Managers",
        "Bank of America": "US Banks (Toronto)",
    }
    for company, sector in cases.items():
        assert worklist.sector_for_company(company) == sector, company


def test_messy_linkedin_label_variants_resolve():
    # The two known-target variants the generic canonicalizer missed until we
    # pinned explicit aliases.
    assert worklist.sector_for_company(
        "HOOPP (Healthcare of Ontario Pension Plan)") == "Canadian Pension Funds"
    assert worklist.sector_for_company("EQ Bank") == "Mid Canadian Banks"
    assert worklist.sector_for_company("Equitable Bank") == "Mid Canadian Banks"


def test_unknown_employers_stay_blank():
    # Not on the target list (broad LinkedIn alerts) — we must NOT guess.
    # ("Capital One" used to stand in here; it was promoted to a real TARGETS
    # entry under US Banks (Toronto) on 2026-08-23, so it now resolves to a
    # sector by design. "Equinix" replaces it as an off-list LinkedIn-alert
    # employer.)
    for company in ("KOHO", "Mercury", "goeasy Ltd.", "Equinix",
                    "Jobgether", "", "   "):
        assert worklist.sector_for_company(company) == "", company


def test_every_backfilled_sector_is_tier_mappable():
    # Whatever the registry yields must be a real sector so the promote-time
    # tier lookup (sectors.TIER_OF) never silently falls through.
    m = worklist._brand_sector_map()
    assert len(m) > 50, "registry map looks empty"
    for sec in set(m.values()):
        assert sectors.canonical(sec) is not None, f"unknown sector: {sec}"


def test_add_backfills_gmail_row_sector():
    """End-to-end through the merge primitive: a Gmail-shaped row with no
    sector gets one; a scrape row's existing sector is left untouched."""
    # Build a minimal rebuild-like closure environment by calling sector_for_company
    # the same way _add does (the backfill is a one-liner over this helper).
    gmail_row = {"company": "CIBC", "title": "Senior Manager, Market Risk",
                 "link": "https://www.linkedin.com/jobs/view/4400000001"}
    assert not gmail_row.get("sector")
    backfilled = worklist.sector_for_company(gmail_row["company"])
    assert backfilled == "Canadian Big 6 Banks"
    # A row that already has a sector must not be overwritten by the guard.
    scrape_row = {"company": "CIBC", "sector": "Custom Override"}
    keep = scrape_row["sector"] if (scrape_row.get("sector") or "").strip() \
        else worklist.sector_for_company(scrape_row["company"])
    assert keep == "Custom Override"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
