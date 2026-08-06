"""geo_tagger.py — Tag each scraped job with a geography / work-authorization
bucket, so the report shows not just the strategy lane but *where* a role is and
what it implies for a Canadian (no-visa vs TN move).

Buckets (visa lens):
  🍁 Canada — GTA          no move, no visa
  🍁 Canada — other        relocate within Canada, no visa
  🌎 Remote                location-agnostic / Canada-remote, no visa
  🇺🇸 US — remote          no visa (EOR / contractor from Canada)
  🇺🇸 US — on-site (TN)    needs work authorization (TN route)
  🌍 Other / overseas      on-site outside North America
  ❔ Unknown               no location given (scorer decides)

Stdlib-only; reuses the detectors in location_filter.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from location_filter import (
    is_gta_or_canada_remote, has_us, has_canada,
    _GTA_CITY_RE, _GTA_WITH_US_STATE_RE,
)

GEO_CA_GTA = "\U0001F341 Canada — GTA"
GEO_CA_OTHER = "\U0001F341 Canada — other"
GEO_REMOTE = "\U0001F30E Remote"
GEO_US_REMOTE = "\U0001F1FA\U0001F1F8 US — remote"
GEO_US_ONSITE = "\U0001F1FA\U0001F1F8 US — on-site (TN)"
GEO_OTHER = "\U0001F30D Other / overseas"
GEO_UNKNOWN = "❔ Unknown"

GEO_ORDER = [GEO_CA_GTA, GEO_CA_OTHER, GEO_REMOTE, GEO_US_REMOTE,
             GEO_US_ONSITE, GEO_OTHER, GEO_UNKNOWN]


def _is_gta(sl: str) -> bool:
    return bool(_GTA_CITY_RE.search(sl) and not _GTA_WITH_US_STATE_RE.search(sl))


def geo_for(loc: str | None) -> str:
    """Classify a location string into a geo/visa bucket. Canada wins when a
    Canadian anchor is present (it's reachable with no visa)."""
    s = str(loc or "").strip()
    if not s:
        return GEO_UNKNOWN
    sl = s.lower()
    remote = "remote" in sl
    if is_gta_or_canada_remote(s) or has_canada(s):
        return GEO_CA_GTA if _is_gta(sl) else GEO_CA_OTHER
    if has_us(s):
        return GEO_US_REMOTE if remote else GEO_US_ONSITE
    if remote:
        return GEO_REMOTE
    return GEO_OTHER


def tag_geo(rows: Iterable[dict]) -> Counter:
    """Add a 'geo' key to every row dict in place. Returns geo→count Counter."""
    counts: Counter = Counter()
    for r in rows:
        g = geo_for(r.get("location"))
        r["geo"] = g
        counts[g] += 1
    return counts


if __name__ == "__main__":
    for loc in ["Toronto, ON", "Remote, Canada", "Ottawa, ON", "United States (Remote)",
                "Raleigh, NC", "New York, NY", "Remote", "London, UK", ""]:
        print("%-26s -> %s" % (repr(loc), geo_for(loc)))
