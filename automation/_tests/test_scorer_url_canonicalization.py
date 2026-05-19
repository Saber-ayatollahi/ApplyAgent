"""Verify fit_scorer's per-URL cache key collapses tracking-param / trailing-
slash / case variants to the same hash. Audit found scorer rescored every URL
that arrived with new ?utm_source=… noise; that wasted Haiku calls and hit the
$5 daily cap mid-run on cold cache. Goal: scorer cache key matches worklist's
dedup key."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fit_scorer import _canonicalize_url, _url_hash  # type: ignore


def _expect_eq(a, b, label):
    ha, hb = _url_hash(a), _url_hash(b)
    ok = ha == hb
    print(f"  {'OK ' if ok else 'FAIL'}  {label}\n        {a!r}\n        {b!r}\n        canon: {_canonicalize_url(a)!r} vs {_canonicalize_url(b)!r}")
    assert ok, f"{label}: hashes diverged ({ha} vs {hb})"


def _expect_neq(a, b, label):
    ha, hb = _url_hash(a), _url_hash(b)
    ok = ha != hb
    print(f"  {'OK ' if ok else 'FAIL'}  {label}  (canonical: {_canonicalize_url(a)!r} / {_canonicalize_url(b)!r})")
    assert ok, f"{label}: hashes collided unexpectedly ({ha})"


def main() -> int:
    print("=" * 60)
    print("scorer URL cache-key canonicalization")
    print("=" * 60)

    # LinkedIn /jobs/view/<id> — UTM, currentJobId-style fragments, slug, mixed case
    _expect_eq(
        "https://www.linkedin.com/jobs/view/4123456789",
        "https://www.linkedin.com/jobs/view/4123456789?utm_source=newsletter&utm_medium=email",
        "LinkedIn /jobs/view: UTM stripped",
    )
    _expect_eq(
        "https://www.linkedin.com/jobs/view/4123456789#applied",
        "https://www.linkedin.com/jobs/view/4123456789",
        "LinkedIn /jobs/view: fragment stripped",
    )
    _expect_eq(
        "https://WWW.LinkedIn.com/jobs/view/4123456789",
        "https://www.linkedin.com/jobs/view/4123456789",
        "LinkedIn /jobs/view: host case-insensitive",
    )

    # Generic ATS URL (Workday/Greenhouse): query/trailing-slash/case noise
    _expect_eq(
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Senior-ALM_R-12345",
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Senior-ALM_R-12345/",
        "Workday: trailing slash",
    )
    _expect_eq(
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Senior-ALM_R-12345",
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Senior-ALM_R-12345?utm_campaign=alerts",
        "Workday: UTM stripped",
    )

    # Different jobs MUST NOT collide
    _expect_neq(
        "https://www.linkedin.com/jobs/view/4123456789",
        "https://www.linkedin.com/jobs/view/9999999999",
        "different LinkedIn job ids do not collide",
    )
    _expect_neq(
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Role-A",
        "https://rbc.wd3.myworkdayjobs.com/Careers/job/Toronto/Role-B",
        "different Workday paths do not collide",
    )

    print()
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
