"""Why does the scrape have 53 rows that are also in the tracker, given load_tracker_urls() is called?"""
import json
from pathlib import Path

ROOT = Path(r"C:\Dev\ApplyAgent")
SCAN = ROOT / "automation" / "outputs" / "scan_20260518.json"
TRACKER = ROOT / "data" / "job_tracker_data.json"

scan = json.loads(SCAN.read_text(encoding="utf-8"))
tracker = json.loads(TRACKER.read_text(encoding="utf-8"))

# Replicate jd_scraper.load_tracker_urls() exactly:
# return {j.get("url", "") for j in data.get("jobs", []) if j.get("url")}
seen = {j.get("url", "") for j in tracker.get("jobs", []) if j.get("url")}
print(f"Tracker 'jobs' rows total: {len(tracker.get('jobs', []))}")
print(f"Tracker URLs (load_tracker_urls() form): {len(seen)}")
# Sample
print("Sample tracker URLs:")
for u in list(seen)[:5]:
    print(f"  {u!r}")
print()

# What about other shapes? maybe it's dict-of-records keyed by URL
print("Tracker top-level keys:", list(tracker.keys())[:10])
print("Type of tracker['jobs']:", type(tracker.get("jobs", [])))
print()

# Now find scrape rows whose 'link' is in seen
scrape_rows = scan["results"]
overlapping = [j for j in scrape_rows if j.get("link") and j["link"] in seen]
print(f"Scrape rows with link in tracker URLs: {len(overlapping)}")

# Group by source
from collections import Counter
by_src = Counter(j.get("source", "?") for j in overlapping)
print("By source:")
for s, n in by_src.most_common():
    print(f"  {s}: {n}")
print()

# Examples
print("First 10 examples:")
for j in overlapping[:10]:
    print(f"  src={j.get('source')!r:30} {j.get('company')!r:35} {j.get('title')[:40]!r:45} {j.get('link')[:70]!r}")
print()

# CRITICAL: did load_tracker_urls() use a different key? Check what tracker really stores
print("=== Examining tracker URL storage ===")
sample_jobs = tracker.get("jobs", [])[:3]
for s in sample_jobs:
    print(f"  URL keys present: { {k: type(v).__name__ for k,v in s.items() if 'url' in k.lower() or 'link' in k.lower()} }")
    print(f"    url={s.get('url')!r}")
    print(f"    link={s.get('link')!r}")
print()

# Theory: scrape rows had url=tracker.url BEFORE the scrape's seen filter ran.
# Looking at code: filter is `if src_j["link"] in seen or _is_negative(src_j["title"])`
# So if scrape rows store under "link" and tracker stores under "url", they match
# only when tracker.url == scrape.link strings.
# Maybe gmail-route bypasses this? Or LinkedIn rows do?

# Check: is overlap mostly LinkedIn (gmail bypass) or Workday (filter should have caught)?
print("Specifically: Workday-source overlaps (these should have been filtered!)")
wd_overlap = [j for j in overlapping if j.get("source", "").startswith("workday")]
print(f"  Count: {len(wd_overlap)}")
for j in wd_overlap[:5]:
    print(f"    {j['link']}")
    print(f"    in seen? {j['link'] in seen}")
    # check whether the URL exact-matches a tracker entry
    matched_track = [t for t in tracker.get("jobs", []) if t.get("url") == j["link"]]
    print(f"    matched tracker rows: {len(matched_track)}")
    if matched_track:
        print(f"      first: {matched_track[0].get('Job Title')!r} status={matched_track[0].get('Status')!r}")
print()

# Was the scan run with --gmail flag? gmail rows bypass the seen filter manually:
# `if g["link"] in seen_tracker: continue` — so gmail SHOULD also filter
# But gmail goes through dedup which might prefer lower-rank duplicates?

# Compare URL canonicalization
print("=== URL canonicalization check ===")
# Are there scrape URLs ending in '/' or with trailing slashes that match tracker URLs without them?
from urllib.parse import urlparse
def canon(u):
    p = urlparse(u)
    return (p.scheme, p.netloc.lower(), p.path.rstrip("/"), p.query)

tracker_canon = {canon(u): u for u in seen if u}
scrape_canon = {canon(j["link"]): j for j in scrape_rows if j.get("link")}
canon_overlap = [(c, scrape_canon[c], tracker_canon[c]) for c in scrape_canon if c in tracker_canon]
print(f"Canonicalized overlap: {len(canon_overlap)}")
print(f"Strict overlap was: {len(overlapping)}")

# What about the UTM parameter or LinkedIn-trk noise?
print()
print("Comparison of strict (==) vs canonical-form mismatch:")
non_strict_only = [(c, sj, tu) for c, sj, tu in canon_overlap if sj["link"] != tu]
print(f"  Match by canonical but NOT strict (URL has different trailing/query): {len(non_strict_only)}")
for c, sj, tu in non_strict_only[:5]:
    print(f"    scrape: {sj['link']!r}")
    print(f"    track:  {tu!r}")
