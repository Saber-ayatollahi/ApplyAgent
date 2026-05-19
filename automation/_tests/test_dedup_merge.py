"""Comprehensive test of worklist.py merge/dedup stage.
Read-only — does NOT modify source. Writes only to its own temp dir.
"""
from __future__ import annotations
import json
import os
import sys
import re
import shutil
import tempfile
import threading
import time
import traceback
from pathlib import Path
from datetime import datetime

# Make automation importable
HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))

import worklist  # type: ignore
from worklist import norm_url, _normalize_title, _ct_key, _LI_JOB_RE  # type: ignore
from brand_aliases import canonical_brand  # type: ignore
import jd_scraper  # type: ignore
from gmail_reader import _clean_alert_fields  # type: ignore

REPORT: list[str] = []
PASS = "PASS"
FAIL = "FAIL"


def _log(label: str, status: str, detail: str = ""):
    line = f"[{status}] {label}"
    if detail:
        line += f"  ::  {detail}"
    REPORT.append(line)
    print(line)


def check(label, got, expected):
    if got == expected:
        _log(label, PASS, f"got={got!r}")
        return True
    _log(label, FAIL, f"expected={expected!r}  got={got!r}")
    return False


# ---------------------------------------------------------------------------
# 1. norm_url() boundary cases
# ---------------------------------------------------------------------------
def test_norm_url():
    print("\n=== 1. norm_url() boundary cases ===")
    expected = "https://www.linkedin.com/jobs/view/4123456789"

    cases = [
        # (label, input link, expected)
        ("LI bare /jobs/view/<id>", "https://www.linkedin.com/jobs/view/4123456789", expected),
        ("LI bare with trailing slash", "https://www.linkedin.com/jobs/view/4123456789/", expected),
        ("LI slug form", "https://ca.linkedin.com/jobs/view/senior-risk-analyst-bmo-4123456789", expected),
        ("LI slug + trailing slash", "https://ca.linkedin.com/jobs/view/senior-risk-analyst-bmo-4123456789/", expected),
        ("LI with query string", "https://www.linkedin.com/jobs/view/4123456789?refId=abc&trackingId=xyz", expected),
        ("LI slug + query", "https://ca.linkedin.com/jobs/view/senior-risk-analyst-bmo-4123456789?refId=q", expected),
        ("LI mobile m.linkedin.com", "https://m.linkedin.com/jobs/view/4123456789", expected),
        ("LI ca.linkedin.com bare", "https://ca.linkedin.com/jobs/view/4123456789", expected),
        ("LI uk.linkedin.com bare", "https://uk.linkedin.com/jobs/view/4123456789", expected),
        ("LI mixed case path", "https://www.linkedin.com/Jobs/View/4123456789", expected),
        ("LI ALL CAPS host", "HTTPS://WWW.LINKEDIN.COM/jobs/view/4123456789", expected),
        ("LI with #apply fragment", "https://www.linkedin.com/jobs/view/4123456789#apply", expected),
        ("LI slug + fragment", "https://ca.linkedin.com/jobs/view/foo-bar-4123456789#apply", expected),
        ("LI extra path /jobs/collections/...", "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4123456789", None),
        # ^ different shape — currentJobId= rather than /jobs/view/<id>; should NOT match LI regex
        ("LI <6 digit ID guard (5 digits)", "https://www.linkedin.com/jobs/view/12345", None),
        ("LI 6 digits (boundary)", "https://www.linkedin.com/jobs/view/123456", "https://www.linkedin.com/jobs/view/123456"),
    ]
    for label, link, exp in cases:
        got = norm_url({"link": link})
        if exp is None:
            # Should NOT collapse to LinkedIn canonical form
            if "/jobs/view/" in got and got.startswith("https://www.linkedin.com/jobs/view/"):
                _log(f"norm_url {label}", FAIL, f"unexpectedly matched LI regex; got={got!r}")
            else:
                _log(f"norm_url {label}", PASS, f"correctly fell through: {got!r}")
        else:
            check(f"norm_url {label}", got, exp)

    # Workday should NOT match LI regex; should fall back to plain normalization
    wd_in = "https://mybmo.wd3.myworkdayjobs.com/External/job/Toronto-ON/Senior-Risk-Analyst_R12345?source=LinkedIn"
    wd_out_expected = "https://mybmo.wd3.myworkdayjobs.com/external/job/toronto-on/senior-risk-analyst_r12345"
    check("norm_url Workday → plain norm", norm_url({"link": wd_in}), wd_out_expected)

    # Fragments
    check("norm_url plain url + fragment", norm_url({"link": "https://example.com/jobs/abc#apply"}), "https://example.com/jobs/abc")
    # Empty/whitespace
    check("norm_url empty", norm_url({"link": ""}), "")
    check("norm_url whitespace-only", norm_url({"link": "   "}), "")
    check("norm_url None-equiv (missing keys)", norm_url({}), "")
    # Just protocol
    check("norm_url 'https://' only", norm_url({"link": "https://"}), "https:")
    # Very long URL
    long_url = "https://www.linkedin.com/jobs/view/4123456789?" + ("p=v&" * 500)
    check("norm_url very long LI", norm_url({"link": long_url}), expected)
    # Two LinkedIn-shaped IDs in one URL — regex picks first match
    twin = "https://www.linkedin.com/jobs/view/foo-9999999999/related/jobs/view/8888888888"
    got = norm_url({"link": twin})
    _log("norm_url twin-ID URL", PASS, f"first match captured: {got!r}")

    # row.url and row.job_url fallbacks
    check("norm_url uses row['url']", norm_url({"url": "https://example.com/x"}), "https://example.com/x")
    check("norm_url uses row['job_url']", norm_url({"job_url": "https://example.com/y"}), "https://example.com/y")
    # priority — link beats url beats job_url
    check("norm_url 'link' takes priority over 'url'",
          norm_url({"link": "https://a.com/a", "url": "https://b.com/b"}),
          "https://a.com/a")

    # Case sensitivity issue probe: Workday URLs with case-significant IDs
    # If a Workday URL has "_R12345" vs "_r12345", they'll be mismatched
    # because plain norm lowercases.
    a = norm_url({"link": "https://x.wd3.myworkdayjobs.com/job/R12345"})
    b = norm_url({"link": "https://x.wd3.myworkdayjobs.com/job/r12345"})
    if a == b:
        _log("Workday case-fold collision (intended)", PASS, f"both → {a!r}")
    else:
        _log("Workday case-fold collision", FAIL, f"a={a!r} b={b!r}")


# ---------------------------------------------------------------------------
# 2. _normalize_title() lockstep with jd_scraper
# ---------------------------------------------------------------------------
def test_normalize_title_lockstep():
    print("\n=== 2. _normalize_title() lockstep with jd_scraper ===")
    cases = [
        "Senior Risk Analyst (Hybrid)",
        "Sr. Risk Analyst, AVP",
        "Sr Risk Analyst",
        "Snr Risk Analyst",
        "Vice President, ALM",
        "Vice-President, ALM",
        "Vice  President   Capital",
        "Risk & Capital Manager",
        "Risk/Capital Manager",
        "Risk Analyst — Toronto, ON",
        "Risk Analyst - Toronto, ON",
        "Risk Analyst (123456)",
        "Risk Analyst (12)",  # too short → not stripped
        "Risk Analyst (Permanent, Full-time)",
        "Director, ALM (Remote)",
        "Senior Manager - Treasury & Capital",
        "ALM Director, VP",
        "VP, Risk Management",
        "Mgr, Risk",  # no expansion for "Mgr"
    ]
    drift = 0
    for title in cases:
        a = _normalize_title(title)
        b = jd_scraper._normalize_title(title)
        if a == b:
            _log(f"lockstep {title!r}", PASS, f"both={a!r}")
        else:
            _log(f"lockstep {title!r}", FAIL, f"worklist={a!r}  jd_scraper={b!r}")
            drift += 1

    # Specific expansions
    check("Sr. → senior", _normalize_title("Sr. Analyst"), "senior analyst")
    check("Sr → senior", _normalize_title("Sr Analyst"), "senior analyst")
    check("Snr → senior", _normalize_title("Snr Analyst"), "senior analyst")
    check("Vice President → vp", _normalize_title("Vice President of Risk"),
          "vp of risk")
    check("Vice-President → vp", _normalize_title("Vice-President of Risk"),
          "vp of risk")
    check("& → and", _normalize_title("Risk & Capital"), "risk and capital")
    check("Title-case Sr capital", _normalize_title("Sr Risk Analyst"), "senior risk analyst")
    # idempotent
    once = _normalize_title("Senior Risk Analyst (Hybrid)")
    twice = _normalize_title(once)
    check("idempotent", twice, once)
    # req-id stripping
    check("req-id (123456) stripped", _normalize_title("Risk Analyst (123456)"), "risk analyst")
    # mid-string number — should NOT be stripped (only trailing)
    check("non-trailing num NOT stripped", _normalize_title("Analyst (123) Toronto"),
          jd_scraper._normalize_title("Analyst (123) Toronto"))

    # Equivalence pairs that should produce same key
    eq_pairs = [
        ("Senior Risk Analyst", "Sr Risk Analyst"),
        ("Senior Risk Analyst", "Sr. Risk Analyst"),
        ("Senior Risk Analyst", "Snr Risk Analyst"),
        ("VP, ALM", "Vice President, ALM"),
        ("Risk and Capital Manager", "Risk & Capital Manager"),
        # The following are challenging — investigate behaviour:
        ("Senior Analyst, AVP", "Sr Analyst, Assistant Vice President"),  # AVP != "Assistant VP" expansion
    ]
    for a, b in eq_pairs:
        na = _normalize_title(a)
        nb = _normalize_title(b)
        ok = (na == nb)
        status = PASS if ok else FAIL
        _log(f"equiv {a!r} == {b!r}", status, f"a={na!r}  b={nb!r}")

    if drift:
        _log(f"LOCKSTEP DRIFT count = {drift}", FAIL,
             "worklist.py vs jd_scraper.py disagree on at least one title")
    else:
        _log("LOCKSTEP DRIFT count = 0", PASS, "all sample titles agree")


# ---------------------------------------------------------------------------
# 3. _ct_key() combined behaviour
# ---------------------------------------------------------------------------
def test_ct_key():
    print("\n=== 3. _ct_key() combined behaviour ===")
    a = _ct_key("BMO", "Sr Analyst")
    b = _ct_key("Bank of Montreal", "Senior Analyst")
    c = _ct_key("BMO Financial Group", "Senior Analyst")
    d = _ct_key("BMO Capital Markets", "Sr. Analyst")
    print(f"  a={a!r}  b={b!r}  c={c!r}  d={d!r}")
    if a == b == c == d:
        _log("BMO/BoM/BMO Fin Group/BMO Cap Mkts all collapse", PASS, f"all → {a!r}")
    else:
        _log("BMO/BoM/BMO Fin Group/BMO Cap Mkts collapse", FAIL,
             f"a={a!r} b={b!r} c={c!r} d={d!r}")

    check("ct_key empty company → None", _ct_key("", "Senior Analyst"), None)
    check("ct_key None company → None", _ct_key(None, "Senior Analyst"), None)
    check("ct_key empty title → None", _ct_key("BMO", ""), None)
    check("ct_key both empty → None", _ct_key("", ""), None)

    # Generic-only company: does fallback collapse different companies?
    g1 = _ct_key("The Company Inc", "Senior Analyst")
    g2 = _ct_key("Company Limited", "Senior Analyst")
    g3 = _ct_key("Group Holdings Inc", "Senior Analyst")
    print(f"  generic1={g1!r}  generic2={g2!r}  generic3={g3!r}")
    if g1 is None and g2 is None and g3 is None:
        _log("generic-only company → None (best)", PASS)
    else:
        # Whatever the fallback returns, do they collapse onto each other?
        rows = [g1, g2, g3]
        rows = [r for r in rows if r is not None]
        if len(set(rows)) > 1:
            _log("generic-only fallback differentiates them", PASS, f"{rows}")
        else:
            _log("generic-only fallback collapses unrelated companies", FAIL,
                 f"all → {rows[0]!r} (would merge unrelated firms with same title)")

    # TD Synnex (an IT distributor, NOT TD Bank)
    td_synnex = canonical_brand("TD Synnex")
    td_bank = canonical_brand("TD Bank")
    if td_synnex == td_bank:
        _log("TD Synnex → 'td' (FALSE COLLAPSE onto TD Bank)", FAIL,
             f"both → {td_synnex!r}; risk: 'TD Synnex' postings would merge with 'TD Bank' postings")
    else:
        _log("TD Synnex distinct from TD Bank", PASS,
             f"td_synnex={td_synnex!r} td_bank={td_bank!r}")
    # Also probe: "TD Insurance" should be TD; "TD Synnex" shouldn't.
    print(f"  canonical_brand('TD Insurance')={canonical_brand('TD Insurance')!r}")
    print(f"  canonical_brand('TD Asset Management')={canonical_brand('TD Asset Management')!r}")

    # More potential false collapses
    probes = [
        "Capital One",          # has "capital" (generic) → may fall to "one"
        "Capital Group",        # has "capital", "group" both generic
        "Bain Capital",         # different from Bain & Co (consultancy)
        "RBC Royal Bank",
        "Royal Caribbean",      # not a bank — but has "royal"
        "Bank of America",      # not in alias map — falls back
        "Bank of New York Mellon",
        "Sun Country Airlines", # has "sun" — could collide with sun life?
        "EY Asset Management",  # could match "ey" prefix
        "Citi Habitats",        # has "citi" prefix → might collapse onto citi
        "Citizen Bank",         # has "citi" prefix issue?
        "Goldman Sachs Asset Management",
        "HSBC Securities Inc",
        "Definity Insurance Co",
        "Intact Mfg Inc",       # Intact — could falsely match the alias
        "Manulife Real Estate",
        "Industrial Alliance Securities",
        "JP Morgan Asset Management",
    ]
    for p in probes:
        cb = canonical_brand(p)
        print(f"  canonical_brand({p!r}) → {cb!r}")
    # Specific concern: does "Citi Habitats" → "citi"? That'd be a false collapse.
    if canonical_brand("Citi Habitats") == "citi":
        _log("Citi Habitats false collapse onto 'citi'", FAIL,
             "Citi Habitats is a real-estate firm, not Citigroup")
    # Capital One probes
    cap_one = canonical_brand("Capital One")
    if cap_one == canonical_brand("Capital One Bank"):
        print(f"  Capital One stable: {cap_one!r}")


# ---------------------------------------------------------------------------
# 4. rebuild() end-to-end with synthetic inputs
# ---------------------------------------------------------------------------
def test_rebuild_end_to_end():
    print("\n=== 4. rebuild() end-to-end ===")
    tmp = Path(tempfile.mkdtemp(prefix="worklist_test_"))
    try:
        # Backup-and-redirect
        old_out = worklist.OUT_DIR
        old_wl = worklist.WORKLIST
        old_wls = worklist.WORKLIST_SCORED
        old_legacy = worklist.LEGACY_DIR

        worklist.OUT_DIR = tmp
        worklist.WORKLIST = tmp / "worklist.json"
        worklist.WORKLIST_SCORED = tmp / "worklist_scored.json"
        worklist.LEGACY_DIR = tmp / "_legacy"

        try:
            # Build synthetic inputs
            web_rows = [
                # row 1: scrape only — Workday URL for BMO Senior Risk Analyst
                {"link": "https://mybmo.wd3.myworkdayjobs.com/External/job/Toronto-ON/Senior-Risk-Analyst_R12345",
                 "company": "BMO", "title": "Senior Risk Analyst",
                 "posted_date": "2026-05-10"},
                # row 2: scrape only — TD Director, ALM
                {"link": "https://jobs.td.com/job/12345-Director-ALM-Toronto",
                 "company": "TD Bank", "title": "Director, ALM",
                 "posted_date": "2026-05-12"},
                # row 3: shares URL with gmail row below
                {"link": "https://www.linkedin.com/jobs/view/4123456789",
                 "company": "RBC", "title": "Senior Risk Analyst",
                 "posted_date": "2026-05-13"},
            ]
            gmail_rows = [
                # G1: same canonical URL as web row 3 (slug form) — should merge to "both"
                {"link": "https://ca.linkedin.com/jobs/view/senior-risk-analyst-rbc-4123456789",
                 "company": "Royal Bank of Canada", "title": "Sr Risk Analyst",
                 "posted_date": "2026-05-14"},
                # G2: shares (brand,title) with web row 1 but different URL
                #     — should merge via _ct_key to "both"
                {"link": "https://ca.linkedin.com/jobs/view/senior-risk-analyst-bmo-4444444444",
                 "company": "Bank of Montreal", "title": "Sr Risk Analyst",
                 "posted_date": "2026-05-14"},
                # G3: gmail-only — different role
                {"link": "https://ca.linkedin.com/jobs/view/treasury-mgr-citi-5555555555",
                 "company": "Citi", "title": "Treasury Manager",
                 "posted_date": "2026-05-15"},
                # G4: gmail-only — also different role
                {"link": "https://ca.linkedin.com/jobs/view/risk-analyst-cibc-6666666666",
                 "company": "CIBC", "title": "Risk Analyst",
                 "posted_date": "2026-05-16"},
                # G5: contaminated row — company has "BMO · Toronto, ON" pattern
                # Should be cleaned via _clean_alert_fields before being added.
                {"link": "https://ca.linkedin.com/jobs/view/risk-mgr-bmo-7777777777",
                 "company": "BMO · Toronto, ON · 23 connections",
                 "title": "Risk Manager",
                 "posted_date": "2026-05-16"},
            ]
            today = datetime.now().strftime("%Y%m%d")
            (tmp / f"scan_{today}.json").write_text(
                json.dumps({"results": web_rows}), encoding="utf-8")
            (tmp / f"scan_gmail_{today}_120000.json").write_text(
                json.dumps({"results": gmail_rows}), encoding="utf-8")

            # 1st rebuild
            stats = worklist.rebuild(quarantine=False)
            print(f"  stats after 1st rebuild: {stats}")

            # Total: 3 web + 5 gmail = 8 raw inputs; expected unique:
            #   web1+G2 merge (BMO Senior Risk Analyst via _ct_key)
            #   web3+G1 merge (LinkedIn URL canonical)
            #   web2 alone (Director, ALM)
            #   G3 alone (Treasury Manager)
            #   G4 alone (Risk Analyst CIBC)
            #   G5 alone (Risk Manager BMO — different title)
            # Expected: 6 rows, 2 with source=both (web1↔G2 and web3↔G1)
            check("rebuild total rows", stats["total"], 6)
            check("rebuild both count", stats["both"], 2)
            # web2, G3, G4, G5 are single-source. web2 is scrape-only;
            # G3/G4/G5 are gmail-only. So scrape=1, gmail=3
            # (web1 and web3 became "both")
            check("rebuild scrape count", stats["scrape"], 1)
            check("rebuild gmail count", stats["gmail"], 3)

            env1 = json.loads((tmp / "worklist.json").read_text())
            urls1 = {r["link"]: r for r in env1["results"]}
            print(f"  rows after 1st rebuild:")
            for r in env1["results"]:
                print(f"    {r['source']:7s}  {r.get('company','?'):30s}  "
                      f"{r.get('title','?'):40s}  first_seen={r.get('first_seen')}")

            # Check the cleaned BMO row (G5) has clean company name
            bmo_g5 = [r for r in env1["results"] if "7777777777" in (r.get("link") or "")]
            if bmo_g5:
                cleaned = bmo_g5[0].get("company", "")
                if cleaned == "BMO":
                    _log("Gmail row contamination cleaned in rebuild", PASS,
                         f"company={cleaned!r}")
                else:
                    _log("Gmail row contamination cleaned in rebuild", FAIL,
                         f"company={cleaned!r} expected 'BMO'")

            # first_seen preservation: 2nd rebuild should keep original first_seen
            # Simulate "tomorrow" by altering posted_date in inputs
            web_rows2 = list(web_rows)
            web_rows2[0] = {**web_rows[0], "posted_date": "2026-06-01"}
            (tmp / f"scan_{today}.json").write_text(
                json.dumps({"results": web_rows2}), encoding="utf-8")
            stats2 = worklist.rebuild(quarantine=False)
            env2 = json.loads((tmp / "worklist.json").read_text())
            for r in env2["results"]:
                u_old = next((x for x in env1["results"] if x.get("link") == r.get("link")), None)
                if u_old and u_old.get("first_seen") != r.get("first_seen"):
                    _log("first_seen NOT preserved across rebuilds", FAIL,
                         f"url={r.get('link')!r} old={u_old.get('first_seen')!r} new={r.get('first_seen')!r}")
                    break
            else:
                _log("first_seen preserved across rebuilds", PASS)

            # is_new_since_last_score: write a synthetic worklist_scored.json
            # containing a SUBSET of the URLs, then rebuild.
            scored_subset = {
                "results": [
                    # only RBC senior risk analyst was scored
                    {"link": "https://www.linkedin.com/jobs/view/4123456789"},
                ]
            }
            (tmp / "worklist_scored.json").write_text(
                json.dumps(scored_subset), encoding="utf-8")
            stats3 = worklist.rebuild(quarantine=False)
            env3 = json.loads((tmp / "worklist.json").read_text())
            new_count = sum(1 for r in env3["results"] if r.get("is_new_since_last_score"))
            previously_scored = sum(1 for r in env3["results"] if not r.get("is_new_since_last_score"))
            print(f"  new_since_last_score={new_count}  previously_scored={previously_scored}")
            # 6 total, 1 was previously scored ⇒ 5 new
            check("is_new_since_last_score count", new_count, 5)
            check("previously_scored count", previously_scored, 1)
            # The RBC row should be marked NOT new
            for r in env3["results"]:
                if "4123456789" in (r.get("link") or ""):
                    if r.get("is_new_since_last_score") == False:
                        _log("Previously scored URL flag flipped correctly", PASS)
                    else:
                        _log("Previously scored URL flag flipped correctly", FAIL,
                             f"is_new_since_last_score={r.get('is_new_since_last_score')}")

        finally:
            worklist.OUT_DIR = old_out
            worklist.WORKLIST = old_wl
            worklist.WORKLIST_SCORED = old_wls
            worklist.LEGACY_DIR = old_legacy

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. _atomic_write_json — fsync, crash-mid-write, race window
# ---------------------------------------------------------------------------
def test_atomic_write():
    print("\n=== 5. _atomic_write_json ===")
    tmp = Path(tempfile.mkdtemp(prefix="atomic_test_"))
    try:
        target = tmp / "worklist.json"
        # Pre-populate so we can verify it isn't truncated on crash
        target.write_text('{"version":0,"results":[{"keep":"me"}]}', encoding="utf-8")
        original_content = target.read_text(encoding="utf-8")

        # (a) Verify fsync is called — inspect source
        src = (Path(__file__).resolve().parent.parent / "worklist.py").read_text(encoding="utf-8")
        if "os.fsync(" in src and "f.flush()" in src and "os.replace(" in src:
            _log("atomic write uses flush + fsync + replace", PASS,
                 "all three primitives present in source")
        else:
            _log("atomic write uses flush + fsync + replace", FAIL,
                 f"flush={'f.flush()' in src} fsync={'os.fsync(' in src} replace={'os.replace(' in src}")

        # (b) Crash-mid-write simulation: monkey-patch json.dump to raise.
        import json as _json
        orig_dump = _json.dump

        def _raise_mid_write(*a, **kw):
            raise RuntimeError("simulated crash mid-write")

        _json.dump = _raise_mid_write
        try:
            try:
                worklist._atomic_write_json(target, {"version": 99})
                _log("crash mid-write raised", FAIL, "no exception was raised")
            except RuntimeError as e:
                _log("crash mid-write raised", PASS, f"caught {e}")
        finally:
            _json.dump = orig_dump

        # Did the original file survive?
        survived = target.read_text(encoding="utf-8")
        if survived == original_content:
            _log("crash mid-write left previous file intact", PASS)
        else:
            _log("crash mid-write left previous file intact", FAIL,
                 f"len(orig)={len(original_content)} len(post)={len(survived)}")

        # Are there any leftover .tmp files?
        leftovers = list(target.parent.glob("worklist.json.*.tmp"))
        if not leftovers:
            _log("no orphan .tmp file after crash", PASS)
        else:
            _log("no orphan .tmp file after crash", FAIL,
                 f"orphans: {[p.name for p in leftovers]}")

        # (c) Race window: while a writer is calling _atomic_write_json,
        # a reader should always see EITHER the old file OR the new file —
        # never a half-written one.
        # Install a slow encoder by monkey-patching json.dump to sleep
        # mid-serialize, then start a writer thread and a reader loop.
        target.write_text('{"version":1}', encoding="utf-8")

        slow_state = {"in_write": False}
        orig_dump2 = _json.dump

        def _slow_dump(obj, fp, *a, **kw):
            slow_state["in_write"] = True
            res = orig_dump2(obj, fp, *a, **kw)
            time.sleep(0.4)  # before flush+fsync+replace
            slow_state["in_write"] = False
            return res

        _json.dump = _slow_dump
        race_failures = []
        stop = threading.Event()

        def _reader():
            while not stop.is_set():
                try:
                    txt = target.read_text(encoding="utf-8")
                    json.loads(txt)  # should always parse
                except Exception as e:
                    race_failures.append(repr(e))
                time.sleep(0.01)

        try:
            t = threading.Thread(target=_reader, daemon=True)
            t.start()
            # write a much larger payload while reader spins
            payload = {"version": 2, "results": [{"k": "v" * 100}] * 200}
            worklist._atomic_write_json(target, payload)
            time.sleep(0.05)
            stop.set()
            t.join(timeout=2)
        finally:
            _json.dump = orig_dump2

        if not race_failures:
            _log("reader never saw half-written JSON during write", PASS,
                 "0 parse errors")
        else:
            _log("reader never saw half-written JSON during write", FAIL,
                 f"{len(race_failures)} errors: {race_failures[:3]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Brand-alias false collapses
# ---------------------------------------------------------------------------
def test_brand_alias_false_collapses():
    print("\n=== 6. Brand alias false collapses ===")
    # Curated list of risky inputs: companies whose names start with a
    # known alias prefix but are unrelated firms.
    risky = [
        # (input, what we hope it returns, comment)
        ("TD Synnex", "tdsynnex", "IT distributor, NOT TD Bank"),
        ("TD Ameritrade", "td", "actually IS a TD company — collapse OK"),
        ("Citi Habitats", "citihabitats", "real estate, NOT Citi"),
        ("Bain Capital", "bain", "PE arm; behaves OK with current map?"),
        ("Bank of America", None, "should NOT collapse onto BMO/Boc"),
        ("Bank of New York Mellon", None, "should NOT collapse onto BMO/Boc"),
        ("Sun Country Airlines", None, "starts with 'sun' — Sun Life prefix risk"),
        ("Sun Microsystems", None, "starts with 'sun' — Sun Life prefix risk"),
        ("Royal Caribbean", None, "starts with 'royal' — RBC prefix risk"),
        ("Goldman Environmental Prize", None, "starts with 'goldman' but unrelated"),
        ("HSBC Hong Kong", "hsbc", "real HSBC arm — collapse OK"),
        ("Citizen Bank", None, "starts with 'citi'? NO — 'citizen' starts diff."),
        ("Definity Healthcare", None, "starts with 'definity' but unrelated"),
        ("Intact Software", None, "starts with 'intact' but a software firm"),
        ("Manulife Real Estate", "manulife", "real Manulife arm — collapse OK"),
        ("National Bank of Greece", None, "starts with 'national bank' — NBC alias risk"),
        ("National Bank of Egypt", None, "same prefix risk"),
        ("EY Asset Management", "ey", "real EY arm"),
        ("Ernst & Young Hong Kong", "ey", "real EY arm"),
    ]
    found_false = []
    for name, hoped, note in risky:
        got = canonical_brand(name)
        # Identify outright false collapses
        # (where input collapses onto a base brand it doesn't belong to)
        bases = {"bmo", "rbc", "td", "cibc", "scotia", "nbc", "manulife",
                 "sunlife", "canadalife", "intact", "definity", "ia",
                 "fairfax", "cppib", "omers", "otpp", "hoopp", "imco",
                 "psp", "cdpq", "caat", "citi", "jpmorgan", "morganstanley",
                 "goldman", "deutsche", "hsbc", "barclays", "ubs",
                 "creditsuisse", "deloitte", "ey", "kpmg", "pwc",
                 "mckinsey", "bcg", "bain", "accenture", "osfi", "boc",
                 "fsra", "osc"}
        # Did the lookup pull a base brand alias when it shouldn't?
        if hoped is None and got in bases:
            found_false.append((name, got, note))
            _log(f"FALSE COLLAPSE: {name!r}", FAIL,
                 f"→ {got!r}  ({note})")
        else:
            _log(f"alias check {name!r}", PASS, f"→ {got!r}  ({note})")

    if found_false:
        _log(f"FALSE COLLAPSE TOTAL = {len(found_false)}", FAIL,
             "; ".join(f"{n}→{g}" for n, g, _ in found_false))
    else:
        _log("FALSE COLLAPSE TOTAL = 0", PASS,
             "no risky prefix collapses observed")

    # Also test the fallback path: a totally novel company name
    print(f"  canonical_brand('Onex Corporation') → {canonical_brand('Onex Corporation')!r}")
    print(f"  canonical_brand('Brookfield Asset Management') → {canonical_brand('Brookfield Asset Management')!r}")
    print(f"  canonical_brand('The Wealth Group Inc.') → {canonical_brand('The Wealth Group Inc.')!r}")
    print(f"  canonical_brand('') → {canonical_brand('')!r}")
    print(f"  canonical_brand(None) → {canonical_brand(None)!r}")


# ---------------------------------------------------------------------------
def main():
    tests = [
        test_norm_url,
        test_normalize_title_lockstep,
        test_ct_key,
        test_rebuild_end_to_end,
        test_atomic_write,
        test_brand_alias_false_collapses,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            tb = traceback.format_exc()
            _log(f"TEST CRASHED: {t.__name__}", FAIL, f"{e}\n{tb}")

    print("\n=== SUMMARY ===")
    pass_count = sum(1 for line in REPORT if line.startswith("[PASS]"))
    fail_count = sum(1 for line in REPORT if line.startswith("[FAIL]"))
    print(f"PASS: {pass_count}  FAIL: {fail_count}")
    if fail_count:
        print("\nFAILURES:")
        for line in REPORT:
            if line.startswith("[FAIL]"):
                print("  " + line)


if __name__ == "__main__":
    main()
