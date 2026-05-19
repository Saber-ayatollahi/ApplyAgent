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

        print()
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
