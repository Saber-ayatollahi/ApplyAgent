#!/usr/bin/env python3
"""
api_preflight.py — CLI-side Anthropic API preflight.

Mirrors ui/api_key.validate() so the CLI (fit_scorer, run_pipeline) fails
fast on auth/credit problems BEFORE spawning workers. Without this, a
stale/revoked/out-of-credits key lets fit_scorer triage 500 roles, spin
up a thread pool, and fail every worker one by one — which looks like
'the scorer is broken' even though it's a single fixable problem.

Public surface:
    check()                 -> PreflightResult
    preflight_or_exit(...)  -> exits non-zero with a clear category if the
                                key can't do a real messages.create call

Error categories mirror ui/api_key.py so the UI and CLI classify the
same failures the same way:
    OK            key works + billing OK
    EMPTY         no key set
    NO_SDK        anthropic package not installed
    AUTH          invalid_api_key / 401 / 403
    CREDIT        billing exhausted
    RATE_LIMIT    429 on preflight (soft-pass: we treat as OK)
    NETWORK       DNS / connection / timeout
    OTHER         anything else

Zero Streamlit dependency so this is safe to import from any CLI script.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime

CATEGORY_OK = "ok"
CATEGORY_EMPTY = "empty"
CATEGORY_NO_SDK = "no_sdk"
CATEGORY_AUTH = "auth"
CATEGORY_CREDIT = "credit"
CATEGORY_RATE = "rate_limit"
CATEGORY_NETWORK = "network"
CATEGORY_OTHER = "other"

# Exit codes for preflight_or_exit(). Chosen so caller scripts can branch on
# them cleanly: 0=OK (no exit), 3 is preflight-specific (distinct from 1
# "hard error" and 2 "usage error" commonly used by argparse).
EXIT_OK = 0
EXIT_PREFLIGHT_FAIL = 3


@dataclass
class PreflightResult:
    ok: bool
    category: str
    message: str
    checked_at: str
    model_count: int = 0
    preflight_ok: bool = False  # True only when billing preflight succeeded


def _classify(err_msg: str) -> str:
    em = (err_msg or "").lower()
    if "credit balance" in em or "billing" in em or "insufficient" in em:
        return CATEGORY_CREDIT
    if ("invalid_api_key" in em or "authentication" in em
            or "permission_denied" in em or "401" in em or "403" in em):
        return CATEGORY_AUTH
    if "rate_limit" in em or "429" in em:
        return CATEGORY_RATE
    if ("connection" in em or "timeout" in em or "timed out" in em
            or "getaddrinfo" in em or "networkerror" in em):
        return CATEGORY_NETWORK
    return CATEGORY_OTHER


def check(*, key: str | None = None, preflight: bool = True,
          preflight_model: str = "claude-haiku-4-5-20251001") -> PreflightResult:
    """Validate the Anthropic API key end-to-end.

    Two-step like the UI:
      1. GET /v1/models — confirms the key is well-formed + authenticated.
      2. (preflight=True) A 1-token messages.create — confirms billing is
         actually available. This is what catches 'credit balance too low'
         before the scorer burns 40 minutes producing 482 skip verdicts.

    `key` defaults to `os.environ['ANTHROPIC_API_KEY']`. Trimmed before use.
    """
    now = lambda: datetime.now().isoformat(timespec="seconds")
    k = (key if key is not None else os.environ.get("ANTHROPIC_API_KEY", "")) or ""
    k = k.strip()
    if not k:
        return PreflightResult(False, CATEGORY_EMPTY,
                                "ANTHROPIC_API_KEY not set in env", now())

    try:
        import anthropic  # type: ignore
    except ImportError:
        return PreflightResult(False, CATEGORY_NO_SDK,
                                "anthropic package not installed "
                                "(pip install anthropic)", now())

    client = anthropic.Anthropic(api_key=k)

    # Step 1: auth check via /v1/models (no tokens billed)
    try:
        page = client.models.list(limit=5)
        models = list(page.data) if hasattr(page, "data") else list(page)
        model_count = len(models)
    except Exception as e:
        msg = str(e)
        cat = _classify(msg)
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return PreflightResult(False, cat, f"Auth check failed: {msg}", now())

    if not preflight:
        return PreflightResult(
            True, CATEGORY_OK,
            f"Key authenticated — {model_count} models visible "
            "(billing preflight skipped)",
            now(), model_count=model_count, preflight_ok=False,
        )

    # Step 2: tiny messages.create to confirm billing
    try:
        client.messages.create(
            model=preflight_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
    except Exception as e:
        msg = str(e)
        cat = _classify(msg)
        if cat == CATEGORY_CREDIT:
            return PreflightResult(
                False, CATEGORY_CREDIT,
                "Key authenticated but credits exhausted — top up at "
                "console.anthropic.com/settings/billing",
                now(), model_count=model_count,
            )
        if cat == CATEGORY_RATE:
            # Rate-limited preflight isn't a real blocker for a CLI run;
            # if the scorer then hits the same rate limit, it has its own
            # retry. Treat as OK with a caveat in the message.
            return PreflightResult(
                True, CATEGORY_RATE,
                "Authenticated; preflight hit rate limit (treated as OK) "
                f"— {model_count} models visible",
                now(), model_count=model_count, preflight_ok=False,
            )
        if cat == CATEGORY_AUTH:
            return PreflightResult(
                False, CATEGORY_AUTH,
                f"Authenticated for models.list but messages blocked: "
                f"{msg[:180]}",
                now(), model_count=model_count,
            )
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return PreflightResult(False, cat, f"Preflight failed: {msg}",
                                now(), model_count=model_count)

    return PreflightResult(
        True, CATEGORY_OK,
        f"Valid & credits OK — {model_count} models, billing works",
        now(), model_count=model_count, preflight_ok=True,
    )


# Human-readable guidance per category. Mirrors the UI copy so both surfaces
# say the same thing.
_REMEDY = {
    CATEGORY_EMPTY: (
        "Set ANTHROPIC_API_KEY in your environment, e.g. (PowerShell):\n"
        "  $env:ANTHROPIC_API_KEY = \"sk-ant-...\"\n"
        "Or paste one in the Streamlit sidebar — it hydrates the env for "
        "subprocesses."
    ),
    CATEGORY_NO_SDK: (
        "Install the Anthropic SDK:\n"
        "  pip install anthropic"
    ),
    CATEGORY_AUTH: (
        "The key was REJECTED by the API. It's probably revoked, mistyped, "
        "or belongs to a deleted workspace.\n"
        "Fix: generate a new key at console.anthropic.com/settings/keys"
    ),
    CATEGORY_CREDIT: (
        "The key is valid BUT your Anthropic account has no billing credit. "
        "If scoring ran now, every role would fail with a credit error.\n"
        "Fix: top up at console.anthropic.com/settings/billing"
    ),
    CATEGORY_NETWORK: (
        "Could not reach the Anthropic API. Check connectivity, VPN, or "
        "proxy settings. (If you're on a corporate network, the API host "
        "may be blocked.)"
    ),
    CATEGORY_OTHER: (
        "Unexpected error — see message above."
    ),
}


def preflight_or_exit(*, module: str = "cli",
                      allow_skip_env: str = "APPLYAGENT_SKIP_PREFLIGHT",
                      require_preflight: bool = True) -> PreflightResult:
    """Run `check()` and exit with a clear message on failure. Returns the
    PreflightResult on success so callers can log `model_count` etc.

    Set `APPLYAGENT_SKIP_PREFLIGHT=1` to bypass (useful in CI or when the
    caller deliberately wants to run with a broken key — e.g. to see what
    triage would look like without spending tokens).

    `require_preflight=False` allows callers that are OK with just the
    auth check (e.g. read-only flows that don't call messages.create)."""
    if os.environ.get(allow_skip_env, "").strip() in ("1", "true", "yes"):
        print(f"[{module}] preflight skipped via {allow_skip_env}", file=sys.stderr)
        return PreflightResult(True, CATEGORY_OK,
                                f"skipped via {allow_skip_env}",
                                datetime.now().isoformat(timespec="seconds"),
                                preflight_ok=True)

    res = check(preflight=require_preflight)
    if res.ok:
        print(f"[{module}] API preflight OK — {res.message}", file=sys.stderr)
        return res

    print(f"[{module}] ❌ API preflight FAILED "
          f"(category={res.category}): {res.message}", file=sys.stderr)
    print(f"[{module}] → {_REMEDY.get(res.category, _REMEDY[CATEGORY_OTHER])}",
          file=sys.stderr)
    print(f"[{module}] (to bypass for debugging: "
          f"{allow_skip_env}=1)", file=sys.stderr)
    sys.exit(EXIT_PREFLIGHT_FAIL)


if __name__ == "__main__":
    # Convenience: `python automation/api_preflight.py` prints status.
    import json as _json
    res = check()
    print(_json.dumps({
        "ok": res.ok, "category": res.category, "message": res.message,
        "checked_at": res.checked_at, "model_count": res.model_count,
        "preflight_ok": res.preflight_ok,
    }, indent=2))
    sys.exit(0 if res.ok else EXIT_PREFLIGHT_FAIL)
