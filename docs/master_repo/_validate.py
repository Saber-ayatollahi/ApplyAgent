#!/usr/bin/env python3
"""
_validate.py — Referential-integrity checks for the Master Repository YAMLs.

Run before committing edits to the repo. Fails loudly on:
  - Duplicate IDs (skill_id, project_id, role_id, bullet_id, story_id)
  - Dangling references (bullet.skill_id pointing to a missing skill, etc.)
  - Variant tags outside the declared legend
  - Skills in `skill_category_order` that no skill belongs to
  - Bullets referenced in bullets.section_groups that don't exist

Usage:
    python docs/master_repo/_validate.py           # exits non-zero on failure
    python docs/master_repo/_validate.py --json    # machine-readable report
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent


def _load(name: str) -> dict:
    p = HERE / f"{name}.yaml"
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{name}.yaml must be a mapping at the top level")
    return data


def _collect_duplicates(items: list, key: str) -> list[str]:
    seen: dict[str, int] = {}
    dups: list[str] = []
    for it in items:
        k = it.get(key)
        if k is None:
            continue
        seen[k] = seen.get(k, 0) + 1
    for k, n in seen.items():
        if n > 1:
            dups.append(k)
    return sorted(dups)


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def passed(self) -> bool:
        return not self.errors


def validate() -> Report:
    r = Report()

    roles = _load("roles")["roles"]
    projects = _load("projects")["projects"]
    skills_data = _load("skills")
    skills = skills_data["skills"]
    bullets_data = _load("bullets")
    bullets = bullets_data["bullets"]
    stories = _load("stories")["stories"]
    positioning = _load("positioning")
    variants = _load("variants")["variants"]
    achievements = _load("achievements")["achievements"]

    # -----------------------------------------------------------------
    # Duplicate IDs
    # -----------------------------------------------------------------
    for label, items in [
        ("roles", roles),
        ("projects", projects),
        ("skills", skills),
        ("bullets", bullets),
        ("stories", stories),
        ("variants", variants),
        ("achievements", achievements),
    ]:
        dups = _collect_duplicates(items, "id")
        for d in dups:
            r.err(f"duplicate id in {label}: {d}")

    role_ids = {ro["id"] for ro in roles}
    # Phase IDs
    phase_ids: set[str] = set()
    for ro in roles:
        for ph in ro.get("phases") or []:
            if ph["id"] in phase_ids:
                r.err(f"duplicate phase id: {ph['id']}")
            phase_ids.add(ph["id"])

    project_ids = {p["id"] for p in projects}
    skill_ids = {s["id"] for s in skills}
    bullet_ids = {b["id"] for b in bullets}

    # -----------------------------------------------------------------
    # Cross references: projects
    # -----------------------------------------------------------------
    for p in projects:
        if p.get("role_id") not in role_ids:
            r.err(f"project {p['id']}.role_id -> unknown role {p.get('role_id')!r}")
        if p.get("phase_id") and p["phase_id"] not in phase_ids:
            r.err(f"project {p['id']}.phase_id -> unknown phase {p['phase_id']!r}")
        for sid in p.get("skill_ids") or []:
            if sid not in skill_ids:
                r.err(f"project {p['id']}.skill_ids -> unknown skill {sid!r}")

    # -----------------------------------------------------------------
    # Cross references: roles
    # -----------------------------------------------------------------
    for ro in roles:
        for pid in ro.get("project_ids") or []:
            if pid not in project_ids:
                r.err(f"role {ro['id']}.project_ids -> unknown project {pid!r}")
        for ph in ro.get("phases") or []:
            for pid in ph.get("project_ids") or []:
                if pid not in project_ids:
                    r.err(f"role {ro['id']}.phase {ph['id']}.project_ids -> unknown project {pid!r}")

    # -----------------------------------------------------------------
    # Cross references: skills -> evidence
    # -----------------------------------------------------------------
    for sk in skills:
        for pid in sk.get("evidence_project_ids") or []:
            if pid not in project_ids:
                r.err(f"skill {sk['id']}.evidence_project_ids -> unknown project {pid!r}")
        for rid in sk.get("evidence_role_ids") or []:
            if rid not in role_ids:
                r.err(f"skill {sk['id']}.evidence_role_ids -> unknown role {rid!r}")

    # -----------------------------------------------------------------
    # Cross references: bullets
    # -----------------------------------------------------------------
    legal_tags = set(bullets_data["variant_tags_legend"].keys())
    for b in bullets:
        if b.get("role_id") not in role_ids:
            r.err(f"bullet {b['id']}.role_id -> unknown role {b.get('role_id')!r}")
        if b.get("project_id") and b["project_id"] not in project_ids:
            r.err(f"bullet {b['id']}.project_id -> unknown project {b['project_id']!r}")
        for sid in b.get("skill_ids") or []:
            if sid not in skill_ids:
                r.err(f"bullet {b['id']}.skill_ids -> unknown skill {sid!r}")
        for tag in b.get("variant_tags") or []:
            if tag not in legal_tags:
                r.err(f"bullet {b['id']}.variant_tags -> unknown tag {tag!r}")

    # Bullet section_groups reference real bullet ids
    for grp in bullets_data["section_groups"]:
        for bid in grp["bullet_ids"]:
            if bid not in bullet_ids:
                r.err(f"bullets.section_groups[{grp['heading']}].bullet_ids -> unknown bullet {bid!r}")
        if grp.get("role_id") and grp["role_id"] not in role_ids:
            r.err(f"bullets.section_groups[{grp['heading']}].role_id -> unknown role {grp['role_id']!r}")

    # -----------------------------------------------------------------
    # Cross references: stories
    # -----------------------------------------------------------------
    for st in stories:
        for sid in st.get("skill_ids") or []:
            if sid not in skill_ids:
                r.err(f"story {st['id']}.skill_ids -> unknown skill {sid!r}")
        for pid in st.get("project_ids") or []:
            if pid not in project_ids:
                r.err(f"story {st['id']}.project_ids -> unknown project {pid!r}")
        for tag in st.get("tags") or []:
            if tag not in legal_tags and tag != "ALL":
                r.err(f"story {st['id']}.tags -> unknown tag {tag!r} (use ALL or legend)")

    # -----------------------------------------------------------------
    # Cross references: positioning
    # -----------------------------------------------------------------
    for angle in positioning["angles"]:
        for tag in angle.get("linked_variants") or []:
            if tag not in legal_tags:
                r.err(f"positioning angle {angle['id']}.linked_variants -> unknown tag {tag!r}")
        for sid in angle.get("linked_skill_ids") or []:
            if sid not in skill_ids:
                r.err(f"positioning angle {angle['id']}.linked_skill_ids -> unknown skill {sid!r}")

    # -----------------------------------------------------------------
    # Cross references: variants & achievements
    # -----------------------------------------------------------------
    for v in variants:
        if v["variant_tag"] not in legal_tags:
            r.err(f"variant {v['id']}.variant_tag -> unknown tag {v['variant_tag']!r}")

    for a in achievements:
        if a.get("evidence_role_id") and a["evidence_role_id"] not in role_ids:
            r.err(f"achievement {a['id']}.evidence_role_id -> unknown role {a['evidence_role_id']!r}")
        for pid in a.get("evidence_project_ids") or []:
            if pid not in project_ids:
                r.err(f"achievement {a['id']}.evidence_project_ids -> unknown project {pid!r}")

    # -----------------------------------------------------------------
    # Skills category coverage
    # -----------------------------------------------------------------
    declared_cats = {c["id"] for c in skills_data["category_order"]}
    for sk in skills:
        if sk.get("category") not in declared_cats:
            r.err(f"skill {sk['id']}.category {sk.get('category')!r} not declared in category_order")

    for cat in skills_data["category_order"]:
        if cat.get("is_markdown_only"):
            continue
        matches = [sk for sk in skills if sk.get("category") == cat["id"]]
        if not matches:
            r.warn(f"category {cat['id']} has no skills assigned")

    # -----------------------------------------------------------------
    # Sanity: every skill in programming_technical_display_groups must exist
    # -----------------------------------------------------------------
    for grp in skills_data.get("programming_technical_display_groups") or []:
        for entry in grp["lines"]:
            sid = entry["skill_id"]
            if sid not in skill_ids:
                r.err(f"programming_technical_display_groups.{grp['heading']} -> unknown skill {sid!r}")

    # -----------------------------------------------------------------
    # Uncovered skills — warn only (a skill with no bullet using it is OK but
    # it means the tailor can't easily surface it)
    # -----------------------------------------------------------------
    bullet_skill_refs: set[str] = set()
    for b in bullets:
        for sid in b.get("skill_ids") or []:
            bullet_skill_refs.add(sid)
    for sk in skills:
        if sk.get("skip_in_section4"):
            continue
        if sk["id"] not in bullet_skill_refs and sk["category"] != "programming_technical":
            # Leadership & regulatory-awareness skills often have no bullet —
            # don't spam warnings for categories where that's expected.
            if sk["category"] not in ("leadership_communication",):
                r.warn(f"skill {sk['id']} has no bullet in bullets.yaml")

    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="Machine-readable report")
    ap.add_argument("--quiet", action="store_true", help="Only print on failure")
    args = ap.parse_args()

    rep = validate()
    if args.json:
        print(json.dumps({
            "passed": rep.passed(),
            "errors": rep.errors,
            "warnings": rep.warnings,
        }, indent=2))
        return 0 if rep.passed() else 1

    if rep.passed() and not args.quiet:
        print(f"OK: master_repo/*.yaml passes integrity checks "
              f"({len(rep.warnings)} warnings)")
    if rep.warnings and not args.quiet:
        print(f"\n{len(rep.warnings)} warning(s):")
        for w in rep.warnings:
            print(f"  [warn] {w}")
    if rep.errors:
        print(f"\n{len(rep.errors)} error(s):", file=sys.stderr)
        for e in rep.errors:
            print(f"  [err]  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
