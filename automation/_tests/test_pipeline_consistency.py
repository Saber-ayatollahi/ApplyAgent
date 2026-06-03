"""Unit tests for the pipeline-consistency layer.

Three things under test:

1. `fit_scorer._input_breadcrumb` — produces a stable fingerprint of the
   input scan/worklist that downstream artifacts embed via the `input`
   key. Stability requirements:
     - Identical row sets → identical sha8, regardless of row order.
     - Adding/removing/rewriting a URL → different sha8.
     - Query strings / fragments / trailing slashes / case differences
       must NOT change the sha8 (URL canonicalization).

2. `ui.pipeline_state.derive_consistency` — given on-disk worklist +
   triage + scored files, returns a `PipelineConsistency` whose
   `global_state` correctly reports `ok` / `drift_at_*` / `empty` /
   `no_breadcrumb`.

3. The keystone invariant: `_input_breadcrumb(worklist)["sha8"]` must
   equal `_worklist_sha8(worklist["results"])`. If these ever drift,
   every downstream consistency check silently returns `drift`. A
   dedicated round-trip test catches that early.

These tests run on synthetic fixtures only — no dev-environment state.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "automation"))

from ui import pipeline_state as ps  # noqa: E402
import fit_scorer  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _row(link: str, title: str = "Senior Risk Analyst",
         company: str = "Acme") -> dict:
    """Minimal worklist-row shape — only the keys the breadcrumb/consistency
    code actually reads."""
    return {"link": link, "title": title, "company": company}


def _write_worklist(out_dir: Path, rows: list[dict]) -> Path:
    p = out_dir / "worklist.json"
    p.write_text(json.dumps({"results": rows}), encoding="utf-8")
    return p


def _write_triage(out_dir: Path, *,
                  passed: int, dropped: int,
                  input_block: dict | None) -> Path:
    """Synthesize a worklist_triage.json with optional input breadcrumb.

    Passing `input_block=None` simulates a legacy file written before
    breadcrumbs existed — used to test the `no_breadcrumb` global_state."""
    payload = {
        "stage1_only": True,
        "stage1_passed": passed,
        "stage1_dropped": dropped,
        "results": [],
        "triage_drops": [],
    }
    if input_block is not None:
        payload["input"] = input_block
    p = out_dir / "worklist_triage.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _write_scored(out_dir: Path, *,
                  scored_count: int, input_block: dict | None) -> Path:
    payload = {
        "stage1_passed": scored_count,
        "stage1_dropped": 0,
        "stage2_scored": scored_count,
        "results": [],
        "triage_drops": [],
    }
    if input_block is not None:
        payload["input"] = input_block
    p = out_dir / "worklist_scored.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Layer 1 — breadcrumb stability and round-trip
# ---------------------------------------------------------------------------

class TestInputBreadcrumb:
    """`fit_scorer._input_breadcrumb` is the data the consistency check
    keys off of — its stability properties are load-bearing."""

    def test_same_rows_same_sha(self, tmp_path: Path) -> None:
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        rows = [_row("https://a.com/j/1"), _row("https://b.com/j/2")]
        a = fit_scorer._input_breadcrumb(p, rows)
        b = fit_scorer._input_breadcrumb(p, rows)
        assert a["sha8"] == b["sha8"]
        assert a["rows"] == 2

    def test_row_order_does_not_affect_sha(self, tmp_path: Path) -> None:
        """Sha is over a sorted SET, so reordering rows must be invisible —
        otherwise a no-op rewrite of worklist.json would invalidate every
        downstream cache file. Critical."""
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        rows_a = [_row("https://a.com/1"), _row("https://b.com/2"),
                  _row("https://c.com/3")]
        rows_b = list(reversed(rows_a))
        assert fit_scorer._input_breadcrumb(p, rows_a)["sha8"] \
            == fit_scorer._input_breadcrumb(p, rows_b)["sha8"]

    def test_adding_a_row_changes_sha(self, tmp_path: Path) -> None:
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        small = [_row("https://a.com/1")]
        big = small + [_row("https://b.com/2")]
        assert fit_scorer._input_breadcrumb(p, small)["sha8"] \
            != fit_scorer._input_breadcrumb(p, big)["sha8"]

    def test_url_canonicalization_collapses_noise(self, tmp_path: Path) -> None:
        """Query/fragment/trailing slash/case differences must not change the
        sha — otherwise the same job listing scraped twice would falsely
        register as drift."""
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        canonical = [_row("https://example.com/jobs/123")]
        noisy = [_row("HTTPS://Example.com/jobs/123/?utm_source=foo#section")]
        assert fit_scorer._input_breadcrumb(p, canonical)["sha8"] \
            == fit_scorer._input_breadcrumb(p, noisy)["sha8"]

    def test_empty_rows_returns_none_sha(self, tmp_path: Path) -> None:
        """Empty input → sha is None (not the hash of empty-string).
        Downstream consistency treats this as 'nothing to compare'."""
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        bc = fit_scorer._input_breadcrumb(p, [])
        assert bc["sha8"] is None
        assert bc["rows"] == 0


# ---------------------------------------------------------------------------
# The keystone invariant — writer and reader must hash identically
# ---------------------------------------------------------------------------

class TestSha8Compatibility:
    """`fit_scorer._input_breadcrumb` and `pipeline_state._worklist_sha8`
    MUST produce identical sha8 values for the same row set. If they ever
    drift, every consistency check silently lies. This is the canary test.

    These fixtures DELIBERATELY include URLs that exercise
    `worklist.norm_url`'s special cases — LinkedIn /jobs/view/<id>
    tracking redirects, Greenhouse gh_jid IDs that survive query
    stripping, Workday currentJobId, etc. A reader that uses a naive
    "strip-query-and-lowercase" canonicalizer would silently disagree
    with the writer on these URLs — exactly the bug we hit in
    production (same 2,015 rows, two different sha8s)."""

    @pytest.mark.parametrize("rows", [
        # Trivial URLs — both implementations agree even without norm_url.
        [_row("https://a.com/1")],
        [_row("https://a.com/1"), _row("https://b.com/2")],
        # Query / fragment / case noise — fallback path handles these.
        [_row("https://A.com/1/?q=1"), _row("https://b.com/2#x")],
        # LinkedIn /jobs/view/<id> with tracking — norm_url collapses to
        # bare /jobs/view/<id>; naive fallback would too (queries get
        # stripped) but the trailing-slash + case interactions can differ.
        [_row("https://www.linkedin.com/jobs/view/3829471028/"
              "?refId=abc&trk=public_jobs")],
        # Greenhouse with gh_jid — THE bug case. norm_url PRESERVES
        # gh_jid as an identity query param; naive strip-query would
        # produce a different canonical form → different sha8.
        [_row("https://boards.greenhouse.io/acme/jobs/4567?gh_jid=4567"),
         _row("https://boards.greenhouse.io/acme/jobs/4568?gh_jid=4568")],
        # Workday with currentJobId — same survival rule as gh_jid.
        [_row("https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers/"
              "job/Senior?currentJobId=R_1234")],
        # Mixed bag — the real worklist has all of these together.
        [_row("https://a.com/1"),
         _row("https://www.linkedin.com/jobs/view/12345/?trk=foo"),
         _row("https://boards.greenhouse.io/x/jobs/99?gh_jid=99")],
        [],
    ])
    def test_round_trip(self, tmp_path: Path, rows: list[dict]) -> None:
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        writer_sha = fit_scorer._input_breadcrumb(p, rows)["sha8"]
        reader_sha = ps._worklist_sha8(rows)
        assert writer_sha == reader_sha, (
            f"Writer sha8 ({writer_sha}) ≠ reader sha8 ({reader_sha}) "
            f"for rows={rows}. The two canonicalizers have drifted — "
            f"check that pipeline_state._canonicalize_link still calls "
            f"worklist.norm_url with the same fallback as fit_scorer."
        )

    def test_writer_does_not_crash_on_non_string_link(
            self, tmp_path: Path) -> None:
        """A malformed row whose link is a non-string (int/list — seen with
        corrupt scans) must NOT crash _input_breadcrumb. The breadcrumb is
        built while assembling the scored-file output dict AFTER all the LLM
        work; a raise here would discard the whole run's results."""
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        rows = [{"link": 12345}, {"link": "https://a.com/1"}]
        # Must not raise.
        bc = fit_scorer._input_breadcrumb(p, rows)
        assert bc["sha8"] is not None  # the good row still contributes

    def test_non_string_link_writer_reader_symmetric(
            self, tmp_path: Path) -> None:
        """Even for a non-string link, writer and reader must still agree —
        both wrap norm_url in try/except and fall back to the same str()
        canonical form. Guards against the asymmetry where one side drops
        the bad row and the other keeps it (→ disagreeing sha8s, the exact
        drift bug this feature exists to catch)."""
        p = tmp_path / "worklist.json"
        p.write_text("{}", encoding="utf-8")
        rows = [{"link": 12345}, {"link": "https://a.com/1"}]
        writer_sha = fit_scorer._input_breadcrumb(p, rows)["sha8"]
        reader_sha = ps._worklist_sha8(rows)
        assert writer_sha == reader_sha


# ---------------------------------------------------------------------------
# Layer 2 — derive_consistency end-to-end
# ---------------------------------------------------------------------------

class TestDeriveConsistency:
    """End-to-end: write fixture files into tmp_path, call
    `derive_consistency`, assert on the structured output. The global_state
    is the field every UI widget keys off of, so each branch needs a test."""

    def test_empty_when_no_worklist(self, tmp_path: Path) -> None:
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "empty"
        assert not c.worklist_exists

    def test_ok_when_all_breadcrumbs_match(self, tmp_path: Path) -> None:
        rows = [_row("https://a.com/1"), _row("https://b.com/2")]
        _write_worklist(tmp_path, rows)
        sha = ps._worklist_sha8(rows)
        _write_triage(tmp_path, passed=2, dropped=0,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 2, "sha8": sha})
        _write_scored(tmp_path, scored_count=2,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 2, "sha8": sha})
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "ok"
        assert c.triage.is_consistent
        assert c.scored.is_consistent
        assert c.worklist_rows == 2

    def test_drift_at_scoring_when_scored_built_against_older_worklist(
            self, tmp_path: Path) -> None:
        """The exact bug we set out to fix: worklist grew, triage was
        re-run (so it's current), but scoring was last run earlier on a
        smaller worklist. global_state must call out scoring specifically
        so the banner tells the user which stage to re-run."""
        # Current worklist is bigger
        current_rows = [_row(f"https://a.com/{i}") for i in range(10)]
        _write_worklist(tmp_path, current_rows)
        current_sha = ps._worklist_sha8(current_rows)
        # Triage was just run on the current worklist (consistent)
        _write_triage(tmp_path, passed=5, dropped=5,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 10, "sha8": current_sha})
        # Scoring was last run on a SMALLER worklist (drift)
        old_rows = current_rows[:5]
        old_sha = ps._worklist_sha8(old_rows)
        assert old_sha != current_sha
        _write_scored(tmp_path, scored_count=3,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 5, "sha8": old_sha})

        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "drift_at_scoring"
        assert c.triage.is_consistent
        assert not c.scored.is_consistent
        assert c.scored.input_rows == 5
        assert c.worklist_rows == 10

    def test_drift_at_triage_when_only_triage_lags(self, tmp_path: Path) -> None:
        current_rows = [_row(f"https://a.com/{i}") for i in range(5)]
        _write_worklist(tmp_path, current_rows)
        sha = ps._worklist_sha8(current_rows)
        old_sha = ps._worklist_sha8(current_rows[:3])
        _write_triage(tmp_path, passed=2, dropped=1,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 3, "sha8": old_sha})
        # Scoring is fresh, triage is not — unusual but possible if the
        # user re-scored after a worklist refresh but never re-triaged.
        _write_scored(tmp_path, scored_count=2,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 5, "sha8": sha})
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "drift_at_triage"

    def test_mixed_drift_when_both_stages_stale(self, tmp_path: Path) -> None:
        current_rows = [_row(f"https://a.com/{i}") for i in range(10)]
        _write_worklist(tmp_path, current_rows)
        old_sha = ps._worklist_sha8(current_rows[:3])
        _write_triage(tmp_path, passed=2, dropped=1,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 3, "sha8": old_sha})
        _write_scored(tmp_path, scored_count=2,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 3, "sha8": old_sha})
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "mixed_drift"

    def test_no_breadcrumb_when_legacy_files_lack_input_block(
            self, tmp_path: Path) -> None:
        """Files written before breadcrumbs existed (no `input` block)
        must report `no_breadcrumb`, not `drift_at_*`. We must not punish
        users for legacy artifacts."""
        rows = [_row("https://a.com/1")]
        _write_worklist(tmp_path, rows)
        _write_triage(tmp_path, passed=1, dropped=0, input_block=None)
        _write_scored(tmp_path, scored_count=1, input_block=None)
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "no_breadcrumb"

    def test_no_breadcrumb_when_only_scored_lacks_breadcrumb(
            self, tmp_path: Path) -> None:
        """Real-world transition case: user just clicked 🎯 Run triage
        (so worklist_triage.json has a fresh breadcrumb that matches the
        worklist), but worklist_scored.json is still the legacy file from
        before this fix shipped (no breadcrumb).

        Banner must NOT say ✅ "all consistent" — that would gaslight
        the user into trusting an unverifiable scored snapshot. Must
        say `no_breadcrumb` so the user knows to re-score to enable
        drift detection."""
        rows = [_row("https://a.com/1"), _row("https://b.com/2")]
        _write_worklist(tmp_path, rows)
        sha = ps._worklist_sha8(rows)
        # Triage written by the new code — has breadcrumb, consistent.
        _write_triage(tmp_path, passed=2, dropped=0,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 2, "sha8": sha})
        # Scored written before this fix — no breadcrumb.
        _write_scored(tmp_path, scored_count=2, input_block=None)
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "no_breadcrumb"

    def test_drift_beats_no_breadcrumb(self, tmp_path: Path) -> None:
        """When one stage has proven drift AND another stage lacks a
        breadcrumb, drift wins — we have something concrete to tell the
        user, don't hide behind 'unknown'."""
        rows = [_row(f"https://a.com/{i}") for i in range(5)]
        _write_worklist(tmp_path, rows)
        old_sha = ps._worklist_sha8(rows[:3])
        # Triage drifted (has breadcrumb pointing at smaller worklist).
        _write_triage(tmp_path, passed=2, dropped=1,
                      input_block={"path": "worklist.json", "mtime": 0,
                                   "rows": 3, "sha8": old_sha})
        # Scored has no breadcrumb at all.
        _write_scored(tmp_path, scored_count=1, input_block=None)
        c = ps.derive_consistency(tmp_path)
        assert c.global_state == "drift_at_triage"


# ---------------------------------------------------------------------------
# Layer 3 — banner copy is keyed off global_state
# ---------------------------------------------------------------------------

class TestBannerCopy:
    """`consistency_banner_copy` is the UI's single source of truth for
    the user-facing message. Sanity-check each branch returns the right
    severity and the headline names the right stage."""

    def test_ok_returns_success(self) -> None:
        rows = [_row("https://a.com/1")]
        sha = ps._worklist_sha8(rows)
        c = ps.PipelineConsistency(
            worklist_exists=True, worklist_rows=1, worklist_sha8=sha,
            triage=ps.StageConsistency(exists=True, input_sha8=sha,
                                       is_consistent=True),
            scored=ps.StageConsistency(exists=True, input_sha8=sha,
                                       is_consistent=True),
        )
        sev, head, _ = ps.consistency_banner_copy(c)
        assert sev == "success"
        assert "consistent" in head.lower()

    def test_drift_at_scoring_returns_warn_and_names_scoring(self) -> None:
        c = ps.PipelineConsistency(
            worklist_exists=True, worklist_rows=10, worklist_sha8="aaaaaaaa",
            triage=ps.StageConsistency(exists=True, input_sha8="aaaaaaaa",
                                       is_consistent=True, input_rows=10),
            scored=ps.StageConsistency(exists=True, input_sha8="bbbbbbbb",
                                       is_consistent=False, input_rows=5),
        )
        sev, head, detail = ps.consistency_banner_copy(c)
        assert sev == "warn"
        assert "scoring" in head.lower() or "scoring" in detail.lower()
        assert "re-score" in detail.lower()

    def test_empty_returns_info(self) -> None:
        c = ps.PipelineConsistency()
        sev, head, _ = ps.consistency_banner_copy(c)
        assert sev == "info"
        assert "worklist" in head.lower()

    def test_no_breadcrumb_names_specific_stale_stage_scoring(self) -> None:
        """When ONLY scoring is legacy (fresh triage), the banner must
        name 'scoring' (not 'snapshot files') AND point to the specific
        action button. Generic copy forces the user to hunt for what
        to fix; specific copy is the whole point of the banner."""
        sha = "abcd1234"
        c = ps.PipelineConsistency(
            worklist_exists=True, worklist_rows=2015, worklist_sha8=sha,
            triage=ps.StageConsistency(exists=True, input_sha8=sha,
                                       is_consistent=True, input_rows=2015),
            scored=ps.StageConsistency(exists=True, input_sha8=None,
                                       is_consistent=False),
        )
        sev, head, detail = ps.consistency_banner_copy(c)
        assert sev == "info"
        # Headline names the stale stage by name.
        assert "scoring" in head.lower()
        assert "triage" not in head.lower()  # don't confuse the user
        # Detail acknowledges what IS fresh + points to the specific action.
        assert "triage" in detail.lower() and "current" in detail.lower()
        assert "score worklist" in detail.lower()

    def test_no_breadcrumb_names_specific_stale_stage_triage(self) -> None:
        """Symmetric case — only triage is legacy."""
        sha = "abcd1234"
        c = ps.PipelineConsistency(
            worklist_exists=True, worklist_rows=100, worklist_sha8=sha,
            triage=ps.StageConsistency(exists=True, input_sha8=None,
                                       is_consistent=False),
            scored=ps.StageConsistency(exists=True, input_sha8=sha,
                                       is_consistent=True, input_rows=100),
        )
        sev, head, detail = ps.consistency_banner_copy(c)
        assert sev == "info"
        assert "triage" in head.lower()
        assert "scoring" not in head.lower()
        assert "scoring" in detail.lower() and "current" in detail.lower()
        assert "run triage" in detail.lower()

    def test_no_breadcrumb_both_legacy_names_both(self) -> None:
        """Both stages legacy — banner still names them by stage rather
        than the generic 'older snapshot files'."""
        sha = "abcd1234"
        c = ps.PipelineConsistency(
            worklist_exists=True, worklist_rows=100, worklist_sha8=sha,
            triage=ps.StageConsistency(exists=True, input_sha8=None,
                                       is_consistent=False),
            scored=ps.StageConsistency(exists=True, input_sha8=None,
                                       is_consistent=False),
        )
        _, head, _ = ps.consistency_banner_copy(c)
        assert "triage" in head.lower() and "scoring" in head.lower()


# ---------------------------------------------------------------------------
# derive_snapshot integration — the headline triage numbers should now
# prefer the fresher of (worklist_triage.json, worklist_scored.json)
# ---------------------------------------------------------------------------

class TestDeriveSnapshotTriageFreshness:
    """The bug the user reported: ③ Triage card showed 512/921 (from
    4d-old worklist_scored.json) while a freshly-run standalone triage
    in worklist_triage.json said 739/1276. After the fix, derive_snapshot
    must surface the FRESH numbers when the standalone triage file is
    newer than the scored snapshot."""

    def test_prefers_fresh_triage_file_when_newer(self, tmp_path: Path) -> None:
        # worklist not required for this assertion
        _write_worklist(tmp_path, [_row(f"https://a/{i}") for i in range(10)])
        # Older scored file says 100/200
        _write_scored(tmp_path, scored_count=100, input_block=None)
        # touch to make scored OLD relative to triage
        scored_path = tmp_path / "worklist_scored.json"
        sc_payload = json.loads(scored_path.read_text(encoding="utf-8"))
        sc_payload["stage1_passed"] = 100
        sc_payload["stage1_dropped"] = 200
        scored_path.write_text(json.dumps(sc_payload), encoding="utf-8")
        old_time = time.time() - 86400  # 1 day ago
        import os as _os
        _os.utime(scored_path, (old_time, old_time))
        # Fresh triage file says 739/1276 — this is what the user expects
        _write_triage(tmp_path, passed=739, dropped=1276, input_block=None)

        snap = ps.derive_snapshot(
            out_dir=tmp_path,
            fit_cache_dir=tmp_path / "fit_cache",
            tracker_path=tmp_path / "tracker.json",
        )
        assert snap.triage_passed == 739
        assert snap.triage_dropped == 1276

    def test_falls_back_to_scored_when_no_triage_file(self, tmp_path: Path) -> None:
        _write_worklist(tmp_path, [_row("https://a/1")])
        sc_path = tmp_path / "worklist_scored.json"
        sc_path.write_text(json.dumps({
            "stage1_passed": 50, "stage1_dropped": 10, "stage2_scored": 50,
            "results": [], "triage_drops": [],
        }), encoding="utf-8")
        snap = ps.derive_snapshot(
            out_dir=tmp_path,
            fit_cache_dir=tmp_path / "fit_cache",
            tracker_path=tmp_path / "tracker.json",
        )
        assert snap.triage_passed == 50
        assert snap.triage_dropped == 10

    def test_fresh_triage_with_zero_passed_still_overrides(
            self, tmp_path: Path) -> None:
        """A fresh standalone triage that legitimately passed 0 rows
        (e.g. a heavy suppression list dropped everything) must override
        the stale scored count — not fall back to it because 0 is falsy.
        Regression guard for the `or` → `is not None` fix."""
        import os as _os
        _write_worklist(tmp_path, [_row(f"https://a/{i}") for i in range(5)])
        # Older scored file says 50 passed.
        sc_path = tmp_path / "worklist_scored.json"
        sc_path.write_text(json.dumps({
            "stage1_passed": 50, "stage1_dropped": 0, "stage2_scored": 50,
            "results": [], "triage_drops": [],
        }), encoding="utf-8")
        old = time.time() - 86400
        _os.utime(sc_path, (old, old))
        # Fresh triage passed ZERO (everything dropped).
        _write_triage(tmp_path, passed=0, dropped=5, input_block=None)
        snap = ps.derive_snapshot(
            out_dir=tmp_path,
            fit_cache_dir=tmp_path / "fit_cache",
            tracker_path=tmp_path / "tracker.json",
        )
        assert snap.triage_passed == 0, \
            "fresh triage passing 0 must override stale 50, not fall back"
        assert snap.triage_dropped == 5
