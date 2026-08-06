"""AIMCo (Alberta) must never canonicalize onto IMCO (Ontario).

Regression for the 2026-07 misattribution: LinkedIn's fuzzy company search
returned AIMCo cards for the IMCO target, the alias substring gate passed them
("imco" ⊂ "aimco"), and the scan row was stamped company=IMCO — so the AIMCo
PM Fixed Income & Relative Value role sat in the tracker under the wrong fund.

Two-part fix under test:
  1. brand_aliases: explicit "aimco" entries so the two funds canonicalize
     to distinct keys.
  2. jd_scraper's LinkedIn stamping prefers company_reported when it
     canonicalizes to a different brand than the queried target (the
     comparison below is exactly the predicate jd_scraper uses).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brand_aliases  # noqa: E402


def test_imco_still_canonicalizes_to_imco():
    assert brand_aliases.canonical_brand("IMCO") == "imco"
    assert brand_aliases.canonical_brand(
        "Investment Management Corporation of Ontario") == "imco"


def test_aimco_canonicalizes_to_its_own_key():
    assert brand_aliases.canonical_brand("AIMCo") == "aimco"
    assert brand_aliases.canonical_brand(
        "Alberta Investment Management Corporation") == "aimco"
    # LinkedIn card subtitle form — parens stripped by the normalizer.
    assert brand_aliases.canonical_brand(
        "Alberta Investment Management Corporation (AIMCo)") == "aimco"


def test_scraper_predicate_separates_the_two_funds():
    """The exact mismatch check jd_scraper's LinkedIn loop now applies."""
    reported = "Alberta Investment Management Corporation (AIMCo)"
    target = "IMCO"
    assert (brand_aliases.canonical_brand(reported)
            != brand_aliases.canonical_brand(target))


def test_same_brand_variants_do_not_trigger_the_override():
    """TD Asset Management must still stamp as the TD target (same brand)."""
    assert (brand_aliases.canonical_brand("TD Asset Management")
            == brand_aliases.canonical_brand("TD Bank"))
