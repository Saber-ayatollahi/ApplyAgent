#!/usr/bin/env python3
"""
outcome_feedback.py — Pipeline-outcome feedback for the fit scorer.

Reads the tracker, computes conversion rates per (sector, tier, primary_variant)
slice, and writes a compact markdown + JSON report. The scorer's system prompt
reads the markdown and tells the LLM: "here's how Saber's pipeline has actually
performed so far — weight accordingly."

Today the tracker has mostly Watch/Found entries (no Applied/Interview yet),
so rates are 0. The skeleton is ready for when outcomes start landing.

Rules the scorer will see:
  - If a slice has >=5 applications and 0 interviews -> "cold lane" warning
  - If a slice has >=3 interviews/applications rate -> "hot lane" preference
  - Otherwise: informational only

Data pipeline:
    tracker statuses -> slices -> rates -> outputs/scorer_feedback.md
                                       -> outputs/scorer_feedback.json

Call this from a nightly job or whenever the tracker changes meaningfully.
The scorer reads the MD at prompt-build time and falls back silently if the
file doesn't exist.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"
FEEDBACK_MD = OUT_DIR / "scorer_feedback.md"
FEEDBACK_JSON = OUT_DIR / "scorer_feedback.json"

# Statuses that count as "outcomes" for conversion math. The tracker uses
# free-form strings that evolve; this tolerant mapping is used instead of
# a strict enum so a new status ("Phone_Screen_Round_2") doesn't break us.
APPLIED_STATUSES = {
    "Applied", "Recruiter_Screen", "Phone_Screen", "Take_Home",
    "Onsite", "Offer", "Interview", "Interview_1", "Interview_2",
    "Final", "Ghosted", "Rejected",
}
INTERVIEWED_STATUSES = {
    "Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite",
    "Interview", "Interview_1", "Interview_2", "Final", "Offer",
}
OFFERED_STATUSES = {"Offer"}
REJECTED_STATUSES = {"Rejected", "Ghosted"}


@dataclass
class SliceStats:
    key: str                   # e.g. "sector:Canadian Big 6 Banks"
    total_in_pipeline: int = 0
    applied: int = 0
    interviewed: int = 0
    offered: int = 0
    rejected: int = 0

    def rate(self, numer: int) -> float:
        return (numer / self.applied) if self.applied else 0.0

    def summarize(self) -> str:
        """Return a one-line summary suitable for the prompt feedback file."""
        if self.applied == 0:
            return (f"{self.key} — {self.total_in_pipeline} in pipeline, "
                    f"no applications yet")
        irate = self.rate(self.interviewed) * 100
        return (
            f"{self.key} — applied:{self.applied}  "
            f"interview_rate:{irate:.0f}%  "
            f"offers:{self.offered}  rejections:{self.rejected}  "
            f"(total in pipeline: {self.total_in_pipeline})"
        )


@dataclass
class FeedbackReport:
    generated_at: str
    total_in_tracker: int
    sectors: dict[str, SliceStats]
    tiers: dict[str, SliceStats]
    variants: dict[str, SliceStats]
    hot_lanes: list[str] = field(default_factory=list)
    cold_lanes: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        def _s(d):
            return {k: vars(v) for k, v in d.items()}
        return {
            "generated_at": self.generated_at,
            "total_in_tracker": self.total_in_tracker,
            "sectors": _s(self.sectors),
            "tiers": _s(self.tiers),
            "variants": _s(self.variants),
            "hot_lanes": self.hot_lanes,
            "cold_lanes": self.cold_lanes,
        }

    def as_markdown(self) -> str:
        lines: list[str] = [
            "# Scorer outcome feedback",
            "",
            f"_Generated {self.generated_at}. Pipeline size: "
            f"{self.total_in_tracker} tracker entries._",
            "",
        ]
        if not self.hot_lanes and not self.cold_lanes:
            lines.append(
                "> **No outcome signal yet** — the tracker has tracker entries "
                "but no Applied/Interview transitions have been recorded, so "
                "there is no conversion data for the scorer to weight on. "
                "Once status moves to Applied/Recruiter_Screen/Interview/"
                "Offer/Rejected, this report will start carrying signal."
            )
            lines.append("")
        if self.hot_lanes:
            lines.append("## Hot lanes (higher interview rate)")
            for ln in self.hot_lanes:
                lines.append(f"- {ln}")
            lines.append("")
        if self.cold_lanes:
            lines.append("## Cold lanes (applied but no interviews)")
            for ln in self.cold_lanes:
                lines.append(f"- {ln}")
            lines.append("")
        lines.append("## Full breakdown")
        for title, d in [("### By sector", self.sectors),
                          ("### By tier", self.tiers),
                          ("### By primary variant", self.variants)]:
            lines.append("")
            lines.append(title)
            items = sorted(d.values(), key=lambda s: -s.total_in_pipeline)
            for s in items:
                lines.append(f"- {s.summarize()}")
        lines.append("")
        return "\n".join(lines)


def _slice_key(prefix: str, value) -> str:
    v = str(value) if value not in (None, "", "?") else "(unknown)"
    return f"{prefix}:{v}"


def _accumulate(stats: dict[str, SliceStats], key: str, status: str) -> None:
    s = stats.setdefault(key, SliceStats(key=key))
    s.total_in_pipeline += 1
    if status in APPLIED_STATUSES:
        s.applied += 1
    if status in INTERVIEWED_STATUSES:
        s.interviewed += 1
    if status in OFFERED_STATUSES:
        s.offered += 1
    if status in REJECTED_STATUSES:
        s.rejected += 1


def build_report(tracker_path: Path = TRACKER) -> FeedbackReport:
    """Read the tracker and compute the feedback report. Does NOT mutate
    the tracker, does NOT write anywhere; callers decide what to persist."""
    if not tracker_path.exists():
        return FeedbackReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            total_in_tracker=0, sectors={}, tiers={}, variants={},
        )
    data = json.loads(tracker_path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    sectors: dict[str, SliceStats] = {}
    tiers: dict[str, SliceStats] = {}
    variants: dict[str, SliceStats] = {}

    for j in jobs:
        status = j.get("status") or "?"
        _accumulate(sectors, _slice_key("sector", j.get("sector")), status)
        _accumulate(tiers, _slice_key("tier", j.get("tier")), status)
        pv = j.get("primary_variant") or (
            (j.get("resume_variants") or [None])[0] if j.get("resume_variants")
            else None
        )
        if pv:
            _accumulate(variants, _slice_key("variant", pv), status)

    hot_lanes: list[str] = []
    cold_lanes: list[str] = []
    for bucket in (sectors, tiers, variants):
        for s in bucket.values():
            if s.applied >= 3 and s.rate(s.interviewed) >= 0.30:
                hot_lanes.append(s.summarize())
            elif s.applied >= 5 and s.interviewed == 0:
                cold_lanes.append(s.summarize())

    return FeedbackReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_in_tracker=len(jobs),
        sectors=sectors, tiers=tiers, variants=variants,
        hot_lanes=hot_lanes, cold_lanes=cold_lanes,
    )


def write_report(report: FeedbackReport, *,
                  md_path: Path = FEEDBACK_MD,
                  json_path: Path = FEEDBACK_JSON) -> None:
    """Persist the report to outputs/. Uses safe_json if available for the
    JSON side (cross-process safety); markdown is a simple write."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report.as_markdown(), encoding="utf-8")
    try:
        from safe_json import write_json  # type: ignore
        write_json(json_path, report.as_json())
    except ImportError:
        json_path.write_text(json.dumps(report.as_json(), indent=2), encoding="utf-8")


def prompt_snippet(md_path: Path = FEEDBACK_MD, max_chars: int = 1500) -> str:
    """Return a compact snippet suitable for the fit_scorer system prompt.

    If the report doesn't exist, returns "". If no signal has been computed
    (no applications yet), returns a short line instead of the whole skeleton
    — we don't want to pollute the scorer prompt with 'no outcome signal yet'
    boilerplate on every call."""
    if not md_path.exists():
        return ""
    text = md_path.read_text(encoding="utf-8")
    # If the report says no outcome signal, skip injection
    if "No outcome signal yet" in text and "Hot lanes" not in text and "Cold lanes" not in text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n_(truncated for prompt)_"
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true",
                    help="Print the markdown to stdout without writing files")
    args = ap.parse_args()

    report = build_report()
    if args.preview:
        # Write to a temp path to avoid Windows stdout encoding issues
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "scorer_feedback_preview.md"
        tmp.write_text(report.as_markdown(), encoding="utf-8")
        print(f"preview written to {tmp}")
        return 0
    write_report(report)
    print(f"[outcome_feedback] wrote {FEEDBACK_MD.name} + {FEEDBACK_JSON.name}")
    print(f"  hot lanes: {len(report.hot_lanes)}")
    print(f"  cold lanes: {len(report.cold_lanes)}")
    print(f"  total in tracker: {report.total_in_tracker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
