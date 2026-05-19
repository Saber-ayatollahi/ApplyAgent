"""Audit: scan envelope schema, ATS endpoint health, title v2 in real data, tracker overlap."""
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(r"C:\Dev\ApplyAgent")
SCAN = ROOT / "automation" / "outputs" / "scan_20260518.json"
TRACKER = ROOT / "data" / "job_tracker_data.json"

print(f"Loading {SCAN.name} ({SCAN.stat().st_size:,} bytes)")
data = json.loads(SCAN.read_text(encoding="utf-8"))
print("Top-level keys:", list(data.keys()))
print()

jobs = data.get("results") or data.get("jobs") or data.get("rows") or []
if isinstance(data, list):
    jobs = data
print(f"Total rows: {len(jobs)}")
if jobs:
    print("Sample row keys:", sorted(jobs[0].keys()))
print()

# Schema check
url_keys = ("link", "url", "job_url")
required = ("company", "title", "location", "posted_date")
missing_url = []
missing_field = defaultdict(list)
posted_date_formats = Counter()
sample_offenders = defaultdict(list)

for j in jobs:
    has_url = any(j.get(k) for k in url_keys)
    if not has_url:
        missing_url.append(j)
    for f in required:
        if not j.get(f):
            missing_field[f].append(j)
            if len(sample_offenders[f]) < 3:
                src = j.get("source") or "?"
                co = j.get("company") or "?"
                ti = j.get("title") or "?"
                sample_offenders[f].append(f"src={src} co={co!r} title={ti!r}")
    pd = j.get("posted_date") or ""
    if pd:
        if re.match(r"^\d{4}-\d{2}-\d{2}", pd):
            posted_date_formats["ISO YYYY-MM-DD"] += 1
        elif re.match(r"^\d{4}-\d{2}-\d{2}T", pd):
            posted_date_formats["ISO with T"] += 1
        elif re.match(r"^\d+\s+(day|hour|month|week)", pd.lower()):
            posted_date_formats["relative"] += 1
        elif re.match(r"^[A-Za-z]+\s+\d", pd):
            posted_date_formats["text"] += 1
        else:
            posted_date_formats[f"other({pd[:20]!r})"] += 1
    else:
        posted_date_formats["empty"] += 1

print("=== Schema audit ===")
print(f"Rows missing ALL of {url_keys}: {len(missing_url)}")
for f in required:
    print(f"Rows missing {f!r}: {len(missing_field[f])}")
    for s in sample_offenders[f]:
        print(f"    {s}")
print()
print("posted_date format breakdown:")
for fmt, n in posted_date_formats.most_common():
    print(f"  {fmt}: {n}")
print()

# Test: does worklist's `[:10]` ISO extraction succeed?
# In worklist.py, prev_first_seen.get(u, "")[:10] is used as a date stamp
# That assumes ISO 'YYYY-MM-DD' format. Let's check.
non_iso = [j for j in jobs if j.get("posted_date") and not re.match(r"^\d{4}-\d{2}-\d{2}", j["posted_date"])]
print(f"Rows with non-ISO posted_date (worklist [:10] would garble): {len(non_iso)}")
if non_iso:
    by_src = Counter(j.get("source", "?") for j in non_iso)
    for src, n in by_src.most_common(10):
        print(f"  {src}: {n}")
    print("Examples:")
    for j in non_iso[:5]:
        print(f"  {j.get('source')!r}: posted_date={j.get('posted_date')!r}")
print()

# ATS endpoint health
print("=== Per-source counts ===")
src_count = Counter(j.get("source", "?") for j in jobs)
for src, n in src_count.most_common():
    print(f"  {src}: {n}")
print()

print("=== Per-company counts ===")
co_count = Counter((j.get("company") or "?") for j in jobs)
for co, n in co_count.most_common():
    print(f"  {co}: {n}")
print()

# diagnostics block
print("=== Diagnostics ===")
diag = data.get("diagnostics") or {}
if not diag:
    print("(no diagnostics block at top level)")
    # Maybe nested
    for k in data.keys():
        if isinstance(data[k], dict) and any(s in k.lower() for s in ("diag", "stats", "meta")):
            print(f"Found candidate at key {k!r}: {list(data[k].keys())[:10]}")
else:
    print("Keys:", list(diag.keys()))
    if "zero_result_companies" in diag:
        zrc = diag["zero_result_companies"]
        print(f"zero_result_companies ({len(zrc)}): {zrc}")
    if "per_company" in diag:
        pc = diag["per_company"]
        print(f"per_company entries: {len(pc)}")
        # Show zeroes + low ones
        zeros = []
        lows = []
        if isinstance(pc, dict):
            for co, info in pc.items():
                # info may be dict with counts or just an int
                if isinstance(info, int):
                    n = info
                elif isinstance(info, dict):
                    n = info.get("count") or info.get("total") or sum(v for v in info.values() if isinstance(v, int))
                else:
                    n = 0
                if n == 0:
                    zeros.append(co)
                elif n <= 2:
                    lows.append((co, n))
        print(f"  Companies with 0 rows: {len(zeros)}")
        for co in zeros:
            print(f"    {co}")
        print(f"  Companies with 1-2 rows: {len(lows)}")
        for co, n in lows:
            print(f"    {co}: {n}")
    # Print other keys
    for k, v in diag.items():
        if k in ("zero_result_companies", "per_company"):
            continue
        if isinstance(v, (int, float, str, bool)):
            print(f"{k}: {v}")
        elif isinstance(v, list):
            print(f"{k}: list len={len(v)}")
            if v and len(v) < 20:
                for item in v[:10]:
                    print(f"  {item}")
        elif isinstance(v, dict):
            print(f"{k}: dict keys={list(v.keys())[:15]}")
print()

# Targets vs scrape: which configured Workday tenants returned 0?
print("=== Workday tenant coverage ===")
# Read TARGETS from jd_scraper to know what was attempted
scraper_text = (ROOT / "automation" / "jd_scraper.py").read_text(encoding="utf-8")
targets_block_match = re.search(r"TARGETS = \[(.*?)\n\]", scraper_text, re.DOTALL)
configured_workday = []
configured_companies = []
if targets_block_match:
    block = targets_block_match.group(1)
    for line in block.splitlines():
        m = re.search(r'"name":\s*"([^"]+)".*?"workday":\s*(\([^)]*\)|None)', line)
        if m:
            name, wd = m.group(1), m.group(2)
            configured_companies.append(name)
            if wd != "None":
                configured_workday.append((name, wd))
print(f"Total companies in TARGETS: {len(configured_companies)}")
print(f"Workday-configured: {len(configured_workday)}")

# Which configured Workday tenants got results?
workday_company_hits = Counter()
for j in jobs:
    src = j.get("source", "")
    co = j.get("company") or ""
    if src.startswith("workday"):
        workday_company_hits[co] += 1
print(f"Workday rows by company:")
for co, n in workday_company_hits.most_common():
    print(f"  {co}: {n}")
print()

print("Workday-configured companies with ZERO Workday rows:")
hit_co_lower = {c.lower() for c in workday_company_hits.keys()}
for name, wd in configured_workday:
    found = any(name.lower() == k or name.lower() in k or k in name.lower() for k in hit_co_lower)
    if not found:
        print(f"  {name}  config={wd}")
print()

# Title v2 expansions in real data
print("=== Title v2 expansions in real data ===")
import sys
sys.path.insert(0, str(ROOT / "automation"))

def load_func(path: Path, fname: str):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"def {fname}("):
            body = [line]
            for j in range(i + 1, len(lines)):
                ln = lines[j]
                if ln and not ln.startswith((" ", "\t")) and ln.lstrip().startswith(("def ", "class ", "@")):
                    break
                body.append(ln)
            ns = {"re": re}
            exec("\n".join(body), ns)
            return ns[fname]
    return None

normalize = load_func(ROOT / "automation" / "jd_scraper.py", "_normalize_title")

raw_sr = []
raw_snr = []
raw_vp = []
raw_amp = []
for j in jobs:
    t = j.get("title") or ""
    if re.search(r"\bSr\.?\b", t):
        raw_sr.append(t)
    if re.search(r"\bSnr\b", t, re.IGNORECASE):
        raw_snr.append(t)
    if re.search(r"\bVice[\s\-]+President\b", t, re.IGNORECASE):
        raw_vp.append(t)
    if " & " in t:
        raw_amp.append(t)

print(f"Raw 'Sr ' titles: {len(raw_sr)}")
for t in raw_sr[:5]:
    print(f"  {t!r:70} -> {normalize(t)!r}")
print(f"Raw 'Snr' titles: {len(raw_snr)}")
for t in raw_snr[:5]:
    print(f"  {t!r:70} -> {normalize(t)!r}")
print(f"Raw 'Vice President' titles: {len(raw_vp)}")
for t in raw_vp[:5]:
    print(f"  {t!r:70} -> {normalize(t)!r}")
print(f"Raw ' & ' titles: {len(raw_amp)}")
for t in raw_amp[:5]:
    print(f"  {t!r:70} -> {normalize(t)!r}")
print()

# Find near-dup pairs that v2 collapses
print("=== Near-dup detection (post-v2-normalize) ===")
canonical_to_titles = defaultdict(list)
for j in jobs:
    co = (j.get("company") or "").lower().strip()
    t = j.get("title") or ""
    if not co or not t:
        continue
    nt = normalize(t)
    canonical_to_titles[(co, nt)].append((t, j.get("source", "?"), j.get("link", "")))

# Show pairs with >1 raw title that collapse to same canonical
collapsed = [(k, v) for k, v in canonical_to_titles.items() if len(v) > 1 and len({tv[0] for tv in v}) > 1]
collapsed.sort(key=lambda kv: -len(kv[1]))
print(f"Distinct (company, normalized_title) keys with multiple raw-title variants: {len(collapsed)}")
for (co, nt), items in collapsed[:15]:
    print(f"  [{co}] -> {nt!r}")
    seen_titles = set()
    for raw, src, link in items:
        if raw in seen_titles:
            continue
        seen_titles.add(raw)
        print(f"      {raw!r:60}  ({src})")
print()

# Tracker overlap
print("=== Tracker overlap ===")
if TRACKER.exists():
    tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
    tracker_urls = set()
    if isinstance(tracker, dict):
        rows = tracker.get("jobs") or tracker.get("rows") or list(tracker.values())
    elif isinstance(tracker, list):
        rows = tracker
    else:
        rows = []
    for r in rows:
        if isinstance(r, dict):
            for k in ("link", "url", "job_url", "JobURL"):
                if r.get(k):
                    tracker_urls.add(r[k])
                    break
    print(f"Tracker URLs found: {len(tracker_urls)}")
    overlap = []
    for j in jobs:
        for k in url_keys:
            u = j.get(k)
            if u and u in tracker_urls:
                overlap.append(j)
                break
    print(f"Scrape rows with URLs already in tracker: {len(overlap)}")
    if overlap:
        for j in overlap[:5]:
            print(f"  {j.get('company')!r} - {j.get('title')!r}")
else:
    print(f"(no tracker at {TRACKER})")
