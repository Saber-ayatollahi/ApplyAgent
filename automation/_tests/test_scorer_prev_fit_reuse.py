"""Verify fit_scorer's _load_prev_fit_index + score_with_llm second-chance
hit. Audit found is_new_since_last_score=False rows still triggered LLM calls
when the per-URL cache was orphaned (e.g. by a cache-key canonicalization
bump). Goal: cache miss + is_new_since_last_score=False + prior worklist_scored
hit -> reuse the prior fit, no LLM call, write into the new cache.
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fit_scorer  # type: ignore


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="scorer_prev_"))
    try:
        # Redirect fit_scorer's OUT_DIR + cache dirs to tmp.
        fit_scorer.OUT_DIR = tmp
        fit_scorer.JD_CACHE = tmp / "jd_cache"
        fit_scorer.FIT_CACHE = tmp / "fit_cache"

        prior_url = "https://www.linkedin.com/jobs/view/4123456789?utm_source=alert"
        unscored_url = "https://www.linkedin.com/jobs/view/9999999999"
        prior_fit = {
            "fit_score": 8, "fit_verdict": "tailor_and_apply", "tier": 2,
            "top_3_reasons": ["alm match", "treasury", "Toronto"],
            "skill_gaps": [], "summary": "Strong ALM fit, mild gap on IFRS17.",
        }
        worklist_scored = {
            "scan_date": "2026-05-18",
            "results": [
                {"link": prior_url, "title": "Senior ALM Analyst",
                 "company": "RBC", "fit": prior_fit},
            ],
        }
        (tmp / "worklist_scored.json").write_text(
            json.dumps(worklist_scored, indent=2), encoding="utf-8")

        idx = fit_scorer._load_prev_fit_index()
        # Index must be keyed by canonical URL (utm stripped, slug collapsed).
        canon = fit_scorer._canonicalize_url(prior_url)
        assert canon in idx, f"canonical URL {canon!r} not in index: {list(idx)}"
        assert idx[canon]["fit_score"] == 8
        print(f"  OK   index loaded {len(idx)} fit(s); canonical key = {canon!r}")

        # Wire the index into the module global as main() does.
        fit_scorer._prev_fit_index = idx

        # Hit path: cache file does NOT exist, role marked
        # is_new_since_last_score=False, canonical URL in index.
        # Different URL form than the index entry -> proves canonicalization works.
        role_hit = {
            # Different query string (utm_campaign vs utm_source) than the
            # prior_url — proves canonicalization strips the query before hashing.
            "link": "https://www.linkedin.com/jobs/view/4123456789?utm_campaign=foo",
            "title": "Senior ALM Analyst",
            "company": "RBC",
            "is_new_since_last_score": False,
        }
        # Pass client=None to ensure we'd crash if the LLM path is taken.
        out_hit = fit_scorer.score_with_llm(None, role_hit, "JD body...")
        assert out_hit["fit_score"] == 8, f"expected reused fit, got {out_hit}"
        cache_path = fit_scorer._cache_path_fit(role_hit["link"])
        assert cache_path.exists(), "second-chance hit should populate the new cache"
        print(f"  OK   second-chance hit reused prior fit + populated cache")

        # Miss path A: is_new_since_last_score=True -> must NOT short-circuit.
        # Sanity-check by passing a None client and confirming an exception
        # bubbles when score_with_llm tries to call the LLM (we don't reach the
        # LLM, but reaching past the second-chance branch is what we want).
        role_new = {
            "link": "https://www.linkedin.com/jobs/view/4123456789",
            "title": "Senior ALM Analyst",
            "company": "RBC",
            "is_new_since_last_score": True,
        }
        # Clear the cache file we just populated to force a real miss
        if cache_path.exists():
            cache_path.unlink()
        try:
            fit_scorer.score_with_llm(None, role_new, "JD body...")
        except Exception:
            pass  # expected — score path attempted to reach the LLM
        assert not cache_path.exists() or json.loads(cache_path.read_text())["fit_verdict"] == "error", \
            "is_new_since_last_score=True must not short-circuit to prior fit"
        print(f"  OK   is_new_since_last_score=True bypasses second-chance hit")

        # Miss path B: URL not in prior index -> must NOT short-circuit.
        role_unknown = {
            "link": unscored_url,
            "title": "New Role",
            "company": "ACME",
            "is_new_since_last_score": False,
        }
        try:
            fit_scorer.score_with_llm(None, role_unknown, "JD body...")
        except Exception:
            pass
        cache_unknown = fit_scorer._cache_path_fit(unscored_url)
        # Either cache absent (LLM call attempted and failed before write), OR
        # cache holds the error verdict — both confirm we did NOT reuse a fit.
        if cache_unknown.exists():
            data = json.loads(cache_unknown.read_text())
            assert data.get("fit_verdict") != "tailor_and_apply", \
                "unknown URL must not be served prior fit"
        print(f"  OK   unknown URL bypasses second-chance hit")

        # ---- New case (R8): .prev.json fallback when live file is missing ----
        # Wipe the live worklist_scored.json + cache and only leave a .prev.json
        # snapshot. _load_prev_fit_index must fall back to it so an interrupted
        # --rescore run (rename-to-prev succeeded, rewrite failed) doesn't
        # force paid re-scoring on the next normal run.
        live = tmp / "worklist_scored.json"
        prev_snap = tmp / "worklist_scored.prev.json"
        if live.exists():
            live.rename(prev_snap)
        else:
            prev_snap.write_text(json.dumps(worklist_scored, indent=2),
                                 encoding="utf-8")
        assert not live.exists() and prev_snap.exists()
        idx_prev = fit_scorer._load_prev_fit_index()
        assert canon in idx_prev, \
            f"prev.json fallback failed: {list(idx_prev)}"
        assert idx_prev[canon]["fit_score"] == 8
        print(f"  OK   .prev.json fallback when live worklist_scored.json absent")

        # Restore the live file for subsequent cases.
        prev_snap.rename(live)

        # ---- New case (R14a): fit_score=0 in prior fit bypasses reuse ----
        # A model parse-miss / default-fallback prior fit must NOT be reused —
        # otherwise we re-stamp the placeholder into fit_cache and skip a real
        # LLM call indefinitely.
        zero_score_fit = {
            "fit_score": 0, "fit_verdict": "tailor_and_apply", "tier": 4,
            "top_3_reasons": ["x", "y", "z"], "skill_gaps": [], "summary": "z",
        }
        zero_url = "https://www.linkedin.com/jobs/view/2222222222"
        zero_canon = fit_scorer._canonicalize_url(zero_url)
        fit_scorer._prev_fit_index = {zero_canon: zero_score_fit}
        zero_cache = fit_scorer._cache_path_fit(zero_url)
        if zero_cache.exists():
            zero_cache.unlink()
        try:
            fit_scorer.score_with_llm(
                None,
                {"link": zero_url, "title": "T", "company": "C",
                 "is_new_since_last_score": False},
                "JD body...")
        except Exception:
            pass  # expected — past second-chance, LLM path crashes on None
        # If a cache file was written, it must NOT be the placeholder fit.
        if zero_cache.exists():
            cached = json.loads(zero_cache.read_text())
            assert cached.get("fit_score") != 0 or \
                   cached.get("fit_verdict") == "error", \
                   "fit_score=0 prior fit must not be reused"
        print(f"  OK   fit_score=0 prior fit bypasses second-chance reuse")

        # ---- New case (R14b): empty top_3_reasons in prior fit bypasses reuse ----
        empty_reasons_fit = {
            "fit_score": 7, "fit_verdict": "tailor_and_apply", "tier": 2,
            "top_3_reasons": [], "skill_gaps": [], "summary": "ok",
        }
        empty_url = "https://www.linkedin.com/jobs/view/3333333333"
        empty_canon = fit_scorer._canonicalize_url(empty_url)
        fit_scorer._prev_fit_index = {empty_canon: empty_reasons_fit}
        empty_cache = fit_scorer._cache_path_fit(empty_url)
        if empty_cache.exists():
            empty_cache.unlink()
        try:
            fit_scorer.score_with_llm(
                None,
                {"link": empty_url, "title": "T", "company": "C",
                 "is_new_since_last_score": False},
                "JD body...")
        except Exception:
            pass
        if empty_cache.exists():
            cached = json.loads(empty_cache.read_text())
            # Either an error verdict (LLM crash) or NOT the empty-reason fit.
            assert cached.get("fit_verdict") == "error" or \
                   cached.get("top_3_reasons"), \
                   "empty top_3_reasons prior fit must not be reused"
        print(f"  OK   empty top_3_reasons prior fit bypasses second-chance reuse")

        # ---- New case (R14c): prev_fit_reuses counter increments on real reuse ----
        # Reset cost state, force a clean reuse, confirm the new counter ticks.
        fit_scorer._cost_state["cache_hits"] = 0
        fit_scorer._cost_state["prev_fit_reuses"] = 0
        good_url = "https://www.linkedin.com/jobs/view/4444444444"
        good_canon = fit_scorer._canonicalize_url(good_url)
        good_fit = dict(prior_fit)  # has score=8, verdict=tailor_and_apply, reasons populated
        fit_scorer._prev_fit_index = {good_canon: good_fit}
        good_cache = fit_scorer._cache_path_fit(good_url)
        if good_cache.exists():
            good_cache.unlink()
        out_good = fit_scorer.score_with_llm(
            None,
            {"link": good_url, "title": "T", "company": "C",
             "is_new_since_last_score": False},
            "JD body...")
        assert out_good["fit_score"] == 8
        assert fit_scorer._cost_state["prev_fit_reuses"] == 1, \
            f"expected prev_fit_reuses=1, got {fit_scorer._cost_state['prev_fit_reuses']}"
        assert fit_scorer._cost_state["cache_hits"] == 1
        print(f"  OK   prev_fit_reuses counter increments on real reuse")

        # ---- New case (R13): --rescore branch nulls _prev_fit_index ----
        # Direct code-inspection assertion: confirm the source contains the
        # explicit `_prev_fit_index = {}` reset inside the `if args.rescore:`
        # branch in main(). Avoids spinning up a full main() invocation just
        # to verify a 2-line guard.
        src = Path(fit_scorer.__file__).read_text(encoding="utf-8")
        rescore_idx = src.find("if args.rescore:")
        assert rescore_idx != -1, "could not find --rescore branch"
        rescore_block = src[rescore_idx:rescore_idx + 1200]
        assert "_prev_fit_index = {}" in rescore_block, \
            "--rescore branch must clear _prev_fit_index module-global"
        print(f"  OK   --rescore branch clears _prev_fit_index module-global")

        print()
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
