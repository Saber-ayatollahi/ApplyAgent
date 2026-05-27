"""Tests for auto_promote.py --only-urls + selection_mode + suppressed_after_score.

Each test isolates auto_promote's TRACKER, OUT_DIR, suppressions paths into
tmp_path so the real data/ files are untouched. The promote run is invoked
end-to-end via auto_promote.main() with sys.argv monkey-patched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
# auto_promote falls back to `from automation import suppressions` because
# suppressions.py uses relative imports internally. Mirror that import path
# here so the monkey-patches hit the SAME module object.
sys.path.insert(0, str(AUTO.parent))  # for `import automation.*`
sys.path.insert(0, str(AUTO))          # for un-namespaced imports

import auto_promote  # noqa: E402
from automation import suppressions as supp  # noqa: E402
import tracker_migrate  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _scored_row(company: str, title: str, url: str, *,
                fit_score: int = 8, verdict: str = "apply_now",
                sector: str = "Canadian Big 6 Banks",
                location: str = "Toronto, ON",
                source: str = "scrape",
                jd_len: int = 1500) -> dict:
    return {
        "company": company,
        "title": title,
        "link": url,
        "url": url,
        "location": location,
        "sector": sector,
        "source": source,
        "_jd_len": jd_len,
        "fit": {
            "fit_score": fit_score,
            "fit_verdict": verdict,
            "tier": 2 if verdict == "tailor_and_apply" else 1,
            "summary": f"synthetic {company}",
            "top_3_reasons": ["r1", "r2", "r3"],
            "skill_gaps": [],
            "applicable_resume_variants": ["risk"],
        },
    }


def _empty_tracker(schema_version: int = 3) -> dict:
    meta = {
        "version": "2.0",
        "total_roles": 0,
        "changelog": [],
        "status_enum": [
            "Found", "Watch", "Applied", "Recruiter_Screen", "Phone_Screen",
            "Take_Home", "Onsite", "Offer", "Rejected", "Hired",
            "Withdrawn", "Expired",
        ],
    }
    if schema_version is not None:
        meta["schema_version"] = schema_version
    return {"meta": meta, "jobs": []}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect TRACKER + OUT_DIR + suppressions paths to tmp_path."""
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    tracker = data_dir / "job_tracker_data.json"
    tracker.write_text(json.dumps(_empty_tracker()), encoding="utf-8")

    monkeypatch.setattr(auto_promote, "OUT_DIR", out_dir)
    monkeypatch.setattr(auto_promote, "TRACKER", tracker)

    # Suppressions: point at tmp paths so load_active() returns empty unless
    # a test populates them via supp.add_sector / supp.add_company.
    live = data_dir / "suppressions.json"
    example = data_dir / "suppressions.example.json"
    events = data_dir / "suppressions_events.jsonl"
    history = data_dir / "suppressions_history.json"
    pending = data_dir / "suppressions_pending_archives.jsonl"
    example.write_text(
        json.dumps({"version": 1, "sectors": [], "companies": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(supp, "LIVE_PATH", live)
    monkeypatch.setattr(supp, "EXAMPLE_PATH", example)
    monkeypatch.setattr(supp, "EVENTS_PATH", events)
    monkeypatch.setattr(supp, "HISTORY_PATH", history)
    monkeypatch.setattr(supp, "PENDING_ARCHIVES_PATH", pending)

    # Make sure auto_promote uses the same module reference (it imports
    # `suppressions` lazily as `_suppressions`).
    monkeypatch.setattr(auto_promote, "_suppressions", supp)

    # Clear any pre-set snapshot env var so the default tests run against
    # the live (tmp) suppression file.
    monkeypatch.delenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", raising=False)

    return {
        "tmp": tmp_path,
        "out_dir": out_dir,
        "tracker": tracker,
        "data_dir": data_dir,
        "supp_live": live,
    }


def _write_scored(out_dir: Path, name: str, results: list[dict]) -> Path:
    path = out_dir / name
    path.write_text(
        json.dumps({"scan_date": "2026-05-26", "results": results}, indent=2),
        encoding="utf-8",
    )
    return path


def _write_urls_file(tmp_path: Path, urls: list[str], name: str = "urls.txt") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(urls), encoding="utf-8")
    return path


def _run_main(monkeypatch, argv: list[str]) -> int:
    """Invoke auto_promote.main() with argv set to (sys.argv[0], *argv)."""
    monkeypatch.setattr(sys, "argv", ["auto_promote.py", *argv])
    return auto_promote.main()


def _read_promote_report(out_dir: Path) -> dict:
    """Find the freshest promote_report_*.json and return the parsed dict."""
    candidates = sorted(out_dir.glob("promote_report_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    assert candidates, "no promote_report_*.json written"
    return json.loads(candidates[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Below-threshold rows promote in --only-urls mode
# ---------------------------------------------------------------------------

def test_only_urls_promotes_below_threshold_rows(isolated, monkeypatch):
    url = "https://example.com/jobs/below-thresh"
    rows = [_scored_row("RBC", "Risk Analyst", url, fit_score=5,
                        verdict="apply_now")]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--min-score", "7",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    assert rep["selection_mode"] == "manual"
    assert rep["summary"]["added"] == 1
    assert len(rep["promoted"]) == 1
    assert rep["promoted"][0]["selection_mode"] == "manual_below_threshold"
    # Tracker should now contain the row.
    tr = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    assert any(j["url"] == url for j in tr["jobs"])


# ---------------------------------------------------------------------------
# 2. skip-verdict rows are promoted as Watch / tier 4 with marker
# ---------------------------------------------------------------------------

def test_only_urls_promotes_skip_verdict_as_watch_tier4(isolated, monkeypatch):
    url = "https://example.com/jobs/skip-row"
    rows = [_scored_row("Acme Co", "Marketing Intern", url, fit_score=4,
                        verdict="skip", sector="Fintech")]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    assert rep["selection_mode"] == "manual"
    assert len(rep["promoted"]) == 1
    promoted = rep["promoted"][0]
    assert promoted["selection_mode"] == "manual_override_skip"
    assert promoted["tier"] == 4

    tr = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    job = next(j for j in tr["jobs"] if j["url"] == url)
    assert job["status"] == "Watch"
    assert job["urgency"] == "Low"
    assert job["tier"] == 4
    assert "manual_override_skip_verdict=true" in job.get("notes", "")


# ---------------------------------------------------------------------------
# 3. Geo gate still wins over manual selection
# ---------------------------------------------------------------------------

def test_only_urls_geo_gate_still_applies(isolated, monkeypatch):
    url = "https://example.com/jobs/nyc-job"
    rows = [_scored_row("US Bank", "Director, Risk", url, fit_score=9,
                        verdict="apply_now",
                        location="New York, NY")]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    assert rep["summary"]["added"] == 0
    assert rep["summary"]["skipped_geo"] >= 1
    tr = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    assert not any(j["url"] == url for j in tr["jobs"])


# ---------------------------------------------------------------------------
# 4. Dedupe against existing tracker row
# ---------------------------------------------------------------------------

def test_only_urls_dedupe_against_existing_tracker(isolated, monkeypatch):
    url = "https://example.com/jobs/already-there"
    # Pre-seed tracker with the same URL at higher score so dedupe wins.
    tr = _empty_tracker()
    tr["jobs"].append({
        "id": "auto-existing",
        "company": "TD",
        "title": "Risk Analyst",
        "url": url,
        "status": "Found",
        "fit_score_numeric": 9,
        "archived": False,
    })
    isolated["tracker"].write_text(json.dumps(tr), encoding="utf-8")

    rows = [_scored_row("TD", "Risk Analyst", url, fit_score=8)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    assert rep["summary"]["added"] == 0
    assert rep["summary"]["skipped_dupe"] >= 1
    skipped_reasons = [r["reason"] for r in rep["skipped_rows"]]
    assert "dupe" in skipped_reasons


# ---------------------------------------------------------------------------
# 5. Dormancy — empty suppressions + no --only-urls = legacy behavior
# ---------------------------------------------------------------------------

def test_threshold_run_with_empty_suppressions_unchanged(isolated, monkeypatch):
    # Two rows that both pass threshold + geo, plus one below-threshold to
    # exercise the existing skipped_score path.
    rows = [
        _scored_row("RBC", "VP Risk", "https://example.com/jobs/rbc-1",
                    fit_score=9, verdict="apply_now"),
        _scored_row("BMO", "Director, ALM", "https://example.com/jobs/bmo-1",
                    fit_score=8, verdict="tailor_and_apply"),
        _scored_row("Lowfit Inc", "Junior", "https://example.com/jobs/low-1",
                    fit_score=4, verdict="apply_now"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--min-score", "7",
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    assert rep["selection_mode"] == "threshold"
    assert rep["suppressed_after_score"] == []
    assert rep["summary"]["added"] == 2
    assert rep["summary"]["skipped_score"] == 1
    promoted_urls = sorted(p["url"] for p in rep["promoted"])
    assert promoted_urls == [
        "https://example.com/jobs/bmo-1",
        "https://example.com/jobs/rbc-1",
    ]
    for p in rep["promoted"]:
        assert p["selection_mode"] == "threshold"


# ---------------------------------------------------------------------------
# 6. suppressed_after_score bucket populated for race-window rows
# ---------------------------------------------------------------------------

def test_suppressed_after_score_bucket_populated(isolated, monkeypatch):
    from datetime import date, timedelta
    rows = [
        _scored_row("RBC", "VP Risk", "https://example.com/jobs/rbc-supp",
                    fit_score=9, verdict="apply_now",
                    sector="Canadian Big 6 Banks"),
        _scored_row("Other Co", "VP Risk", "https://example.com/jobs/other-1",
                    fit_score=9, verdict="apply_now",
                    sector="Fintech"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    # Add suppression AFTER scoring, BEFORE promote.
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "race-window test")

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    sup_urls = [s["url"] for s in rep["suppressed_after_score"]]
    assert "https://example.com/jobs/rbc-supp" in sup_urls
    promoted_urls = [p["url"] for p in rep["promoted"]]
    assert "https://example.com/jobs/rbc-supp" not in promoted_urls
    assert "https://example.com/jobs/other-1" in promoted_urls
    assert rep["summary"]["suppressed_after_score"] == 1


# ---------------------------------------------------------------------------
# 7. --only-url and --only-urls are mutually exclusive
# ---------------------------------------------------------------------------

def test_only_url_and_only_urls_mutually_exclusive(isolated, monkeypatch):
    url = "https://example.com/jobs/whatever"
    rows = [_scored_row("RBC", "VP", url)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--only-url", url,
        "--only-urls", str(urls_file),
    ])
    assert rc == 2  # CLI mutex error


# ---------------------------------------------------------------------------
# 8. APPLYAGENT_SUPPRESSIONS_SNAPSHOT env var is honored
# ---------------------------------------------------------------------------

def test_snapshot_env_var_consumed_when_set(isolated, monkeypatch):
    rows = [
        _scored_row("RBC", "VP Risk", "https://example.com/jobs/rbc-snap",
                    fit_score=9, sector="Canadian Big 6 Banks"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    # Snapshot file says RBC is suppressed; live file is empty.
    snap_path = isolated["data_dir"] / "snap.json"
    snap_path.write_text(json.dumps({
        "version": 1,
        "sectors": [{
            "scope": "sector",
            "name": "Canadian Big 6 Banks",
            "canonical_key": "canadian big 6 banks",
            "until": None,
            "reason": "snapshot",
            "added_at": "2026-05-26T00:00:00",
            "version": 1,
        }],
        "companies": [],
    }), encoding="utf-8")

    monkeypatch.setenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", str(snap_path))
    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    sup_urls = [s["url"] for s in rep["suppressed_after_score"]]
    assert "https://example.com/jobs/rbc-snap" in sup_urls
    assert rep["summary"]["added"] == 0


# ---------------------------------------------------------------------------
# 9. Migration runs on first commit against a v2 tracker
# ---------------------------------------------------------------------------

def test_migration_runs_on_first_commit(isolated, monkeypatch):
    legacy = {
        "meta": {
            "version": "2.0",
            "schema_version": 2,
            "changelog": [],
            "status_enum": ["Found", "Watch", "Applied", "Rejected", "Hired",
                            "Offer", "Withdrawn", "Expired"],
        },
        "jobs": [
            {"id": "legacy-1", "company": "X", "title": "Old", "status": "Found",
             "url": "https://example.com/jobs/legacy-1", "fit_score_numeric": 7},
            {"id": "legacy-2", "company": "Y", "title": "Old2", "status": "Applied",
             "url": "https://example.com/jobs/legacy-2", "fit_score_numeric": 8},
        ],
    }
    isolated["tracker"].write_text(json.dumps(legacy), encoding="utf-8")

    rows = [_scored_row("Z Corp", "Risk", "https://example.com/jobs/new-1",
                        fit_score=9)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
    ])
    assert rc == 0
    tr = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    assert tr["meta"]["schema_version"] == tracker_migrate.SCHEMA_VERSION
    for j in tr["jobs"]:
        assert j.get("archived") is False


# ---------------------------------------------------------------------------
# 10. New entries land with archived: False (forward-compat)
# ---------------------------------------------------------------------------

def test_make_entry_sets_archived_false(isolated, monkeypatch):
    rows = [_scored_row("RBC", "VP Risk", "https://example.com/jobs/new-arch",
                        fit_score=9)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
    ])
    assert rc == 0
    tr = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    promoted_job = next(j for j in tr["jobs"]
                        if j["url"] == "https://example.com/jobs/new-arch")
    assert promoted_job["archived"] is False


# ---------------------------------------------------------------------------
# 11. Mixed run: threshold-eligible + manual selections in same scored file
# ---------------------------------------------------------------------------

def test_only_urls_is_exclusive_not_additive(isolated, monkeypatch):
    """--only-urls promotes EXACTLY the URLs in the file — un-flagged
    threshold-eligible rows in the scored file do NOT slip through. This
    matches the user's mental model ('I picked these N; promote N') and
    mirrors --only-url's pre-filter behavior. Consequently, run-level
    'mixed' is unreachable via --only-urls alone; this is deliberate."""
    threshold_url = "https://example.com/jobs/thresh-eligible"
    manual_url = "https://example.com/jobs/manual-below"
    rows = [
        _scored_row("BMO", "VP Risk", threshold_url, fit_score=9,
                    verdict="apply_now"),
        _scored_row("Acme", "Junior", manual_url, fit_score=4,
                    verdict="apply_now"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)
    urls_file = _write_urls_file(isolated["tmp"], [manual_url])

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--min-score", "7",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    # Exactly one promotion: the manual_below_threshold row. The fit=9
    # threshold-eligible row was NOT in --only-urls, so it must be excluded.
    assert rep["selection_mode"] == "manual"
    promoted_modes = sorted(p["selection_mode"] for p in rep["promoted"])
    assert promoted_modes == ["manual_below_threshold"]
    promoted_urls = {p.get("url") for p in rep["promoted"]}
    assert promoted_urls == {manual_url}
    assert threshold_url not in promoted_urls


def test_only_urls_overrides_suppression_with_audit(isolated, monkeypatch):
    """Manual selection of a suppressed row PROMOTES the row with
    selection_mode=manual_override_suppression and records the override
    reason in notes + suppressed_after_score (with promoted_anyway=True).
    Mirrors fit_scorer's --only-url override behavior. Threshold rows in a
    muted sector still get dropped — the asymmetry IS the design."""
    from datetime import date, timedelta
    bank_url = "https://example.com/jobs/rbc-pick"
    rows = [
        _scored_row("RBC", "Director Risk", bank_url, fit_score=9,
                    verdict="apply_now", sector="Canadian Big 6 Banks"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "treadmill")

    urls_file = _write_urls_file(isolated["tmp"], [bank_url])
    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--only-urls", str(urls_file),
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    # Row promoted DESPITE the mute — manual selection is explicit user intent.
    assert len(rep["promoted"]) == 1
    p = rep["promoted"][0]
    assert p["url"] == bank_url
    assert p["selection_mode"] == "manual_override_suppression"
    # The override audit trail lives in the tracker row's notes field.
    tracker = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    bank_jobs = [j for j in tracker["jobs"] if j.get("url") == bank_url]
    assert len(bank_jobs) == 1
    assert "manual_override_suppression=suppressed_sector" in bank_jobs[0].get("notes", "")
    # Audit trail: suppressed_after_score records the override with the flag.
    sup = rep["suppressed_after_score"]
    assert len(sup) == 1
    assert sup[0]["url"] == bank_url
    assert sup[0]["selection_mode"] == "manual_override_suppression"
    assert sup[0]["promoted_anyway"] is True


def test_threshold_row_in_muted_sector_still_dropped(isolated, monkeypatch):
    """Verify the asymmetry: threshold rows in a muted sector get dropped
    into suppressed_after_score (NOT promoted), while manual selection of
    the same row would override (test above). Different intents,
    different precedence."""
    from datetime import date, timedelta
    bank_url = "https://example.com/jobs/rbc-thresh"
    other_url = "https://example.com/jobs/other-thresh"
    rows = [
        _scored_row("RBC", "Director Risk", bank_url, fit_score=9,
                    verdict="apply_now", sector="Canadian Big 6 Banks"),
        _scored_row("Other Co", "Director Risk", other_url, fit_score=9,
                    verdict="apply_now", sector="Fintech"),
    ]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "treadmill")

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
    ])
    assert rc == 0
    rep = _read_promote_report(isolated["out_dir"])
    promoted_urls = {p["url"] for p in rep["promoted"]}
    assert bank_url not in promoted_urls
    assert other_url in promoted_urls
    sup = rep["suppressed_after_score"]
    assert len(sup) == 1
    assert sup[0]["url"] == bank_url
    assert sup[0]["selection_mode"] == "threshold"
    assert sup[0]["promoted_anyway"] is False
