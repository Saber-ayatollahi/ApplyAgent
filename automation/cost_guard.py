#!/usr/bin/env python3
"""
cost_guard.py — Spend caps for LLM-driven jobs.

Two caps enforced before (or during) any paid run:
  - Daily cap   : rolling 24-hour USD spend across all models, read from the
                  cost_ledger. Default $5/day, env: COST_GUARD_DAILY_CAP_USD
  - Per-run cap : in-process USD spend since guard was started. Default $2/run,
                  env: COST_GUARD_PER_RUN_CAP_USD

Usage pattern (fit_scorer):

    from cost_guard import CostGuard
    guard = CostGuard.from_env()
    guard.preflight_or_exit()            # hard-fail before any LLM call
    # ... in scoring loop, after each LLM call:
    guard.record(estimated_usd)
    if guard.exceeded():
        guard.trigger_abort(abort_event, reason_list)
        break

The guard does not override user intent — if you WANT to spend more, set
the env cap higher before the run. The point is to catch runaway loops
that would burn $50 before anyone notices.
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import date

try:
    from cost_ledger import load as _load_ledger  # type: ignore
except ImportError:
    try:
        from .cost_ledger import load as _load_ledger  # type: ignore
    except Exception:
        _load_ledger = None  # type: ignore


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[cost_guard] WARN: env {name}={raw!r} not a float; using "
              f"default {default}", file=sys.stderr)
        return default


@dataclass
class CostGuard:
    daily_cap_usd: float = 5.0
    per_run_cap_usd: float = 2.0
    run_spend_usd: float = 0.0
    _triggered_reason: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def from_env(cls) -> "CostGuard":
        return cls(
            daily_cap_usd=_env_float("COST_GUARD_DAILY_CAP_USD", 5.0),
            per_run_cap_usd=_env_float("COST_GUARD_PER_RUN_CAP_USD", 2.0),
        )

    def today_spend_usd(self) -> float:
        """Best-effort read of today's spend from the ledger. Returns 0.0 if
        the ledger isn't available — never blocks a run on ledger IO."""
        if _load_ledger is None:
            return 0.0
        try:
            data = _load_ledger()
            return float(data.get("daily", {})
                             .get(date.today().isoformat(), {})
                             .get("cost_usd", 0.0))
        except Exception:
            return 0.0

    def preflight_or_exit(self, *, require_ledger: bool = False) -> None:
        """Refuse to start if today's ledger spend already exceeds the daily
        cap. Prints a clear explanation and exits non-zero.

        `require_ledger=True` fails if the ledger isn't importable — useful
        in CI, but not the default (local dev can run the scorer without
        having the ledger wired in)."""
        if _load_ledger is None:
            if require_ledger:
                print("[cost_guard] ERROR: cost_ledger not available; refusing "
                      "to start a guarded run.", file=sys.stderr)
                sys.exit(3)
            return
        spend = self.today_spend_usd()
        if spend >= self.daily_cap_usd:
            print(
                f"[cost_guard] ABORT: today's spend ${spend:.3f} already "
                f"exceeds daily cap ${self.daily_cap_usd:.2f}. "
                f"Set COST_GUARD_DAILY_CAP_USD higher if intentional.",
                file=sys.stderr,
            )
            sys.exit(4)

    def record(self, usd: float) -> None:
        """Accumulate in-process run spend. Thread-safe: scorer threads
        record costs concurrently, and a non-atomic += would lose updates
        under contention."""
        if usd and usd > 0:
            with self._lock:
                self.run_spend_usd += float(usd)

    def exceeded(self) -> bool:
        """True if either cap is breached. Evaluates run-cap from accumulated
        spend and daily-cap from ledger + accumulated spend.

        NOTE: the daily check re-reads the ledger each call; inside a tight
        scoring loop this is fine (the ledger is local disk), and it means
        the guard also responds to a PARALLEL job's spend within the same
        day. If cost becomes a concern, this can be moved to a periodic
        check (every N calls)."""
        with self._lock:
            run_spend = self.run_spend_usd
            if run_spend >= self.per_run_cap_usd:
                self._triggered_reason = (
                    f"per-run cap exceeded: ${run_spend:.3f} >= "
                    f"${self.per_run_cap_usd:.2f}"
                )
                return True
        # Ledger read is outside the lock — it does its own IO and we don't
        # want to serialize disk reads behind the spend counter.
        ledger_today = self.today_spend_usd()
        with self._lock:
            run_spend = self.run_spend_usd
            total_today = ledger_today + max(0.0, run_spend)
            if total_today >= self.daily_cap_usd:
                self._triggered_reason = (
                    f"daily cap exceeded: ledger=${ledger_today:.3f} + "
                    f"run=${run_spend:.3f} >= cap=${self.daily_cap_usd:.2f}"
                )
                return True
        return False

    @property
    def reason(self) -> str:
        return self._triggered_reason or "(not exceeded)"

    def trigger_abort(self, abort_event, reason_list: list[str]) -> None:
        """Mark the caller's abort_event and add our reason. Idempotent."""
        if abort_event is None:
            return
        if abort_event.is_set():
            return
        reason_list.append(f"cost_guard: {self.reason}")
        abort_event.set()
        print(f"\n[cost_guard] {self.reason} — aborting pending LLM calls.",
              file=sys.stderr)

    def summary(self) -> str:
        with self._lock:
            run_spend = self.run_spend_usd
        return (
            f"run_spend=${run_spend:.3f} / cap=${self.per_run_cap_usd:.2f}  "
            f"today_spend=${self.today_spend_usd():.3f} / cap=${self.daily_cap_usd:.2f}"
        )


if __name__ == "__main__":
    g = CostGuard.from_env()
    print(f"CostGuard from env: daily_cap=${g.daily_cap_usd:.2f}, "
          f"per_run_cap=${g.per_run_cap_usd:.2f}")
    print(f"Today's spend: ${g.today_spend_usd():.3f}")
    print(f"Exceeded? {g.exceeded()}  (reason: {g.reason})")
