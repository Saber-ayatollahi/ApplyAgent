"""Inspect diagnostics block in detail + check workday-source-on-LinkedIn cross-coverage."""
import json
from pathlib import Path
from collections import Counter

SCAN = Path(r"C:\Dev\ApplyAgent\automation\outputs\scan_20260518.json")
data = json.loads(SCAN.read_text(encoding="utf-8"))
diag = data["diagnostics"]
per_co = diag["per_company"]

print("=== Per-company diagnostics (sample of first row) ===")
if per_co:
    print("Schema:", list(per_co[0].keys()))
    print()

# Find companies with workday config but 0 workday rows
print("=== Workday-configured companies, source breakdown ===")
print(f"{'Company':<40} {'tot':>4} {'wd':>4} {'gh':>3} {'lev':>4} {'sf':>3} {'ph':>3} {'li':>4}  flags")
for c in per_co:
    if not c.get("has_workday_config"):
        continue
    flags = []
    if c.get("workday", 0) == 0:
        flags.append("WD=0!")
    if c.get("total", 0) == 0:
        flags.append("ZERO")
    print(f"{c['name']:<40} {c.get('total',0):>4} "
          f"{c.get('workday',0):>4} {c.get('greenhouse',0):>3} "
          f"{c.get('lever',0):>4} {c.get('successfactors',0):>3} "
          f"{c.get('phenom',0):>3} {c.get('linkedin',0):>4}  {' '.join(flags)}")
print()

print("=== Companies with total=0 (all sources) ===")
for c in per_co:
    if c.get("total", 0) == 0:
        cfg = []
        if c.get("has_workday_config"): cfg.append("workday")
        if c.get("has_greenhouse_config"): cfg.append("greenhouse")
        if c.get("has_lever_config"): cfg.append("lever")
        if c.get("has_successfactors_config"): cfg.append("sf")
        if c.get("has_phenom_config"): cfg.append("phenom")
        cfg_s = ",".join(cfg) or "linkedin-only"
        print(f"  {c['name']} (configured: {cfg_s})")
print()

# Are companies that ARE Workday-configured but Workday=0 still finding jobs via LinkedIn?
print("=== Workday-config + workday=0 — what's happening? ===")
for c in per_co:
    if c.get("has_workday_config") and c.get("workday", 0) == 0:
        print(f"  {c['name']}: total={c.get('total',0)} li={c.get('linkedin',0)} other={c.get('total',0)-c.get('linkedin',0)}")
print()

# Source breakdown for the diagnostics' per_company
print("=== Total per_company validation ===")
total_per_co = sum(c.get("total", 0) for c in per_co)
print(f"sum(per_company.total) = {total_per_co}")
print(f"len(results)            = {len(data.get('results', []))}")
print(f"data['total_new_candidates'] = {data.get('total_new_candidates')}")
print(f"dedup_stats: {data.get('dedup_stats')}")
print()

# What sectors are the zero-result companies in?
print("=== Zero-result companies, sector distribution ===")
import re
scraper_text = (Path(r"C:\Dev\ApplyAgent\automation\jd_scraper.py")).read_text(encoding="utf-8")
zrc = diag.get("zero_result_companies", [])
sector_for = {}
for line in scraper_text.splitlines():
    m_name = re.search(r'"name":\s*"([^"]+)"', line)
    m_sector = re.search(r'"sector":\s*"([^"]+)"', line)
    if m_name and m_sector:
        sector_for[m_name.group(1)] = m_sector.group(1)
for co in zrc:
    print(f"  {co}  ({sector_for.get(co, '?')})")
