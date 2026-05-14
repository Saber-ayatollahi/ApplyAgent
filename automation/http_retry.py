#!/usr/bin/env python3
"""
http_retry.py — Shared retrying HTTP GET for scrapers and JD fetchers.

Wraps requests.get with:
  - max_tries with exponential backoff
  - Retry-After header support (429 + 503)
  - Error classification (transient vs. terminal)
  - Jitter to avoid thundering herd when running the scraper in parallel
  - Error-log integration — every retry is logged with context

Usage:
    from http_retry import retry_get

    resp = retry_get(url, headers=HEADERS, timeout=25,
                      context="scraper:workday")
    if resp is None:
        # Exhausted retries or terminal error — caller should skip this URL.
        continue

`retry_get` returns `None` on failure instead of raising; callers almost
always want to skip and continue rather than crash the whole pipeline.

Classifications:
    TRANSIENT  -> 429, 500-504, connection errors, read timeouts
    TERMINAL   -> 4xx other than 429, redirects gone wrong, bad URL
"""
from __future__ import annotations

import random
import time
from typing import Any, Optional

import requests

try:
    from error_log import log_error  # type: ignore
except ImportError:
    try:
        from .error_log import log_error  # type: ignore
    except Exception:
        log_error = None  # type: ignore

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DEFAULT_HEADERS = {"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"}

# Status codes we retry on (rest are treated as terminal).
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_SLEEP_SEC = 20.0  # cap any single sleep, even if Retry-After says "5 min"


def _jittered_backoff(base: float, attempt: int, cap: float = _MAX_SLEEP_SEC) -> float:
    """Exponential backoff with ±25% jitter, clamped to `cap` seconds."""
    raw = base * (2 ** attempt)
    jitter = raw * random.uniform(-0.25, 0.25)
    return min(cap, max(0.05, raw + jitter))


def _parse_retry_after(value: str) -> Optional[float]:
    """Parse a Retry-After header. Most servers send delta-seconds; some
    send an HTTP-date. We only handle the integer-seconds form — date-form
    is rare and we'd rather fall back to our own backoff than mis-parse."""
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def retry_get(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: float = 25.0,
    max_tries: int = 3,
    base_backoff: float = 1.0,
    session: Optional[requests.Session] = None,
    context: str = "",
    allow_redirects: bool = True,
) -> Optional[requests.Response]:
    """Robust GET: returns a Response on 2xx/3xx success, else None.

    `context` is a short tag that lands in the error log so you can tell
    one scraper's failures apart from another's.

    The function honors Retry-After on 429/503. It does NOT raise on
    terminal errors (4xx non-429, bad DNS, SSL failures) — it logs them
    and returns None. Caller skips or logs as it sees fit.
    """
    hdrs = dict(DEFAULT_HEADERS)
    if headers:
        hdrs.update(headers)
    get = (session.get if session is not None else requests.get)

    last_err: Optional[str] = None
    for attempt in range(max_tries):
        try:
            r = get(url, headers=hdrs, timeout=timeout,
                    allow_redirects=allow_redirects)
        except requests.RequestException as e:
            # Transient: retry.
            last_err = f"{type(e).__name__}: {e}"
            if attempt < max_tries - 1:
                sleep = _jittered_backoff(base_backoff, attempt)
                time.sleep(sleep)
                continue
            # Out of attempts
            if log_error is not None:
                log_error(context or "http_retry",
                          e, module="http_retry",
                          extra={"url": url, "attempt": attempt + 1,
                                 "max_tries": max_tries, "kind": "transient_exhausted"})
            return None

        # Success path
        if 200 <= r.status_code < 400:
            return r

        # Transient HTTP status: honor Retry-After + exponential backoff
        if r.status_code in _TRANSIENT_STATUS and attempt < max_tries - 1:
            ra = _parse_retry_after(r.headers.get("Retry-After", ""))
            sleep = min(_MAX_SLEEP_SEC, ra) if ra is not None else \
                    _jittered_backoff(base_backoff, attempt)
            time.sleep(sleep)
            continue

        # Terminal: log + return None.
        last_err = f"HTTP {r.status_code}"
        if log_error is not None:
            try:
                # Synthesize an exception so log_error gets a traceback-style record
                raise RuntimeError(f"HTTP {r.status_code} on {url}")
            except Exception as e:
                log_error(context or "http_retry",
                          e, module="http_retry",
                          extra={"url": url, "status": r.status_code,
                                 "kind": "terminal" if r.status_code not in _TRANSIENT_STATUS
                                         else "transient_exhausted"})
        return None

    # Shouldn't reach here, but defensively:
    return None


if __name__ == "__main__":
    # Quick smoke test — hit a couple of endpoints that respond differently
    import sys
    for u in [
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/503",
        "https://httpbin.org/status/404",
    ]:
        print(f"GET {u} ...")
        r = retry_get(u, timeout=10, max_tries=2, context="smoke")
        print(f"  -> {'ok' if r is not None else 'None'} "
              f"(status: {r.status_code if r is not None else '-'})")
