#!/usr/bin/env python3
"""
url_check.py — Bulk URL liveness verifier for the job tracker.

Why this exists
---------------
Saber's memory rule: verify a JD is live BEFORE investing 2hrs tailoring.
The tracker holds 96 roles; some Tier-1 entries have a `date_jd_verified`
that is 12+ days stale. Up to now there was no script that re-checks the
URLs in bulk. This is that script.

What it does
------------
1. Reads `data/job_tracker_data.json` and selects entries whose status
   is in {Found, Watch, JD_Verified, Tailoring} (configurable).
2. Fires HEAD requests in parallel (default 10 workers, 30s hard cap each).
   Falls back to GET (stream=True, immediately closed) if HEAD returns
   405/501. Honors the project's `http_retry` retry+backoff for the GET
   fallback so a flaky 503 doesn't get mis-classified as `error`.
3. Classifies each URL as one of:
       live, redirect, 404, gone, auth_required, rate_limited,
       timeout, error
4. Writes three artefacts to `automation/outputs/`:
       url_check_<YYYYMMDD>.json   per-job result rows
       url_check_<YYYYMMDD>.md     human-readable summary + dead list
       outcome_proposals.json      append-aware proposal list (NOT a
                                   tracker mutation — feedback to the
                                   review/promote step)

5. Tracker is *only* mutated under --commit, and only via
   `safe_json.mutate_json` (atomic + cross-process safe).

CLI
---
    python automation/url_check.py --help
    python automation/url_check.py --dry-run
    python automation/url_check.py --limit 5
    python automation/url_check.py --workers 20 --statuses Watch,Found
    python automation/url_check.py --commit          # actually mutate

Design notes
------------
- We classify 401/403 as `auth_required` and explicitly never propose them
  as Expired — many ATS portals (Workday, Greenhouse, iCIMS) bounce
  unauthenticated bots with 401/403, but the JD is still live for humans.
- 429 is its own bucket so we don't blast a host that is throttling us
  AND we don't false-positive an Expired proposal.
- Redirects are followed exactly once and then re-classified, so a 301
  to a "no longer accepting applications" page lands in the right bucket.
- Output JSON write is atomic (temp + os.replace). Markdown is a single
  short text write — atomicity adds no real safety there.
- No new dependencies; stdlib + project-local `requests`/`http_retry`/`safe_json`.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# ---- Project-local imports. We support both "run as script" (where the
#      automation/ dir is on sys.path) and "run as module" (rare, but the
#      pipeline driver does it) without forcing a package layout.
ROOT = Path(__file__).resolve().parent.parent
AUTOMATION_DIR = Path(__file__).resolve().parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

try:
    from safe_json import read_json, mutate_json  # type: ignore
except ImportError as e:
    print(f"[url_check] FATAL: safe_json not importable: {e}", file=sys.stderr)
    raise

# http_retry is reused only for the GET-fallback path. HEAD requests don't
# benefit from its retry logic in the way we want (we'd rather classify a
# bad HEAD fast and fall back to GET than retry HEAD three times against
# servers that don't speak HEAD properly).
try:
    from http_retry import retry_get  # type: ignore
except ImportError:
    retry_get = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRACKER_PATH = ROOT / "data" / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"
PROPOSALS_PATH = OUT_DIR / "outcome_proposals.json"

DEFAULT_STATUSES = ("Found", "Watch", "JD_Verified", "Tailoring")
DEFAULT_WORKERS = 10
PER_URL_TIMEOUT_SEC = 30.0
USER_AGENT = "Mozilla/5.0 (compatible; ApplyAgent-URLCheck/1.0)"

# Statuses we never want to overwrite even on hard 404 — those are downstream
# of the "did we apply" decision, so a JD going dark afterwards doesn't mean
# the application is invalid.
TERMINAL_STATUSES = {
    "Applied", "Recruiter_Screen", "Phone_Screen", "Take_Home",
    "Onsite", "Offer", "Rejected", "Ghosted", "Withdrawn", "Expired",
}

# Classifications that should produce an Expired-proposal row.
DEAD_CLASSIFICATIONS = {"404", "gone"}


# ---------------------------------------------------------------------------
# Tracker selection
# ---------------------------------------------------------------------------
def select_jobs(
    tracker: dict,
    statuses: tuple[str, ...],
    limit: Optional[int] = None,
) -> list[dict]:
    """Return jobs whose status is in `statuses` and whose url is non-empty.

    We deliberately do NOT dedupe on URL here — two tracker entries can
    legitimately point at the same listing (e.g. a primary + alt source);
    they're independent rows in the output and both should be re-verified.
    """
    out: list[dict] = []
    for j in tracker.get("jobs", []):
        if j.get("status") not in statuses:
            continue
        url = (j.get("url") or "").strip()
        if not url:
            continue
        out.append(j)
        if limit is not None and len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Single-URL probe
# ---------------------------------------------------------------------------
def _classify_status(code: int) -> str:
    """Map a final HTTP status code to a verdict string. Caller handles
    redirect-following and timeouts separately."""
    if 200 <= code < 300:
        return "live"
    if 300 <= code < 400:
        # Caller normally follows redirects, so seeing 3xx here means the
        # server returned a 3xx that we chose not to follow — treat as live
        # since something is responding at the URL.
        return "redirect"
    if code == 404:
        return "404"
    if code == 410:
        return "gone"
    if code in (401, 403):
        return "auth_required"
    if code == 429:
        return "rate_limited"
    if 400 <= code < 500:
        # Treat the long tail of 4xx as 'gone' so the operator gets a
        # proposal to review — better to over-flag than under-flag.
        return "gone"
    if 500 <= code < 600:
        # 5xx is server-side; never propose Expired for these.
        return "error"
    return "error"


def _probe_once(
    session: requests.Session,
    url: str,
    method: str,
    *,
    timeout: float,
    allow_redirects: bool,
) -> requests.Response:
    """Single HEAD or GET request. GET is streamed and the body discarded
    to avoid downloading large pages just to read the status line."""
    if method == "HEAD":
        return session.head(
            url, timeout=timeout, allow_redirects=allow_redirects,
            headers={"User-Agent": USER_AGENT},
        )
    # GET path — stream + immediate close; we only need the status code.
    r = session.get(
        url, timeout=timeout, allow_redirects=allow_redirects,
        stream=True, headers={"User-Agent": USER_AGENT},
    )
    try:
        # Read at most a few bytes so the connection can be cleanly closed.
        # Some servers return a streaming body that never EOFs without this.
        next(r.iter_content(chunk_size=64), None)
    except Exception:
        pass
    finally:
        try:
            r.close()
        except Exception:
            pass
    return r


def check_url(url: str, *, timeout: float = PER_URL_TIMEOUT_SEC) -> dict:
    """Probe a single URL and return a result dict. Never raises.

    Result schema:
        {
            "url":            <str>,
            "classification": <str>,   # live | redirect | 404 | gone | ...
            "status_code":    <int|None>,
            "method":         "HEAD" | "GET",
            "final_url":      <str>,   # after redirect follow
            "redirected":     <bool>,
            "elapsed_ms":     <int>,
            "error":          <str|None>,
            "checked_at":     <ISO-8601-Z str>,
        }
    """
    started = time.monotonic()
    result: dict[str, Any] = {
        "url": url,
        "classification": "error",
        "status_code": None,
        "method": "HEAD",
        "final_url": url,
        "redirected": False,
        "elapsed_ms": 0,
        "error": None,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    session = requests.Session()
    try:
        # ---- HEAD first, no redirect-follow so we can detect & classify
        #      a 3xx explicitly. allow_redirects=False prevents requests
        #      from converting a 3xx into a 200 silently.
        try:
            r = _probe_once(session, url, "HEAD",
                            timeout=timeout, allow_redirects=False)
        except requests.Timeout:
            result["classification"] = "timeout"
            result["error"] = f"HEAD timeout >{timeout:.0f}s"
            return result
        except requests.RequestException as e:
            # DNS, SSL, connection reset, etc. Don't classify as 'gone' —
            # the operator should see these separately.
            result["classification"] = "error"
            result["error"] = f"{type(e).__name__}: {e}"
            return result

        result["status_code"] = r.status_code
        result["method"] = "HEAD"

        # ---- Many ATS systems (Workday is the worst offender) reject HEAD
        #      with 405/501. Fall back to GET in those cases. Also fall back
        #      on the rare 5xx in case it's a HEAD-specific bug.
        if r.status_code in (405, 501):
            try:
                if retry_get is not None:
                    # retry_get follows redirects by default and returns the
                    # final response. Use it for the GET fallback so we get
                    # one round of backoff for free on a transient 503.
                    r2 = retry_get(
                        url, timeout=timeout, max_tries=2,
                        headers={"User-Agent": USER_AGENT},
                        context="url_check:get_fallback",
                        allow_redirects=True,
                    )
                    if r2 is None:
                        # retry_get already logged; treat as error so a
                        # human looks at it (don't auto-Expire).
                        result["classification"] = "error"
                        result["error"] = "GET fallback failed (see error_log)"
                        result["method"] = "GET"
                        return result
                    r = r2
                else:
                    r = _probe_once(session, url, "GET",
                                    timeout=timeout, allow_redirects=True)
                result["method"] = "GET"
                result["status_code"] = r.status_code
                result["final_url"] = str(r.url) if r.url else url
                result["redirected"] = (str(r.url) != url) if r.url else False
                result["classification"] = _classify_status(r.status_code)
                return result
            except requests.Timeout:
                result["classification"] = "timeout"
                result["error"] = f"GET-fallback timeout >{timeout:.0f}s"
                result["method"] = "GET"
                return result
            except requests.RequestException as e:
                result["classification"] = "error"
                result["error"] = f"{type(e).__name__}: {e}"
                result["method"] = "GET"
                return result

        # ---- HEAD redirect: follow exactly once and re-classify.
        if 300 <= r.status_code < 400:
            loc = r.headers.get("Location")
            if not loc:
                # 3xx without a Location header — treat as live, the server
                # responded but isn't telling us where to go.
                result["classification"] = "live"
                return result
            # Resolve relative redirects.
            from urllib.parse import urljoin
            target = urljoin(url, loc)
            result["final_url"] = target
            result["redirected"] = True
            try:
                # Use GET on the redirect target — many destinations also
                # 405 on HEAD. allow_redirects=True so any further chained
                # redirects are followed in a single hop count.
                r2 = _probe_once(session, target, "GET",
                                 timeout=timeout, allow_redirects=True)
                result["method"] = "GET"
                result["status_code"] = r2.status_code
                result["final_url"] = str(r2.url) if r2.url else target
                result["classification"] = _classify_status(r2.status_code)
                return result
            except requests.Timeout:
                result["classification"] = "timeout"
                result["error"] = f"redirect-follow timeout >{timeout:.0f}s"
                return result
            except requests.RequestException as e:
                result["classification"] = "error"
                result["error"] = f"redirect-follow {type(e).__name__}: {e}"
                return result

        # ---- Plain HEAD success/failure path.
        result["classification"] = _classify_status(r.status_code)
        return result
    finally:
        result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        try:
            session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------
def run_checks(
    jobs: list[dict],
    workers: int,
    timeout: float,
) -> list[dict]:
    """Run check_url across jobs with a thread pool. Order of results
    matches the order of `jobs` so the markdown report is stable."""
    results: list[Optional[dict]] = [None] * len(jobs)
    if not jobs:
        return []

    workers = max(1, min(workers, len(jobs)))
    with cf.ThreadPoolExecutor(max_workers=workers,
                               thread_name_prefix="url-check") as pool:
        future_to_idx = {
            pool.submit(check_url, j["url"], timeout=timeout): i
            for i, j in enumerate(jobs)
        }
        for fut in cf.as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                res = fut.result()
            except Exception as e:
                # check_url shouldn't raise, but be defensive.
                res = {
                    "url": jobs[idx]["url"],
                    "classification": "error",
                    "status_code": None,
                    "method": "HEAD",
                    "final_url": jobs[idx]["url"],
                    "redirected": False,
                    "elapsed_ms": 0,
                    "error": f"runner {type(e).__name__}: {e}",
                    "checked_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                }
            res["job_id"] = jobs[idx].get("id")
            res["company"] = jobs[idx].get("company")
            res["title"] = jobs[idx].get("title")
            res["current_status"] = jobs[idx].get("status")
            results[idx] = res
    # mypy/typing: by construction every slot is filled.
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path via temp + os.replace. Used for both .md and
    .json outputs so a Ctrl-C mid-write can never leave a half-file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # Windows replace can be flaky under AV; retry a handful of times.
        for attempt in range(8):
            try:
                os.replace(tmp_path, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.02 * (2 ** attempt))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_json_report(
    path: Path,
    *,
    results: list[dict],
    summary: dict,
    args_snapshot: dict,
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "args": args_snapshot,
        "summary": summary,
        "results": results,
    }
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def render_markdown(
    *,
    results: list[dict],
    summary: dict,
    args_snapshot: dict,
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# URL liveness check — {today}",
        "",
        f"- Checked: **{summary['total']}** URLs "
        f"(workers={args_snapshot['workers']}, "
        f"statuses={','.join(args_snapshot['statuses'])})",
        "",
        "## Totals",
        "",
        "| classification | count |",
        "| --- | ---: |",
    ]
    for k in ("live", "redirect", "auth_required", "rate_limited",
              "timeout", "error", "404", "gone"):
        lines.append(f"| {k} | {summary['by_classification'].get(k, 0)} |")
    lines.append("")

    # Dead-URL list (404 + gone). This is the actionable part of the report.
    dead = [r for r in results if r["classification"] in DEAD_CLASSIFICATIONS]
    lines.append(f"## Dead URLs ({len(dead)})")
    lines.append("")
    if not dead:
        lines.append("_None — every checked URL is live, auth-walled, or transient._")
    else:
        lines.append("| job_id | company | status | code | url |")
        lines.append("| --- | --- | --- | ---: | --- |")
        for r in dead:
            lines.append(
                f"| {r.get('job_id','?')} "
                f"| {r.get('company','?')} "
                f"| {r.get('current_status','?')} "
                f"| {r.get('status_code','?')} "
                f"| {r['url']} |"
            )
    lines.append("")

    # Auth-walled list — informational only, never proposed as Expired.
    auth = [r for r in results if r["classification"] == "auth_required"]
    if auth:
        lines.append(f"## Auth-required ({len(auth)}) — not proposed as Expired")
        lines.append("")
        lines.append("| job_id | company | code | url |")
        lines.append("| --- | --- | ---: | --- |")
        for r in auth:
            lines.append(
                f"| {r.get('job_id','?')} "
                f"| {r.get('company','?')} "
                f"| {r.get('status_code','?')} "
                f"| {r['url']} |"
            )
        lines.append("")

    # Timeouts and errors — operator should eyeball these.
    sus = [r for r in results
           if r["classification"] in ("timeout", "error", "rate_limited")]
    if sus:
        lines.append(f"## Needs human eyes ({len(sus)})")
        lines.append("")
        lines.append("| job_id | classification | reason | url |")
        lines.append("| --- | --- | --- | --- |")
        for r in sus:
            reason = r.get("error") or f"HTTP {r.get('status_code')}"
            lines.append(
                f"| {r.get('job_id','?')} "
                f"| {r['classification']} "
                f"| {reason} "
                f"| {r['url']} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Proposals + (optional) tracker mutation
# ---------------------------------------------------------------------------
def build_proposals(results: list[dict], today_str: str) -> list[dict]:
    """Build the list of {Expired} proposals from dead URLs. We never propose
    a status change for jobs already in a terminal status (Applied, Offer,
    Rejected, etc.) — the URL going 404 after we applied doesn't invalidate
    the application."""
    proposals = []
    for r in results:
        if r["classification"] not in DEAD_CLASSIFICATIONS:
            continue
        if r.get("current_status") in TERMINAL_STATUSES:
            continue
        if not r.get("job_id"):
            continue
        proposals.append({
            "job_id": r["job_id"],
            "current_status": r["current_status"],
            "proposed_status": "Expired",
            "reason": f"url_check {r['classification']} on {today_str}",
            "evidence": {
                "source": "automation/url_check.py",
                "url": r["url"],
                "final_url": r.get("final_url"),
                "status_code": r.get("status_code"),
                "method": r.get("method"),
                "checked_at": r.get("checked_at"),
            },
        })
    return proposals


def _dedupe_key(p: dict) -> tuple:
    """Two proposals collide if they target the same job with the same
    proposed status from the same source. We keep the newest one."""
    return (p.get("job_id"), p.get("proposed_status"),
            p.get("evidence", {}).get("source", ""))


def append_proposals(path: Path, new_props: list[dict]) -> int:
    """Append-aware proposals merge. Reads the existing list (or [] if
    missing), drops any prior entries that collide on (job_id, status,
    source), then appends the new ones. Atomic write via the same
    safe_json plumbing the tracker uses, so two URL-check runs racing
    each other can't shred this file.

    Returns the count of NEW proposals actually written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    def _merge(current: Any) -> list[dict]:
        if not isinstance(current, list):
            current = []
        # Drop colliding old entries — the new run is authoritative.
        new_keys = {_dedupe_key(p) for p in new_props}
        kept = [p for p in current if _dedupe_key(p) not in new_keys]
        return kept + new_props

    # mutate_json gives us atomic write + cross-process lock for free.
    mutate_json(path, _merge, default=[])
    return len(new_props)


def commit_tracker_changes(proposals: list[dict]) -> tuple[int, list[str]]:
    """Apply proposals to the tracker under an exclusive lock. Returns
    (changed_count, changed_ids). Never lowers a terminal status (defense
    in depth — build_proposals already filters those out)."""
    if not proposals:
        return 0, []

    by_id = {p["job_id"]: p for p in proposals}
    changed_ids: list[str] = []

    def _apply(tracker: Any) -> Any:
        if not isinstance(tracker, dict) or "jobs" not in tracker:
            # Tracker is malformed; do nothing rather than corrupt it.
            return tracker
        for j in tracker["jobs"]:
            jid = j.get("id")
            if jid not in by_id:
                continue
            if j.get("status") in TERMINAL_STATUSES:
                continue
            j["status"] = by_id[jid]["proposed_status"]
            # Stamp a marker so a future run can attribute the change.
            j["status_changed_by"] = "url_check"
            j["status_changed_on"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%d")
            changed_ids.append(jid)
        return tracker

    mutate_json(TRACKER_PATH, _apply, default={"jobs": []})
    return len(changed_ids), changed_ids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="url_check",
        description="Bulk URL liveness verifier for the job tracker.",
    )
    p.add_argument(
        "--commit", action="store_true",
        help="Mutate the tracker for dead-URL proposals via safe_json. "
             "Default is propose-only (no tracker writes).",
    )
    p.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"Parallel HTTP workers (default {DEFAULT_WORKERS}).",
    )
    p.add_argument(
        "--statuses", type=str, default=",".join(DEFAULT_STATUSES),
        help="Comma-separated tracker statuses to check. "
             f"Default: {','.join(DEFAULT_STATUSES)}",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of URLs checked (useful for smoke tests).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan and exit. No HTTP requests, no file writes.",
    )
    p.add_argument(
        "--timeout", type=float, default=PER_URL_TIMEOUT_SEC,
        help=f"Per-URL hard cap in seconds (default {PER_URL_TIMEOUT_SEC:.0f}).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    statuses = tuple(s.strip() for s in args.statuses.split(",") if s.strip())
    if not statuses:
        print("[url_check] FATAL: --statuses cannot be empty", file=sys.stderr)
        return 2

    # Tracker selection — done up front so --dry-run can show the plan.
    tracker = read_json(TRACKER_PATH, default={"jobs": []}) or {"jobs": []}
    jobs = select_jobs(tracker, statuses, limit=args.limit)

    print(f"[url_check] tracker={TRACKER_PATH}")
    print(f"[url_check] statuses={list(statuses)} limit={args.limit}")
    print(f"[url_check] selected {len(jobs)} URLs to check "
          f"(workers={args.workers}, timeout={args.timeout:.0f}s)")
    if args.dry_run:
        # In dry-run mode, list the first ~20 URLs so the operator can
        # sanity-check the selection without firing requests.
        for j in jobs[:20]:
            print(f"  - {j.get('id'):<24} [{j.get('status')}] {j.get('url')}")
        if len(jobs) > 20:
            print(f"  ... and {len(jobs) - 20} more")
        print("[url_check] dry-run complete (no requests, no writes).")
        return 0

    if not jobs:
        print("[url_check] no jobs match selection — nothing to do.")
        return 0

    # ---- Run probes
    t0 = time.monotonic()
    results = run_checks(jobs, workers=args.workers, timeout=args.timeout)
    elapsed = time.monotonic() - t0

    # ---- Aggregate
    by_class: dict[str, int] = {}
    for r in results:
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1
    summary = {
        "total": len(results),
        "elapsed_sec": round(elapsed, 2),
        "by_classification": by_class,
    }

    # ---- Write outputs
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"url_check_{today}.json"
    md_path = OUT_DIR / f"url_check_{today}.md"

    args_snapshot = {
        "workers": args.workers,
        "statuses": list(statuses),
        "limit": args.limit,
        "timeout": args.timeout,
        "commit": bool(args.commit),
    }
    write_json_report(
        json_path,
        results=results,
        summary=summary,
        args_snapshot=args_snapshot,
    )
    _atomic_write_text(
        md_path,
        render_markdown(results=results, summary=summary,
                        args_snapshot=args_snapshot),
    )

    # ---- Proposals (always written; tracker mutation only with --commit)
    # We initialize the proposals file even when there's nothing to add so
    # downstream consumers (review UI, auto_promote) can safely `read_json`
    # without a "missing file" branch.
    proposals = build_proposals(results, today_iso)
    n_props = append_proposals(PROPOSALS_PATH, proposals)

    # ---- Optional: actually move statuses to Expired in the tracker.
    n_committed = 0
    committed_ids: list[str] = []
    if args.commit and proposals:
        n_committed, committed_ids = commit_tracker_changes(proposals)

    # ---- Console summary
    print(f"[url_check] done in {elapsed:.1f}s — "
          + " ".join(f"{k}={v}" for k, v in sorted(by_class.items())))
    print(f"[url_check] wrote {json_path.name} + {md_path.name}")
    print(f"[url_check] proposals: +{n_props} (file={PROPOSALS_PATH.name})")
    if args.commit:
        print(f"[url_check] --commit: applied {n_committed} status changes "
              f"to tracker ({', '.join(committed_ids) if committed_ids else 'none'})")
    else:
        print("[url_check] propose-only (no tracker mutation). "
              "Re-run with --commit to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
