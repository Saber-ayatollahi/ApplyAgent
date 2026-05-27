"""sectors.py — Single source of truth for sector display names + tier map.

Replaces the duplicated `SECTOR_ROUGH_TIER` const that previously lived only
inside `auto_promote.py`. Suppressions, audit pack, UI sector-pickers, and
auto_promote all share this registry so a sector rename happens in exactly
one place.

Stdlib-only.
"""
from __future__ import annotations

import re

# Display name → rough tier (1=top, 4=bottom). Lifted verbatim from the
# original `auto_promote.SECTOR_ROUGH_TIER` so existing tracker rows keep
# their tier semantics across the migration.
TIER_OF: dict[str, int] = {
    "Canadian Big 6 Banks":        1,
    "Canadian Pension Funds":      1,
    "US & Global Asset Managers":  2,
    "Analytics & Risk Vendors":    2,
    "Canadian Insurers":           2,
    "Big 4 Risk Advisory":         3,
    "Pension/ALM Consulting":      3,
    "US Banks (Toronto)":          3,
    "Canadian Asset Managers":     3,
    "Mid Canadian Banks":          2,
    "FS Strategy Consulting":      3,
    "Fintech":                     4,
    "Regulators & Crown":          3,
    "Market Infrastructure":       4,
    "Fund Admin/Custody":          4,
    "Mortgage Lenders":            4,
    "Hedge Funds / Alt AM":        4,
    "Private Credit":              4,
}

# Sorted display list — used by UI sector-pickers and validation.
KNOWN: list[str] = sorted(TIER_OF.keys())


def is_known(name: str) -> bool:
    """Exact match against the registry (case-sensitive — display names are
    canonical and stable). Use `canonical()` for lenient matching."""
    return name in TIER_OF


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# Pre-compute normalized → display map once at import. Cheap; KNOWN is small.
_NORM_TO_DISPLAY: dict[str, str] = {_normalize(d): d for d in KNOWN}


def canonical(name: str) -> str | None:
    """Lenient match: case- and punctuation-insensitive lookup against the
    registry. Returns the canonical display name on hit, None on miss.

    "big 6 banks" → "Canadian Big 6 Banks"  (no — too lossy; we don't drop
                                              the "Canadian" prefix).
    "Canadian Big 6 Banks" → "Canadian Big 6 Banks"
    "canadian big 6 banks" → "Canadian Big 6 Banks"
    "Canadian Big-6 Banks" → "Canadian Big 6 Banks"
    "Big 4 Risk Advisory"  → "Big 4 Risk Advisory"
    "unknown sector"       → None
    """
    return _NORM_TO_DISPLAY.get(_normalize(name))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Print the registry and run lookup checks")
    args = ap.parse_args()

    if args.smoke:
        print(f"KNOWN ({len(KNOWN)} sectors):")
        for name in KNOWN:
            print(f"  {TIER_OF[name]}  {name}")
        print()
        for probe, expected in [
            ("Canadian Big 6 Banks", "Canadian Big 6 Banks"),
            ("canadian big 6 banks", "Canadian Big 6 Banks"),
            ("Canadian Big-6 Banks", "Canadian Big 6 Banks"),
            ("CANADIAN BIG 6 BANKS", "Canadian Big 6 Banks"),
            ("Hedge Funds / Alt AM", "Hedge Funds / Alt AM"),
            ("hedge funds alt am",   "Hedge Funds / Alt AM"),
            ("unknown sector",       None),
        ]:
            got = canonical(probe)
            ok = "OK " if got == expected else "FAIL"
            print(f"  {ok}  canonical({probe!r}) -> {got!r}  (expected {expected!r})")
        print()
        print(f"is_known('Fintech')      = {is_known('Fintech')}")
        print(f"is_known('fintech')      = {is_known('fintech')}")
        print(f"is_known('Made-up Inc.') = {is_known('Made-up Inc.')}")
