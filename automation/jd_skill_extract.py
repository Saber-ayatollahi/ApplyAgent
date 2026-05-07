#!/usr/bin/env python3
"""
jd_skill_extract.py — Deterministic JD → skills / variants / gaps analysis.

Unlike `master_repo.score_jd_skills(keywords_list)`, this works on a raw JD
TEXT and walks every skill's (name + aliases) as a whole-phrase matcher
against the JD. No LLM, no vibes — if "IRRBB" literally appears in the JD,
sk_irrbb matches; if it doesn't, it doesn't. Callers feed the structured
output into an LLM prompt so the LLM can score with facts instead of
re-parsing the JD itself.

Key outputs:
    matched_skills[]       — every skill whose name/alias appears in JD
    primary_hits[]         — subset where skill.is_primary
    suggested_variants[]   — resume variants ranked by matching-bullet count
    gaps_flagged[]         — skills saber does NOT have that JD asks for
    coverage_pct           — matched / (matched + gaps)
    keyword_summary        — flat list of phrases we DID and DID NOT find

This module has no Anthropic / network dependencies — pure string search.
"""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    from master_repo import load as _load_repo, MasterRepo, Skill, Bullet
except ImportError:
    # When run from a different cwd, allow package-style import
    from automation.master_repo import load as _load_repo  # type: ignore
    from automation.master_repo import MasterRepo, Skill, Bullet  # type: ignore


@dataclass(frozen=True)
class SkillHit:
    skill_id: str
    skill_name: str
    matched_phrase: str       # the literal phrase we found (from name or aliases)
    match_source: str         # "name" | "alias"
    level: str
    years: int
    is_primary: bool
    interview_depth: bool


@dataclass(frozen=True)
class GapHit:
    canonical: str            # from gaps.not_hands_on
    matched_phrase: str       # the phrase that appeared in the JD
    severity: str             # "hard" | "soft"


@dataclass(frozen=True)
class VariantScore:
    variant: str              # "ALM" | "VAL" | "VEN" | "QUANT" | "CON"
    bullets_supporting: int
    skills_supporting: int
    rank_score: float         # higher = stronger fit


# ---------------------------------------------------------------------------
# Phrase matching
# ---------------------------------------------------------------------------
# Words shorter than 3 chars get literal anchoring (e.g., "R" → must be
# whole-token, not part of "Risk"). Otherwise we use a case-insensitive
# word-boundary match. Punctuation-heavy phrases (e.g. "IRRBB", "B-12") are
# regex-escaped so the hyphen matches literally.
_WORD_CHAR = r"[A-Za-z0-9]"


def _build_pattern(phrase: str) -> re.Pattern:
    """Build a case-insensitive regex that matches `phrase` as a phrase with
    word boundaries at both ends. Handles hyphens/slashes/punctuation via
    re.escape, then softens the internal whitespace so "parallel rate shock"
    matches "parallel  rate\nshock" too."""
    # Escape then relax internal whitespace
    esc = re.escape(phrase)
    esc = re.sub(r"\\\s+", r"\\s+", esc)
    # Word-boundary at each end. For phrases starting/ending with punctuation
    # (e.g. ".NET", "B-12"), \b doesn't fire — fall back to negative lookarounds
    # against word chars.
    left = r"(?<![A-Za-z0-9_])"
    right = r"(?![A-Za-z0-9_])"
    return re.compile(left + esc + right, flags=re.IGNORECASE)


def _find_phrase(jd: str, phrase: str) -> Optional[str]:
    """Return the first matched literal span (preserving JD casing), or None."""
    if not phrase or not jd:
        return None
    m = _build_pattern(phrase).search(jd)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------
@dataclass
class JDExtract:
    matched_skills: list[SkillHit]
    primary_hits: list[SkillHit]
    suggested_variants: list[VariantScore]
    gaps_flagged: list[GapHit]
    coverage_pct: float
    keywords_found: list[str]         # every distinct phrase that matched
    keywords_not_found_probes: list[str]  # common lane terms we specifically checked and didn't find
    skill_ids_matched: list[str]      # flat id list for downstream filters

    def as_prompt_block(self, max_items: int = 18) -> str:
        """Render a compact markdown block suitable for injection into an
        LLM prompt. Stays terse because the LLM is going to re-read it."""
        lines: list[str] = ["## Deterministic JD analysis (pre-computed, do not re-derive)"]
        lines.append(f"- coverage: **{self.coverage_pct:.0f}%** "
                     f"({len(self.matched_skills)} skill hits, "
                     f"{len(self.gaps_flagged)} gap hits)")
        if self.suggested_variants:
            top = ", ".join(f"{v.variant} ({v.bullets_supporting}b/{v.skills_supporting}s)"
                            for v in self.suggested_variants[:3])
            lines.append(f"- suggested variants (by bullet+skill support): {top}")
        if self.matched_skills:
            lines.append("- skills the JD calls for that Saber has evidence for:")
            for sh in self.matched_skills[:max_items]:
                primary = " **[PRIMARY]**" if sh.is_primary else ""
                lines.append(f"  - `{sh.skill_id}` ({sh.level}, {sh.years}y){primary} "
                             f"— matched on \"{sh.matched_phrase}\"")
        if self.gaps_flagged:
            lines.append("- **GAPS flagged** — JD mentions these, Saber is NOT hands-on:")
            for g in self.gaps_flagged:
                lines.append(f"  - \"{g.matched_phrase}\" (gap: {g.canonical})")
        if self.keywords_not_found_probes:
            lines.append(f"- lane-probe negatives (not in JD, informational): "
                         f"{', '.join(self.keywords_not_found_probes[:8])}")
        return "\n".join(lines)


# Lane-check probes — high-signal phrases we specifically test for so the
# caller knows which lane the JD does NOT belong to even when nothing matched.
_LANE_PROBES = [
    "IRRBB", "ALM", "LDI", "model validation", "model governance",
    "model risk", "treasury", "balance sheet", "liquidity",
    "stress testing", "aladdin", "bloomberg", "msci", "python",
    "derivatives", "fixed income",
]


def extract(jd_text: str, repo: Optional[MasterRepo] = None,
            max_skills: int = 40) -> JDExtract:
    """Run the full deterministic extraction on a JD text."""
    repo = repo or _load_repo()
    jd = jd_text or ""

    # 1. Skill matching — walk every skill, try name first then aliases.
    matched: list[SkillHit] = []
    seen_skill_ids: set[str] = set()
    keywords_found: list[str] = []

    for sk in repo.skills.values():
        hit: Optional[SkillHit] = None
        m = _find_phrase(jd, sk.name)
        if m:
            hit = SkillHit(
                skill_id=sk.id, skill_name=sk.name, matched_phrase=m,
                match_source="name", level=sk.level, years=sk.years,
                is_primary=sk.is_primary, interview_depth=sk.interview_depth,
            )
        else:
            for alias in sk.aliases:
                m = _find_phrase(jd, alias)
                if m:
                    hit = SkillHit(
                        skill_id=sk.id, skill_name=sk.name, matched_phrase=m,
                        match_source="alias", level=sk.level, years=sk.years,
                        is_primary=sk.is_primary, interview_depth=sk.interview_depth,
                    )
                    break
        if hit and hit.skill_id not in seen_skill_ids:
            seen_skill_ids.add(hit.skill_id)
            matched.append(hit)
            keywords_found.append(hit.matched_phrase)

    # Rank matched skills: primary first, then by level ordinal desc, then years desc
    level_ord = {"expert": 3, "proficient": 2, "familiar": 1, "not_hands_on": 0}
    matched.sort(key=lambda h: (
        0 if h.is_primary else 1,
        -level_ord.get(h.level, 0),
        -h.years,
    ))
    matched = matched[:max_skills]
    primary_hits = [h for h in matched if h.is_primary]

    # 2. Gap detection — walk gaps.not_hands_on. Structured entries (with
    # `aliases`) are the expected format; legacy flat strings are supported
    # via the head-phrase splitting fallback.
    gaps_flagged: list[GapHit] = []
    gap_canonicals_seen: set[str] = set()

    def _record_gap(canonical: str, matched_phrase: str, severity: str) -> None:
        if canonical in gap_canonicals_seen:
            return
        gap_canonicals_seen.add(canonical)
        gaps_flagged.append(GapHit(
            canonical=canonical, matched_phrase=matched_phrase, severity=severity,
        ))
        keywords_found.append(matched_phrase)

    for entry in repo.gaps.get("not_hands_on", []) or []:
        if isinstance(entry, dict):
            canonical = entry.get("canonical", "")
            severity = entry.get("severity", "hard")
            probes = list(entry.get("aliases") or [])
            # Also use the canonical's head (pre-parenthesis) as a probe, so
            # "BlackRock Aladdin (hands-on user)" still matches "BlackRock
            # Aladdin" directly even if aliases list is sparse.
            head = canonical.split("(")[0].strip()
            if head and head not in probes:
                probes.insert(0, head)
        else:
            # Legacy flat-string form: "Java / C++"
            canonical = str(entry)
            severity = "hard"
            head = canonical.split("(")[0].strip()
            probes = [p.strip() for p in re.split(r"\s*/\s*", head) if p.strip()]

        for probe in probes:
            if len(probe) < 3:
                continue
            m = _find_phrase(jd, probe)
            if m:
                _record_gap(canonical, m, severity)
                break  # one hit per gap entry is enough

    # 3. Variant scoring — walk bullets, for each variant sum (1) distinct
    # bullets whose skill_ids intersect matched skill ids, (2) distinct matched
    # skill ids that are evidenced by that variant's bullets.
    matched_skill_ids = {h.skill_id for h in matched}
    by_variant_bullets: dict[str, set[str]] = {}
    by_variant_skills: dict[str, set[str]] = {}
    for b in repo.bullets.values():
        bullet_skill_hits = set(b.skill_ids) & matched_skill_ids
        if not bullet_skill_hits:
            continue
        for vt in b.variant_tags:
            by_variant_bullets.setdefault(vt, set()).add(b.id)
            by_variant_skills.setdefault(vt, set()).update(bullet_skill_hits)

    variants: list[VariantScore] = []
    for vt, bids in by_variant_bullets.items():
        sids = by_variant_skills.get(vt, set())
        rank = 1.5 * len(bids) + 1.0 * len(sids)
        variants.append(VariantScore(
            variant=vt,
            bullets_supporting=len(bids),
            skills_supporting=len(sids),
            rank_score=round(rank, 2),
        ))
    variants.sort(key=lambda v: -v.rank_score)

    # 4. Lane probes — report which high-signal phrases are NOT in the JD.
    not_found: list[str] = []
    jd_lower = jd.lower()
    for probe in _LANE_PROBES:
        if probe.lower() not in jd_lower:
            not_found.append(probe)

    # 5. Coverage
    matched_count = len(matched)
    gap_count = len(gaps_flagged)
    denom = matched_count + gap_count
    coverage_pct = (100.0 * matched_count / denom) if denom > 0 else 0.0

    return JDExtract(
        matched_skills=matched,
        primary_hits=primary_hits,
        suggested_variants=variants,
        gaps_flagged=gaps_flagged,
        coverage_pct=round(coverage_pct, 1),
        keywords_found=sorted(set(keywords_found)),
        keywords_not_found_probes=not_found,
        skill_ids_matched=sorted(matched_skill_ids),
    )


# ---------------------------------------------------------------------------
# Bullet shortlist — consumed by jd_tailor
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RankedBullet:
    bullet_id: str
    text: str
    variant_tags: tuple[str, ...]
    role_id: str
    skill_ids_matched: tuple[str, ...]  # intersection with JD-matched skills
    rank_score: float


def rank_bullets(jd_extract: JDExtract, repo: Optional[MasterRepo] = None,
                 variants: Optional[Iterable[str]] = None,
                 limit: int = 20) -> list[RankedBullet]:
    """Return bullets ranked by relevance to the JD.

    Score = (# matched primary skills × 2) + (# matched non-primary skills)
          + (metric bonus 0.5 if has_metric)
          + (variant-fit bonus: 1.0 if bullet has a tag in `variants`).

    `variants` defaults to the top 2 suggested variants from the extract.
    """
    repo = repo or _load_repo()
    matched_ids = set(jd_extract.skill_ids_matched)
    primary_matched = {h.skill_id for h in jd_extract.primary_hits}
    if variants is None:
        variants_set = {v.variant for v in jd_extract.suggested_variants[:2]}
    else:
        variants_set = set(variants)

    out: list[RankedBullet] = []
    for b in repo.bullets.values():
        hits = set(b.skill_ids) & matched_ids
        if not hits:
            continue
        primary_overlap = hits & primary_matched
        non_primary = hits - primary_matched
        score = 2.0 * len(primary_overlap) + 1.0 * len(non_primary)
        if b.has_metric:
            score += 0.5
        if set(b.variant_tags) & variants_set:
            score += 1.0
        out.append(RankedBullet(
            bullet_id=b.id, text=b.text, variant_tags=b.variant_tags,
            role_id=b.role_id,
            skill_ids_matched=tuple(sorted(hits)),
            rank_score=round(score, 2),
        ))
    out.sort(key=lambda x: -x.rank_score)
    return out[:limit]


def format_bullet_shortlist(ranked: list[RankedBullet], group_by_role: bool = True) -> str:
    """Render the shortlist as a markdown block for an LLM prompt."""
    if not ranked:
        return "(no bullets matched — tailor must select from full §5 library)"
    lines = ["## Pre-ranked bullet shortlist (select from here; highest-ranked first)"]
    if group_by_role:
        by_role: dict[str, list[RankedBullet]] = {}
        for b in ranked:
            by_role.setdefault(b.role_id, []).append(b)
        for role_id, bs in by_role.items():
            lines.append(f"\n### {role_id}")
            for b in bs:
                tags = "".join(f"[{t}]" for t in b.variant_tags)
                skill_str = ", ".join(b.skill_ids_matched[:4])
                lines.append(f"- `{b.bullet_id}` (score={b.rank_score}) {tags} "
                             f"[matches: {skill_str}]")
                lines.append(f"  > {b.text}")
    else:
        for b in ranked:
            tags = "".join(f"[{t}]" for t in b.variant_tags)
            lines.append(f"- `{b.bullet_id}` (score={b.rank_score}) {tags}")
            lines.append(f"  > {b.text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI — smoke test against a pasted JD
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd-file", help="Path to JD text file")
    ap.add_argument("--jd-text", help="JD text inline")
    ap.add_argument("--sample", action="store_true",
                    help="Use a canned sample JD for a quick smoke test")
    args = ap.parse_args()

    if args.sample:
        jd = (
            "Director, ALM & Balance Sheet Risk — Scotiabank Treasury\n\n"
            "We are seeking a senior leader to oversee our IRRBB analytics and "
            "liquidity risk measurement across the banking book. You will own EVE "
            "and NII sensitivity modelling, lead the cash flow projection and "
            "liquidity gap frameworks, and work closely with the model validation "
            "team on governance reviews aligned with OSFI B-12 and OSFI E-23.\n\n"
            "Required: deep ALM + IRRBB expertise, LDI or stochastic modelling, "
            "Python, experience with yield curve construction, stress testing under "
            "parallel and non-parallel rate shocks. BlackRock Aladdin exposure a plus."
        )
    elif args.jd_text:
        jd = args.jd_text
    elif args.jd_file:
        from pathlib import Path
        jd = Path(args.jd_file).read_text(encoding="utf-8")
    else:
        print("Pass --sample, --jd-text, or --jd-file", file=sys.stderr)
        return 2

    ex = extract(jd)
    print(ex.as_prompt_block())
    print()
    print("=" * 60)
    ranked = rank_bullets(ex)
    print(format_bullet_shortlist(ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
