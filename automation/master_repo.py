#!/usr/bin/env python3
"""
master_repo.py — Structured loader over docs/master_repo/*.yaml.

Future callers (fit_scorer, jd_tailor, agentic pipelines) should import this
module instead of re-parsing the rendered .md. It exposes typed accessors
keyed by stable IDs so you can write:

    repo = load()
    matching = repo.bullets_matching(variants={"ALM"}, skill_ids={"sk_irrbb"})
    coverage = repo.score_jd_skills(["IRRBB", "LDI", "Python"])

and get deterministic, cacheable outputs instead of LLM-vibes extraction.

The loader is intentionally small: YAML in, dataclasses out, a handful of
query helpers. No network calls, no Anthropic SDK dependency.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

try:
    import yaml  # type: ignore
except ImportError as e:
    raise RuntimeError("pip install pyyaml — master_repo loader requires it") from e

REPO_ROOT = Path(__file__).resolve().parent.parent
MASTER_REPO_DIR = REPO_ROOT / "docs" / "master_repo"


# ---------------------------------------------------------------------------
# Dataclasses — kept deliberately shallow; each wraps the YAML dict and
# exposes the frequently-used fields. Unused fields are accessible via .raw.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Role:
    id: str
    employer: str
    title: str
    period_display: str
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    role_id: str
    skill_ids: tuple[str, ...]
    status: str
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    category: str
    level: str              # expert | proficient | familiar | not_hands_on
    years: int
    aliases: tuple[str, ...]
    evidence_project_ids: tuple[str, ...]
    evidence_role_ids: tuple[str, ...]
    interview_depth: bool
    is_primary: bool
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class Bullet:
    id: str
    text: str
    variant_tags: tuple[str, ...]
    role_id: str
    project_id: Optional[str]
    skill_ids: tuple[str, ...]
    has_metric: bool
    length: str
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class Story:
    id: str
    number: int
    title: str
    tags: tuple[str, ...]
    skill_ids: tuple[str, ...]
    project_ids: tuple[str, ...]
    raw: dict = field(repr=False)


# Level ordinals for "is-this-skill-deep-enough-to-claim" queries
_LEVEL_ORD = {"not_hands_on": 0, "familiar": 1, "proficient": 2, "expert": 3}


@dataclass
class MasterRepo:
    identity: dict
    education: dict
    roles: dict[str, Role]
    projects: dict[str, Project]
    skills: dict[str, Skill]
    bullets: dict[str, Bullet]
    stories: dict[str, Story]
    positioning: dict
    summaries: dict
    logistics: dict
    variants: dict
    strategy: dict
    achievements: list
    keyword_bank: list
    gaps: dict

    # -----------------------------------------------------------------
    # Skill queries
    # -----------------------------------------------------------------
    def skill(self, sid: str) -> Optional[Skill]:
        return self.skills.get(sid)

    def skills_by_category(self, category: str) -> list[Skill]:
        return [s for s in self.skills.values() if s.category == category]

    def primary_skills(self) -> list[Skill]:
        return [s for s in self.skills.values() if s.is_primary]

    def skill_level_ord(self, sid: str) -> int:
        sk = self.skills.get(sid)
        return _LEVEL_ORD.get(sk.level, 0) if sk else 0

    def find_skill_by_alias(self, term: str) -> Optional[Skill]:
        """Case-insensitive match against name + aliases. Returns the skill
        whose name/aliases contain the longest overlap with `term`.

        Useful when the JD mentions "EVE sensitivity" or "liquidity gap" and
        you want the structured skill record back without LLM help."""
        t = term.strip().lower()
        best: tuple[int, Optional[Skill]] = (0, None)
        for sk in self.skills.values():
            candidates = [sk.name] + list(sk.aliases)
            for c in candidates:
                cl = c.lower()
                # Full containment either direction
                if t == cl or t in cl or cl in t:
                    overlap = len(cl) if cl in t or t in cl else 0
                    if overlap > best[0]:
                        best = (overlap, sk)
        return best[1]

    # -----------------------------------------------------------------
    # Bullet queries
    # -----------------------------------------------------------------
    def bullets_matching(
        self,
        variants: Optional[set[str]] = None,
        skill_ids: Optional[set[str]] = None,
        role_id: Optional[str] = None,
        project_id: Optional[str] = None,
        has_metric: Optional[bool] = None,
    ) -> list[Bullet]:
        """Return bullets satisfying all provided filters (AND semantics).

        - `variants`: match if any variant_tag in the bullet is in the set.
        - `skill_ids`: match if any skill_id overlaps.
        - `role_id` / `project_id` / `has_metric`: exact match.
        """
        out: list[Bullet] = []
        for b in self.bullets.values():
            if variants and not (set(b.variant_tags) & variants):
                continue
            if skill_ids and not (set(b.skill_ids) & skill_ids):
                continue
            if role_id and b.role_id != role_id:
                continue
            if project_id and b.project_id != project_id:
                continue
            if has_metric is not None and b.has_metric != has_metric:
                continue
            out.append(b)
        return out

    # -----------------------------------------------------------------
    # Story queries
    # -----------------------------------------------------------------
    def stories_matching(
        self,
        variants: Optional[set[str]] = None,
        skill_ids: Optional[set[str]] = None,
    ) -> list[Story]:
        out: list[Story] = []
        for st in self.stories.values():
            tags = set(st.tags)
            if variants and not (tags & variants) and "ALL" not in tags:
                continue
            if skill_ids and not (set(st.skill_ids) & skill_ids):
                continue
            out.append(st)
        return out

    # -----------------------------------------------------------------
    # JD coverage — deterministic skill scoring
    # -----------------------------------------------------------------
    def score_jd_skills(
        self,
        jd_keywords: Iterable[str],
    ) -> dict:
        """Given a set of JD-extracted keywords, return which skills match
        (by name OR alias), at what level, and what's missing.

        Returns:
            {
                "matched": [ {keyword, skill_id, skill_name, level, years} ],
                "missed":  [keyword, ...],
                "coverage_pct": 0-100,
                "primary_hits": [skill_id, ...],
            }
        """
        matched: list[dict] = []
        missed: list[str] = []
        primary_hits: set[str] = set()
        seen_skills: set[str] = set()

        for kw in jd_keywords:
            sk = self.find_skill_by_alias(kw)
            if sk is None:
                missed.append(kw)
                continue
            if sk.id not in seen_skills:
                seen_skills.add(sk.id)
                if sk.is_primary:
                    primary_hits.add(sk.id)
            matched.append({
                "keyword": kw,
                "skill_id": sk.id,
                "skill_name": sk.name,
                "level": sk.level,
                "years": sk.years,
            })

        total = max(len(list(jd_keywords)) if not isinstance(jd_keywords, list) else len(jd_keywords), 1)
        # Recompute total accurately (jd_keywords may be a one-shot iterator)
        n_matched = len(matched)
        n_missed = len(missed)
        total = n_matched + n_missed or 1

        return {
            "matched": matched,
            "missed": missed,
            "coverage_pct": round(100 * n_matched / total, 1),
            "primary_hits": sorted(primary_hits),
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _yaml(name: str) -> dict:
    with (MASTER_REPO_DIR / f"{name}.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _mk_role(d: dict) -> Role:
    return Role(id=d["id"], employer=d["employer"], title=d["title"],
                period_display=d["period_display"], raw=d)


def _mk_project(d: dict) -> Project:
    return Project(
        id=d["id"], name=d["name"], role_id=d["role_id"],
        skill_ids=tuple(d.get("skill_ids") or []),
        status=d.get("status", ""), raw=d,
    )


def _mk_skill(d: dict) -> Skill:
    return Skill(
        id=d["id"], name=d["name"], category=d["category"],
        level=d.get("level", "familiar"),
        years=int(d.get("years") or 0),
        aliases=tuple(d.get("aliases") or []),
        evidence_project_ids=tuple(d.get("evidence_project_ids") or []),
        evidence_role_ids=tuple(d.get("evidence_role_ids") or []),
        interview_depth=bool(d.get("interview_depth") or False),
        is_primary=bool(d.get("is_primary") or False),
        raw=d,
    )


def _mk_bullet(d: dict) -> Bullet:
    return Bullet(
        id=d["id"], text=d["text"],
        variant_tags=tuple(d.get("variant_tags") or []),
        role_id=d["role_id"], project_id=d.get("project_id"),
        skill_ids=tuple(d.get("skill_ids") or []),
        has_metric=bool(d.get("has_metric") or False),
        length=d.get("length", "full"),
        raw=d,
    )


def _mk_story(d: dict) -> Story:
    return Story(
        id=d["id"], number=int(d.get("number") or 0), title=d["title"],
        tags=tuple(d.get("tags") or []),
        skill_ids=tuple(d.get("skill_ids") or []),
        project_ids=tuple(d.get("project_ids") or []),
        raw=d,
    )


@lru_cache(maxsize=1)
def load() -> MasterRepo:
    """Load and cache the full repo. Cheap on second call. If YAMLs change
    on disk you must call `load.cache_clear()` to re-read."""
    identity = _yaml("identity")
    education = _yaml("education")
    roles_raw = _yaml("roles")["roles"]
    projects_raw = _yaml("projects")["projects"]
    skills_data = _yaml("skills")
    skills_raw = skills_data["skills"]
    bullets_raw = _yaml("bullets")["bullets"]
    stories_raw = _yaml("stories")["stories"]
    positioning = _yaml("positioning")
    summaries = _yaml("summaries")
    logistics = _yaml("logistics")
    variants = _yaml("variants")
    strategy = _yaml("strategy")
    achievements = _yaml("achievements")["achievements"]
    keyword_bank = _yaml("keyword_bank")["aliases"]

    return MasterRepo(
        identity=identity,
        education=education,
        roles={r["id"]: _mk_role(r) for r in roles_raw},
        projects={p["id"]: _mk_project(p) for p in projects_raw},
        skills={s["id"]: _mk_skill(s) for s in skills_raw},
        bullets={b["id"]: _mk_bullet(b) for b in bullets_raw},
        stories={s["id"]: _mk_story(s) for s in stories_raw},
        positioning=positioning,
        summaries=summaries,
        logistics=logistics,
        variants=variants,
        strategy=strategy,
        achievements=achievements,
        keyword_bank=keyword_bank,
        gaps=skills_data.get("gaps") or {},
    )


if __name__ == "__main__":
    # Smoke test: load, print a quick shape summary, exercise the query paths
    repo = load()
    print(f"Roles:       {len(repo.roles):3d}   {sorted(repo.roles)}")
    print(f"Projects:    {len(repo.projects):3d}")
    print(f"Skills:      {len(repo.skills):3d}   ({len(repo.primary_skills())} primary)")
    print(f"Bullets:     {len(repo.bullets):3d}")
    print(f"Stories:     {len(repo.stories):3d}")
    print()
    print("Sample query — bullets matching ALM + sk_irrbb:")
    for b in repo.bullets_matching(variants={"ALM"}, skill_ids={"sk_irrbb"}):
        print(f"  [{b.id}] {b.text[:90]}...")
    print()
    print("Sample query — JD mentions 'IRRBB, LDI, Python, Aladdin':")
    score = repo.score_jd_skills(["IRRBB", "LDI", "Python", "Aladdin"])
    print(f"  coverage: {score['coverage_pct']}%  primary_hits: {score['primary_hits']}")
    print(f"  matched:  {[m['skill_id'] for m in score['matched']]}")
    print(f"  missed:   {score['missed']}")
