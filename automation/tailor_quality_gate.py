#!/usr/bin/env python3
"""
tailor_quality_gate.py — Deterministic post-processor for jd_tailor output.

Why this exists
---------------
Memory [[feedback_osfi_deemphasis]] (2026-05-06): cover letters MUST NOT lead
on regulatory framing (OSFI, E-23, B-12, LAR, IFRS 17/9, Basel, ECL). The
tailor system prompt explicitly bans this. LLMs lapse anyway — on 2026-05-14
a Scotiabank cover letter opened with "With OSFI's B-12 IRRBB revision
entering consultations..." despite the instruction.

This module is the deterministic backstop:
  1. Regex-scan paragraph 1 of the COVER LETTER section for forbidden tokens.
  2. If a violation is found, fire ONE rescue LLM call (Sonnet 4.6, cheap)
     under cost-guard to rewrite paragraph 1 leading on a capability claim.
  3. Substitute the new paragraph back into the markdown document
     atomically; keep a .bak of the original.

Library API
-----------
    from tailor_quality_gate import gate_check, gate_rescue, GateResult

    result = gate_check(markdown_text)
    if not result.clean:
        new_md = gate_rescue(markdown_text, result)  # makes one LLM call

CLI
---
    python tailor_quality_gate.py <path>          # check only, exit 2 if dirty
    python tailor_quality_gate.py <path> --rescue # check + rewrite if dirty
    python tailor_quality_gate.py <path> --dry-run

Constraints (per design spec):
  - Reuses cost_guard, cost_ledger, error_log exactly as fit_scorer/jd_tailor.
  - Atomic write of the rescued markdown.
  - Backup before overwrite (.bak.YYYYMMDD).
  - No new dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Optional infra imports — same defensive try/except pattern as jd_tailor.
# ---------------------------------------------------------------------------
try:
    import anthropic  # type: ignore
    _HAVE_ANTHROPIC = True
except ImportError:
    _HAVE_ANTHROPIC = False
    anthropic = None  # type: ignore

try:
    from cost_guard import CostGuard as _CostGuard  # type: ignore
except ImportError:
    try:
        from .cost_guard import CostGuard as _CostGuard  # type: ignore
    except Exception:
        _CostGuard = None  # type: ignore

try:
    from cost_ledger import record as _ledger_record  # type: ignore
except ImportError:
    try:
        from .cost_ledger import record as _ledger_record  # type: ignore
    except Exception:
        _ledger_record = None  # type: ignore

try:
    from error_log import log_error as _log_error  # type: ignore
except ImportError:
    try:
        from .error_log import log_error as _log_error  # type: ignore
    except Exception:
        _log_error = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
GATE_LOG = OUT_DIR / "quality_gate_log.jsonl"

# Tight per-run budget for the gate alone — independent of the tailor's own
# cap. Sonnet 4.6 input is $3/M and output $15/M; a ~3K-token cover letter
# plus a ~150-token rewrite costs well under $0.05.
RUN_BUDGET_USD = 0.05

# Sonnet 4.6 — cheaper than Opus and plenty smart for a paragraph rewrite.
RESCUE_MODEL = os.environ.get("TAILOR_GATE_MODEL", "claude-sonnet-4-6")

_MODEL_PRICES = {
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0,  "output": 5.0},
    "claude-haiku-4-5":          {"input": 1.0,  "output": 5.0},
}


def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _MODEL_PRICES.get(model) or _MODEL_PRICES.get(model.split("-2025")[0])
    if not p:
        return 0.0
    return (in_tokens * p["input"] + out_tokens * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Forbidden-token catalog
# ---------------------------------------------------------------------------
# Word-boundary aware where the literal would otherwise eat substrings.
# Patterns are pre-compiled (case-insensitive) once at import.
#
# We deliberately scope the scan to PARAGRAPH 1 only — the policy is that the
# cover letter must LEAD on capability, not that OSFI etc. can never appear
# in the document at all (later paragraphs and the resume routinely cite
# regulatory context, which is fine and even useful).
_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OSFI",           re.compile(r"\bOSFI\b", re.IGNORECASE)),
    ("E-23",           re.compile(r"\bE[-\s]?23\b", re.IGNORECASE)),
    ("B-12",           re.compile(r"\bB[-\s]?12\b", re.IGNORECASE)),
    ("LAR",            re.compile(r"\bLAR\b")),  # case-sensitive: avoid 'lar' in 'similar'
    ("IFRS 17",        re.compile(r"\bIFRS\s?17\b", re.IGNORECASE)),
    ("IFRS 9",         re.compile(r"\bIFRS\s?9\b", re.IGNORECASE)),
    ("Basel",          re.compile(r"\bBasel\b", re.IGNORECASE)),
    ("ECL",            re.compile(r"\bECL\b")),  # case-sensitive: avoid 'ecl' substrings
    ("regulatory tailwind",  re.compile(r"regulatory\s+tailwind", re.IGNORECASE)),
    ("regulatory calendar",  re.compile(r"regulatory\s+calendar", re.IGNORECASE)),
    ("regulatory posture",   re.compile(r"regulatory\s+posture", re.IGNORECASE)),
    ("under guideline",      re.compile(r"\bunder\s+(?:OSFI|the)?\s*guideline", re.IGNORECASE)),
]


# ---------------------------------------------------------------------------
# Cover-letter section / paragraph extraction
# ---------------------------------------------------------------------------
# jd_tailor writes the section header as `## § COVER LETTER`. We accept a
# small set of variants (the §, the literal "COVER LETTER", optional spacing)
# so a manually-edited file or a slightly different template still gets
# scanned. The next `## ` header (or end-of-file) bounds the section.
_COVER_HEADER_RE = re.compile(
    r"^##\s*(?:§\s*)?COVER\s*LETTER\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Match any next H2 header. Used to find the END of the cover-letter section.
_NEXT_H2_RE = re.compile(r"^##\s+\S", re.MULTILINE)


def _extract_cover_letter(markdown: str) -> Optional[tuple[int, int, str]]:
    """Return (start_offset, end_offset, body) of the cover-letter section, or
    None if the section header isn't found. `start_offset` is the character
    AFTER the header line; `end_offset` is just BEFORE the next H2 header (or
    end of document)."""
    m = _COVER_HEADER_RE.search(markdown)
    if not m:
        return None
    start = m.end()
    # Skip the trailing newline of the header line so body starts cleanly.
    while start < len(markdown) and markdown[start] == "\n":
        start += 1
    rest = markdown[start:]
    nxt = _NEXT_H2_RE.search(rest)
    end = start + (nxt.start() if nxt else len(rest))
    body = markdown[start:end]
    return (start, end, body)


# Lines that look like cover-letter scaffolding rather than prose paragraph 1.
# We skip leading scaffolding (subject line, salutation, blank lines, bold
# meta) so the "first paragraph" is the actual opening prose.
_SCAFFOLD_RE = re.compile(
    r"""^(
        \s*$ |                                    # blank line
        \s*\*\*[^*]+\*\*\s*$ |                    # bold-only line (e.g. **Subject:** ...)
        \s*\*\*Subject:\*\*.* |                   # explicit subject line
        \s*Subject\s*:\s*.* |                     # 'Subject: ...' plaintext
        \s*Dear\s+.* |                            # salutation
        \s*To\s+whom.* |                          # alternate salutation
        \s*Hiring\s+(Team|Manager|Committee).*    # alternate salutation
    )$""",
    re.VERBOSE | re.IGNORECASE,
)


def _first_paragraph(cover_body: str) -> tuple[int, int, str]:
    """Return (start, end, text) of the first prose paragraph relative to the
    cover-letter body. A paragraph is bounded by blank lines. We skip
    scaffolding (subject, salutation) before declaring the first paragraph.
    Falls back to an empty string at offset 0 if nothing prose-like is
    found."""
    lines = cover_body.split("\n")
    # Find index of first non-scaffold line.
    i = 0
    while i < len(lines) and _SCAFFOLD_RE.match(lines[i]):
        i += 1
    # Now collect contiguous non-blank lines from i — that's paragraph 1.
    j = i
    while j < len(lines) and lines[j].strip() != "":
        j += 1
    para_lines = lines[i:j]
    if not para_lines:
        return (0, 0, "")
    # Compute character offsets within cover_body. Sum lengths of preceding
    # lines including the '\n' separators.
    pre = "\n".join(lines[:i])
    start = len(pre) + (1 if i > 0 else 0)
    para_text = "\n".join(para_lines)
    end = start + len(para_text)
    return (start, end, para_text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@dataclass
class GateResult:
    clean: bool
    violations: list[str] = field(default_factory=list)
    paragraph_1: str = ""
    # Internal offsets so the rescue path can rewrite in place without
    # re-parsing. Not part of the documented contract — callers should rely
    # on the public fields above.
    cover_start: int = 0
    cover_end: int = 0
    para_start_in_cover: int = 0
    para_end_in_cover: int = 0


def gate_check(markdown_text: str) -> GateResult:
    """Scan paragraph 1 of the cover-letter section for forbidden tokens.

    Returns a GateResult with `clean=True` if no violations are found, else
    `clean=False` and a deduplicated, sorted list of violation labels. If the
    document has no cover-letter section at all we return `clean=True` (the
    gate is advisory and shouldn't fire on docs that have no cover letter to
    police).
    """
    extracted = _extract_cover_letter(markdown_text)
    if extracted is None:
        return GateResult(clean=True, violations=[], paragraph_1="")

    cover_start, cover_end, cover_body = extracted
    p_start, p_end, para = _first_paragraph(cover_body)
    if not para.strip():
        return GateResult(
            clean=True, violations=[], paragraph_1="",
            cover_start=cover_start, cover_end=cover_end,
            para_start_in_cover=p_start, para_end_in_cover=p_end,
        )

    found: list[str] = []
    for label, pat in _FORBIDDEN_PATTERNS:
        if pat.search(para):
            found.append(label)
    found = sorted(set(found))
    return GateResult(
        clean=not found,
        violations=found,
        paragraph_1=para,
        cover_start=cover_start,
        cover_end=cover_end,
        para_start_in_cover=p_start,
        para_end_in_cover=p_end,
    )


# ---------------------------------------------------------------------------
# Rescue: ONE LLM call to rewrite paragraph 1 lead-on-capability.
# ---------------------------------------------------------------------------
_RESCUE_SYSTEM_PROMPT = (
    "You are a senior finance career strategist. You rewrite a cover-letter "
    "OPENING paragraph for Saber Ayatollahi (CFA, ~7.3 years ALM/IRRBB/Moody's "
    "Analytics) so that it LEADS on a concrete capability claim — sign-off "
    "authority on multi-asset institutional portfolios, cash-flow projection "
    "engines, IRRBB-analogous shock analytics, LDI background from Ortec, "
    "IFRS-delivery experience at EY — rather than on a regulatory-calendar "
    "narrative.\n\n"
    "BANNED tokens (do NOT use any of these in the rewritten paragraph): "
    "OSFI, E-23, B-12, LAR, IFRS 17, IFRS 9, Basel, ECL, 'regulatory "
    "tailwind', 'regulatory calendar', 'regulatory posture', 'under guideline'.\n\n"
    "Length target: 3-5 sentences (~80-130 words). Tone: confident, specific, "
    "tied to the target employer/role. No regulatory framing. No filler. "
    "Do not invent accomplishments."
)


def _build_rescue_user_prompt(markdown: str, violations: list[str]) -> str:
    return (
        "Below is a tailored cover letter generated for Saber. Paragraph 1 "
        "violates the rule against leading on regulatory framing — it "
        f"contains: {', '.join(violations)}.\n\n"
        "Rewrite ONLY paragraph 1 so it leads on a concrete capability claim "
        "tied to the target role. Keep the rest of the cover letter implicit "
        "context — your output is a drop-in replacement for paragraph 1 only.\n\n"
        "Return ONLY the revised paragraph 1, no preamble, no markdown header, "
        "no quotes around it.\n\n"
        "----- BEGIN COVER LETTER -----\n"
        f"{markdown}\n"
        "----- END COVER LETTER -----\n"
    )


def _rescue_llm_call(markdown: str, violations: list[str]) -> tuple[str, float]:
    """Make one cost-guarded Anthropic call to rewrite paragraph 1.

    Returns (revised_paragraph, cost_usd). Raises on hard failure (no API
    key, SDK missing, cost-guard tripped, API error). Caller is responsible
    for catching and downgrading to a warning so the tailor's exit code
    isn't blocked.
    """
    if not _HAVE_ANTHROPIC:
        raise RuntimeError(
            "anthropic SDK not installed — cannot run rescue. "
            "pip install anthropic"
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot run rescue.")

    # Cost guard with a tight per-run cap dedicated to the gate. We honor the
    # daily cap from env (same source as the rest of the pipeline) but pin
    # the per-run cap to RUN_BUDGET_USD so a misfiring rescue can't burn
    # more than ~$0.05 even if env COST_GUARD_PER_RUN_CAP_USD is high.
    guard = None
    if _CostGuard is not None:
        guard = _CostGuard.from_env()
        guard.per_run_cap_usd = min(guard.per_run_cap_usd, RUN_BUDGET_USD)
        guard.preflight_or_exit()
        if guard.exceeded():
            raise RuntimeError(f"cost_guard tripped pre-call: {guard.reason}")

    client = anthropic.Anthropic()
    user = _build_rescue_user_prompt(markdown, violations)

    resp = client.messages.create(
        model=RESCUE_MODEL,
        max_tokens=600,
        system=_RESCUE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )

    cost = 0.0
    in_t = out_t = 0
    try:
        usage = resp.usage
        in_t = getattr(usage, "input_tokens", 0) or 0
        out_t = getattr(usage, "output_tokens", 0) or 0
        cost = _estimate_cost_usd(RESCUE_MODEL, in_t, out_t)
        if guard is not None and cost > 0:
            guard.record(cost)
        if _ledger_record is not None:
            try:
                _ledger_record(
                    model=RESCUE_MODEL, in_tokens=in_t, out_tokens=out_t,
                    cost_usd=cost, cache_create=0, cache_read=0, cache_hit=False,
                )
            except Exception as _le:
                if _log_error is not None:
                    _log_error("ledger_record", _le, module="tailor_quality_gate")
        print(f"  [gate] rescue {RESCUE_MODEL} cost ${cost:.4f} "
              f"(in={in_t}, out={out_t})", file=sys.stderr)
    except Exception:
        # Telemetry is best-effort.
        pass

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        raise RuntimeError("rescue LLM returned empty paragraph")

    # Strip stray surrounding quotes / leading "Paragraph 1:" labels just in
    # case the model ignored the instruction.
    text = re.sub(r"^\s*paragraph\s*1\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip('"').strip("'").strip()

    return text, cost


def gate_rescue(markdown_text: str, result: GateResult) -> tuple[str, float]:
    """Rewrite paragraph 1 in `markdown_text` based on `result` and return
    (new_markdown, cost_usd). Caller must persist the result and create a
    backup if appropriate.
    """
    if result.clean:
        return markdown_text, 0.0
    revised, cost = _rescue_llm_call(markdown_text, result.violations)

    # Defense-in-depth: if the model itself produced a banned token, refuse
    # the rescue rather than silently re-introducing the violation.
    for label, pat in _FORBIDDEN_PATTERNS:
        if pat.search(revised):
            raise RuntimeError(
                f"rescue paragraph still contains banned token '{label}' — "
                "refusing to substitute"
            )

    # Splice: replace [cover_start + para_start, cover_start + para_end]
    # with `revised`.
    abs_start = result.cover_start + result.para_start_in_cover
    abs_end = result.cover_start + result.para_end_in_cover
    new_md = markdown_text[:abs_start] + revised + markdown_text[abs_end:]
    return new_md, cost


# ---------------------------------------------------------------------------
# Atomic file ops + logging
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path via temp-file + os.replace. Mirrors safe_json's
    atomic-write pattern but for plain text (the markdown is not JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # Windows can briefly hold the file via indexer/AV; retry on PermissionError.
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                import time as _time
                _time.sleep(0.02 * (2 ** attempt))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    return path.with_suffix(path.suffix + f".bak.{stamp}")


def _append_log(record: dict) -> None:
    """Append one JSONL record to the gate log. Best-effort — never raises."""
    try:
        GATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GATE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        if _log_error is not None:
            _log_error("gate_log_append", e, module="tailor_quality_gate")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Cover-letter quality gate. Scans paragraph 1 for forbidden "
            "regulatory-framing tokens and (optionally) calls one rescue LLM "
            "to rewrite it lead-on-capability."
        ),
    )
    ap.add_argument("path", help="Path to a tailor markdown file (the unified PARSE LOG / RESUME / COVER LETTER / INTERVIEW BRIEF document).")
    ap.add_argument("--rescue", action="store_true",
                    help="If violations found, call one rescue LLM, back up the original, and overwrite the file.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show violations only; never spend money. Implies no rescue.")
    args = ap.parse_args(argv)

    target = Path(args.path)
    if not target.exists():
        print(f"[gate] ERROR: file not found: {target}", file=sys.stderr)
        return 2

    md = target.read_text(encoding="utf-8")
    result = gate_check(md)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if result.clean:
        print(f"[gate] OK — paragraph 1 clean ({len(result.paragraph_1)} chars)")
        _append_log({"ts": ts, "file": str(target), "violations": [],
                     "action": "clean", "cost": 0.0})
        return 0

    print(f"[gate] VIOLATIONS in {target.name}: {', '.join(result.violations)}",
          file=sys.stderr)
    print(f"[gate] paragraph 1 preview: {result.paragraph_1[:200]}...",
          file=sys.stderr)

    if args.dry_run or not args.rescue:
        # Dry-run / check-only: report and exit non-zero, no spend.
        action = "warned" if args.dry_run else "warned"
        _append_log({"ts": ts, "file": str(target),
                     "violations": result.violations,
                     "action": action, "cost": 0.0,
                     "dry_run": bool(args.dry_run)})
        return 2

    # --rescue path: backup, attempt rescue, overwrite atomically.
    bak = _backup_path(target)
    try:
        shutil.copy2(target, bak)
        print(f"[gate] backup written: {bak}", file=sys.stderr)
    except Exception as e:
        print(f"[gate] WARN: backup failed ({e}); aborting rescue to preserve original",
              file=sys.stderr)
        if _log_error is not None:
            _log_error("gate_backup_fail", e, module="tailor_quality_gate",
                       extra={"path": str(target)})
        _append_log({"ts": ts, "file": str(target),
                     "violations": result.violations,
                     "action": "warned", "cost": 0.0,
                     "warn": "backup_failed"})
        return 2

    try:
        new_md, cost = gate_rescue(md, result)
    except Exception as e:
        # Any rescue failure (budget, API error, banned-token in rewrite)
        # leaves the original alone. The gate is advisory.
        print(f"[gate] WARN: rescue failed ({e}); leaving original in place",
              file=sys.stderr)
        if _log_error is not None:
            _log_error("gate_rescue_fail", e, module="tailor_quality_gate",
                       extra={"path": str(target),
                              "violations": result.violations})
        _append_log({"ts": ts, "file": str(target),
                     "violations": result.violations,
                     "action": "warned", "cost": 0.0,
                     "warn": str(e)[:200]})
        return 2

    try:
        _atomic_write_text(target, new_md)
    except Exception as e:
        print(f"[gate] WARN: atomic write failed ({e}); original preserved at {bak}",
              file=sys.stderr)
        if _log_error is not None:
            _log_error("gate_write_fail", e, module="tailor_quality_gate",
                       extra={"path": str(target)})
        _append_log({"ts": ts, "file": str(target),
                     "violations": result.violations,
                     "action": "warned", "cost": cost,
                     "warn": "write_failed"})
        return 2

    print(f"[gate] RESCUED — overwrote {target.name} (cost ${cost:.4f}, "
          f"backup: {bak.name})")
    _append_log({"ts": ts, "file": str(target),
                 "violations": result.violations,
                 "action": "rescued", "cost": round(cost, 6),
                 "backup": str(bak), "model": RESCUE_MODEL})
    return 0


if __name__ == "__main__":
    sys.exit(_main())
