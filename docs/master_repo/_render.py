#!/usr/bin/env python3
"""
_render.py — Regenerate docs/Saber_Ayatollahi_Master_Repository.md from the
YAML sources in this directory.

The rendered .md is a BUILD ARTIFACT. Do not hand-edit it — edit the YAMLs
and re-run:
    python docs/master_repo/_render.py

The renderer preserves the exact section-header anchors that fit_scorer.py
string-matches against:
    - "## 4. SKILLS INVENTORY"
    - "## 7. TARGET ROLE POSITIONING"
    - "## 10. RESUME VARIANTS"
so changing the YAML structure does not break the scorer.

Usage:
    python _render.py               # write docs/Saber_Ayatollahi_Master_Repository.md
    python _render.py --stdout      # print to stdout (for diffing in CI)
    python _render.py --check       # fail non-zero if the on-disk .md drifts
                                      from what we would render (useful as a
                                      pre-commit hook).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
OUT_MD = REPO_ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"


def _load(name: str) -> dict:
    p = HERE / f"{name}.yaml"
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{name}.yaml must be a mapping at the top level")
    return data


def _skill_by_id(skills: list[dict]) -> dict[str, dict]:
    return {s["id"]: s for s in skills}


def _bullet_by_id(bullets: list[dict]) -> dict[str, dict]:
    return {b["id"]: b for b in bullets}


# ---------------------------------------------------------------------------
# §1 — Identity & contact
# ---------------------------------------------------------------------------
def render_identity(id_data: dict) -> list[str]:
    comp = id_data["target_comp_cad"]
    rows = [
        ("Name", id_data["full_name_with_credentials"]),
        ("Location", id_data["location"]),
        ("Phone", id_data["phone"]),
        ("Email", id_data["email"]),
        ("LinkedIn", id_data["linkedin"]),
        ("Languages", ", ".join(
            f"{l['name']} ({l['level']})" for l in id_data["languages"]
        )),
        ("Work authorization", id_data["work_authorization"]["display_phrase"]),
        ("Notice period", id_data["notice_period"]["display_phrase"]),
        ("Target comp band (CAD)", comp["display_phrase"]),
        ("Relocation", id_data["relocation"]["display_phrase"]),
        ("Availability", id_data["availability_phrase"]),
    ]
    lines = [
        "## 1. IDENTITY & CONTACT",
        "",
        "| | |",
        "|---|---|",
    ]
    for k, v in rows:
        lines.append(f"| **{k}** | {v} |")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §2 — Education & credentials
# ---------------------------------------------------------------------------
def render_education(edu: dict) -> list[str]:
    lines = [
        "## 2. EDUCATION & CREDENTIALS",
        "",
        "| Credential | Institution | Year |",
        "|---|---|---|",
    ]
    for c in edu["credentials"]:
        # Bold only the credential name; the scholarship suffix is italicized
        # OUTSIDE the bold span to match the original rendering.
        if c.get("scholarship"):
            name_col = f"**{c['name']}** *({c['scholarship']})*"
        else:
            name_col = f"**{c['name']}**"
        lines.append(f"| {name_col} | {c['institution']} | {c['year']} |")
    lines.append("")
    lines.append("### Why these matter")
    lines.append(edu["why_these_matter_md"].rstrip())
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §3 — Professional experience
# ---------------------------------------------------------------------------
def render_experience(roles_data: dict, projects: list[dict]) -> list[str]:
    """Render §3. The §3 narrative is wrapped in ** bold in the original to
    emphasize the years figure — preserve that. Section separators (---) go
    BETWEEN roles, not after the last one (the top-level driver adds the final
    separator before §4)."""
    proj_by_id = {p["id"]: p for p in projects}
    lines = ["## 3. PROFESSIONAL EXPERIENCE", ""]
    # Original wraps the entire narrative in ** — not just the year count.
    lines.append(
        f"Years of experience: **~{roles_data['experience_years_as_of_2026_05']} "
        "years full-time finance experience** (Feb 2019 → May 2026). "
        "Reference this consistently — avoid \"8+\" or \"10+\" phrasing that doesn't match."
    )
    lines.append("")

    for i, role in enumerate(roles_data["roles"], 1):
        heading = f"### 3.{i} {role['employer']}"
        if role.get("division"):
            heading += f" — {role['division']}"
        lines.append(heading)
        lines.append(f"**Role:** {role['title']}")
        lines.append(f"**Location:** {role['location']}")
        lines.append(f"**Period:** {role['period_display']}")
        if role.get("team_size_scope"):
            lines.append(f"**Team size / scope:** {role['team_size_scope']}")
        lines.append("")

        if role.get("phases"):
            for phase in role["phases"]:
                lines.append(f"#### {phase['name']} ({phase['period_display']})")
                for b in phase.get("ongoing_responsibilities", []):
                    lines.append(f"- {b}")
                for pid in phase.get("project_ids", []):
                    proj = proj_by_id.get(pid)
                    if not proj or not proj.get("narrative_for_section3_md"):
                        continue
                    for line in proj["narrative_for_section3_md"].rstrip().splitlines():
                        lines.append(line)
                for b in phase.get("closing_responsibilities", []):
                    lines.append(f"- {b}")
                lines.append("")
        else:
            for b in role.get("ongoing_responsibilities", []):
                lines.append(f"- {b}")
            lines.append("")

        # Separator between roles only — not after the last role (the
        # section-driver adds a --- before §4).
        if i < len(roles_data["roles"]):
            lines.append("---")
            lines.append("")

    return lines


# ---------------------------------------------------------------------------
# §4 — Skills inventory (evidenced)
# CRITICAL: header "## 4. SKILLS INVENTORY" must match fit_scorer exactly.
# ---------------------------------------------------------------------------
def render_skills(sk_data: dict) -> list[str]:
    """Render §4. Order: 4.1–4.8 → Removed-from-v1 note → 4.9 Regulatory
    (from regulatory_context_md) → 4.10 Leadership. Each skill renders its
    `display` string if present, otherwise `name`. Skills with
    `skip_in_section4: true` are omitted (they're bundled into a parent
    skill's display line to match the original §4 phrasing)."""
    skills = sk_data["skills"]
    lines = [
        "## 4. SKILLS INVENTORY (evidenced)",
        "",
        "> **Rule:** no skill lives here without evidence in Section 3. "
        "If it's not in the experience section, it doesn't belong.",
        "",
    ]

    for cat in sk_data["category_order"]:
        cat_id = cat["id"]

        # Markdown-only categories (4.9 regulatory) render from a prose block
        if cat.get("is_markdown_only"):
            md = sk_data.get("regulatory_context_md", "").rstrip()
            # The regulatory_context_md already contains its own ### heading;
            # trust it rather than re-emitting the category display.
            if md:
                lines.append(md)
                lines.append("")
            continue

        lines.append(f"### {cat['display']}")
        if cat_id == "programming_technical":
            for group in sk_data["programming_technical_display_groups"]:
                lines.append(f"**{group['heading']}**")
                for entry in group["lines"]:
                    lines.append(f"- {entry['text']}")
                lines.append("")
            # Removed-from-v1 note goes immediately after §4.8 Programming,
            # before §4.9 Regulatory (matches original ordering).
            if sk_data.get("removed_from_v1_md"):
                lines.append(sk_data["removed_from_v1_md"].rstrip())
                lines.append("")
        else:
            for sk in skills:
                if sk.get("category") != cat_id:
                    continue
                if sk.get("skip_in_section4"):
                    continue
                display = sk.get("display") or sk["name"]
                lines.append(f"- {display}")
            lines.append("")

    return lines


# ---------------------------------------------------------------------------
# §5 — Tagged bullet library
# ---------------------------------------------------------------------------
def render_bullets(bullets_data: dict) -> list[str]:
    lines = ["## 5. TAGGED BULLET LIBRARY", "", "> **Tags:**"]
    legend = bullets_data["variant_tags_legend"]
    for tag, desc in legend.items():
        lines.append(f"> `[{tag}]` = {desc}")
    lines.append("")

    by_id = _bullet_by_id(bullets_data["bullets"])
    for group in bullets_data["section_groups"]:
        lines.append(f"### {group['heading']}")
        lines.append("")
        for bid in group["bullet_ids"]:
            b = by_id.get(bid)
            if not b:
                continue
            tags = " ".join(f"[{t}]" for t in b["variant_tags"])
            # Original format: `[ALM][VAL]` Text... (joined without space between brackets)
            joined_tags = "".join(f"[{t}]" for t in b["variant_tags"])
            lines.append(f"- `{joined_tags}` {b['text']}")
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §6 — STAR story bank
# ---------------------------------------------------------------------------
def render_stories(stories_data: dict) -> list[str]:
    lines = ["## 6. STAR STORY BANK *(for behavioral interviews)*", ""]
    for st in stories_data["stories"]:
        lines.append(f"### Story {st['number']} — \"{st['title']}\"")
        lines.append(f"**Situation:** {st['situation'].strip()}")
        lines.append(f"**Task:** {st['task'].strip()}")
        lines.append(f"**Action:** {st['action'].strip()}")
        lines.append(f"**Result:** {st['result'].strip()}")
        tags_disp = " ".join(f"`[{t}]`" for t in st["tags"])
        lines.append(f"**Tags:** {tags_disp}")
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §7 — Target role positioning
# CRITICAL: "## 7. TARGET ROLE POSITIONING" must match fit_scorer exactly.
# ---------------------------------------------------------------------------
def render_positioning(pos_data: dict) -> list[str]:
    """Render §7. Intra-section '---' separators between angles are PART of
    §7 (original has them there). The inter-section separator before §8 is
    added by the top-level driver — so we trim trailing '---' here."""
    lines = [
        "## 7. TARGET ROLE POSITIONING — **TWO ANGLES ONLY**",
        "",
        f"> **Decision {pos_data['positioning_decision_date']}:** "
        f"{pos_data['positioning_decision_note'].strip()}",
        "",
    ]
    angles = pos_data["angles"]
    for idx, angle in enumerate(angles):
        is_last = idx == len(angles) - 1
        if angle.get("adhoc_only"):
            lines.append(
                f"### {angle['number']} — Ad-hoc third lane: {angle['name']} (opportunistic)"
            )
            lines.append(angle["trigger_description"].strip())
            lines.append("")
        else:
            rank_label = angle["rank"].upper()
            lines.append(f"### {angle['number']} — {rank_label}: {angle['name']}")
            lines.append("**Best-fit titles:** " + " · ".join(angle["best_fit_titles"]))
            lines.append("")
            lines.append("**Evidence stack:** " + " · ".join(angle["evidence_stack"]) + ".")
            lines.append("")
            lines.append(f"**Summary angle ({angle['summary_words']} words):**")
            lines.append(f"> {angle['summary_text'].strip()}")
            lines.append("")
            emp_bullets = angle.get("target_employers") or []
            lines.append("**Target employers:** " + "; ".join(emp_bullets) + ".")
            lines.append("")
        if not is_last:
            lines.append("---")
            lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §8 — Summary-statement bank
# ---------------------------------------------------------------------------
def _display_id(sid: str) -> str:
    """Summary IDs in the .md use dash-separated slugs (v-ALM-short). YAML
    uses underscore-separated (v_alm_short). Round-trip back to the original
    form for the .md output so it stays byte-stable with v1."""
    # v_alm_short -> v-ALM-short. Heuristic: split on _, upper-case the
    # 2nd segment (the tag), keep the rest lowercase.
    parts = sid.split("_")
    if len(parts) >= 2:
        parts[1] = parts[1].upper()
    return "-".join(parts)


def render_summaries(sum_data: dict) -> list[str]:
    lines = [
        "## 8. SUMMARY-STATEMENT BANK",
        "",
        "### Short (LinkedIn headline, 150 chars)",
    ]
    for s in sum_data["short_linkedin"]:
        lines.append(f"- `{_display_id(s['id'])}` *{s['text']}*")
    lines.append("")
    lines.append("### Medium (resume header, 40–70 words)")
    lines.append("Covered in §7.1 and §7.2.")
    lines.append("")
    lines.append("### Long (cover-letter opening paragraph, 110–140 words)")
    lines.append("")
    for s in sum_data["long_cover_letter"]:
        lines.append(f"- `{_display_id(s['id'])}`")
        lines.append(f"> {s['text'].strip()}")
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §9 — Logistics & housekeeping
# ---------------------------------------------------------------------------
def render_logistics(log: dict) -> list[str]:
    lines = [
        "## 9. LOGISTICS & HOUSEKEEPING",
        "",
        "### Work authorization",
        log["work_auth_confirmation_phrase"].strip(),
        "",
        "### Notice period and earliest start",
        log["notice_and_start_phrase"],
        "",
        "### Salary anchoring by tier",
        f"See `{log['salary_bands_reference_file']}` for detailed band research.",
    ]
    for band in log["salary_bands"]:
        lines.append(f"- {band['display']}")
    lines.append("")
    lines.append("### References (to confirm with Saber)")
    for r in log["references"]:
        desc = r["description"]
        flavor = r["flavor"]
        if desc:
            lines.append(f"- {r['source']}: {desc} — **{flavor}**")
        else:
            lines.append(f"- {r['source']} — **{flavor}**")
    lines.append(log["references_instruction"])
    lines.append("")
    lines.append("### Publications / speaking / thought leadership")
    lines.append(log["publications_speaking_note"].strip())
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §10 — Resume variants on file
# CRITICAL: "## 10. RESUME VARIANTS" must match fit_scorer exactly.
# ---------------------------------------------------------------------------
def render_variants(var_data: dict) -> list[str]:
    lines = [
        f"## 10. RESUME VARIANTS ON FILE (update {var_data['update_date']})",
        "",
        "| Variant | Role focus | File | Status |",
        "|---|---|---|---|",
    ]
    for v in var_data["variants"]:
        lines.append(
            f"| {v['label']} | {v['role_focus']} | `{v['file']}` | {v['status']} |"
        )
    lines.append("")
    retired = ", ".join(var_data["retired"])
    lines.append(f"Retired variants (no longer in rotation): {retired}.")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# §11 — Job-search strategy notes
# ---------------------------------------------------------------------------
def render_strategy(strat: dict) -> list[str]:
    lines = ["## 11. JOB-SEARCH STRATEGY NOTES", ""]
    lines.append(strat["strategy_notes_md"].rstrip())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(strat["last_updated_footer"])
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Top-of-document preamble
# ---------------------------------------------------------------------------
PREAMBLE = """# Saber Ayatollahi — Master Career Repository (v2)

> **Purpose:** Single source of truth for resume and cover-letter generation. Every role-specific resume, cover letter, and LinkedIn snippet must draft from this document. The rewrite (2026-05-03) narrows positioning, adds a tagged bullet library for fast recombination, and captures a STAR story bank for interviews.

> **How to use this file:**
> 1. Sections 1–3 = identity, education, experience (factual spine).
> 2. Section 4 = evidenced skills inventory — **do not add skills not backed by Section 3**.
> 3. Section 5 = tagged bullet library — pick bullets by `[TAG]` for any resume variant.
> 4. Section 6 = STAR story bank for behavioral interviews.
> 5. Section 7 = role angles — **two primary**, not seven. All outbound focuses here.
> 6. Sections 8–11 = logistics, summary-statement bank, resume variants, job-search strategy.

> **Generated from:** `docs/master_repo/*.yaml`. Regenerate with `python docs/master_repo/_render.py`. Do not hand-edit this file.

---

"""


def render_all() -> str:
    identity = _load("identity")
    education = _load("education")
    roles = _load("roles")
    projects = _load("projects")["projects"]
    skills = _load("skills")
    bullets = _load("bullets")
    stories = _load("stories")
    positioning = _load("positioning")
    summaries = _load("summaries")
    logistics = _load("logistics")
    variants = _load("variants")
    strategy = _load("strategy")

    parts: list[str] = [PREAMBLE.rstrip("\n")]
    parts.append("")

    sections = [
        render_identity(identity),
        render_education(education),
        render_experience(roles, projects),
        render_skills(skills),
        render_bullets(bullets),
        render_stories(stories),
        render_positioning(positioning),
        render_summaries(summaries),
        render_logistics(logistics),
        render_variants(variants),
        render_strategy(strategy),
    ]

    for i, sec_lines in enumerate(sections):
        # Each section already carries its own leading header; separate with
        # "---" between top-level sections, matching the original file.
        parts.extend(sec_lines)
        # Ensure section-separator except after the last (strategy emits
        # its own trailing footer).
        if i < len(sections) - 1:
            if not parts[-1].strip() == "---":
                parts.append("---")
                parts.append("")

    out = "\n".join(parts).rstrip() + "\n"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true",
                    help="Print to stdout instead of writing the .md file.")
    ap.add_argument("--check", action="store_true",
                    help="Exit non-zero if the on-disk .md differs from what would be rendered.")
    args = ap.parse_args()

    text = render_all()
    if args.stdout:
        sys.stdout.write(text)
        return 0
    if args.check:
        current = OUT_MD.read_text(encoding="utf-8") if OUT_MD.exists() else ""
        if current != text:
            print(f"DRIFT: {OUT_MD} is out of sync with YAML sources.\n"
                  f"       Run: python {Path(__file__).relative_to(REPO_ROOT)}",
                  file=sys.stderr)
            return 1
        print(f"OK: {OUT_MD} matches YAML sources.")
        return 0
    OUT_MD.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_MD} ({len(text)} chars, {text.count(chr(10)) + 1} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
