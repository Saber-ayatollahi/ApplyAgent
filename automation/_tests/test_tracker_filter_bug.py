"""Why does the Workday filter NOT reject 40 already-tracked URLs?
The code at line 1118: `if src_j["link"] in seen or _is_negative(src_j["title"]): continue`
And seen comes from `load_tracker_urls()` which returns {j["url"] for j in tracker.jobs if j.url}.

Hypothesis options:
A) The scan was run from a checkpoint, when tracker had FEWER URLs at scan-start.
B) The tracker was UPDATED after the scrape (new URLs added post-scan).
C) There's a real string-mismatch bug we're missing.

Check tracker timestamp, scan timestamp, tracker meta.
"""
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Dev\ApplyAgent")
SCAN = ROOT / "automation" / "outputs" / "scan_20260518.json"
TRACKER = ROOT / "data" / "job_tracker_data.json"

scan_stat = SCAN.stat()
tracker_stat = TRACKER.stat()
print(f"Scan file mtime: {datetime.fromtimestamp(scan_stat.st_mtime)}")
print(f"Tracker mtime:   {datetime.fromtimestamp(tracker_stat.st_mtime)}")
print()

scan = json.loads(SCAN.read_text(encoding="utf-8"))
tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
print(f"Scan scan_date: {scan.get('scan_date')}")
print(f"Tracker meta:   {tracker.get('meta')}")
print()

# Each tracker.job may have a "first_seen" / "added" / "Date Applied" field.
# If most overlap rows in the tracker were ADDED AFTER scan_date, that
# explains why the filter let them through — they weren't in `seen` at scan time.
# Let's check.
overlap_links = set()
seen_tracker = {j.get("url", "") for j in tracker["jobs"] if j.get("url")}
for j in scan["results"]:
    if j.get("link") and j["link"] in seen_tracker:
        overlap_links.add(j["link"])

# Map tracker URL -> tracker row
url_to_track = {j["url"]: j for j in tracker["jobs"] if j.get("url")}
print(f"Overlap URL count: {len(overlap_links)}")
print()

# Date fields on tracker rows
sample = list(overlap_links)[:5]
print("Sample tracker entries for overlap URLs:")
for u in sample:
    t = url_to_track.get(u, {})
    print(f"  url: {u}")
    date_keys = {k: v for k, v in t.items() if 'date' in k.lower() or 'added' in k.lower() or 'seen' in k.lower() or 'applied' in k.lower() or 'last' in k.lower()}
    print(f"    date fields: {date_keys}")
    print(f"    Status: {t.get('Status') or t.get('status')!r}")
    print(f"    title: {(t.get('Job Title') or t.get('title') or '')[:60]!r}")
print()

# Look at all available fields on a single tracker row
if tracker["jobs"]:
    print("Tracker row schema (keys of first job):")
    print(sorted(tracker["jobs"][0].keys()))
print()

# Group overlap by Status to understand: are these jobs that were
# applied-to AFTER the scrape? Or already-applied that should have been filtered?
from collections import Counter
status_counter = Counter()
seen_at_counter = Counter()
for u in overlap_links:
    t = url_to_track.get(u, {})
    status_counter[t.get("Status") or t.get("status") or "(none)"] += 1
    # collect any date-ish field
    for k in ("first_seen", "added", "Date Added", "Date Applied", "first_seen_at"):
        if t.get(k):
            seen_at_counter[k] += 1
print("Status distribution of overlap entries:")
for s, n in status_counter.most_common():
    print(f"  {s!r}: {n}")
print()
print("Date-field presence on overlap entries:")
for k, n in seen_at_counter.most_common():
    print(f"  {k}: {n}")
