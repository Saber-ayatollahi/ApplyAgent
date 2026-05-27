"""One-shot tracker schema migration. Idempotent; backups are caller's job."""
from __future__ import annotations

from datetime import date


SCHEMA_VERSION = 3


def needs_migration(t: dict) -> bool:
    return (t.get("meta") or {}).get("schema_version", 0) < SCHEMA_VERSION


def migrate_in_place(t: dict) -> dict:
    if not needs_migration(t):
        return t

    meta = t.setdefault("meta", {})
    old_version = meta.get("schema_version", 0)

    jobs = t.get("jobs", [])
    for j in jobs:
        if "archived" not in j:
            j["archived"] = False

    meta["schema_version"] = SCHEMA_VERSION
    changelog = meta.setdefault("changelog", [])
    changelog.append({
        "date": date.today().isoformat(),
        "event": f"schema_migration: v{old_version} → v{SCHEMA_VERSION} (added archived field)",
        "roles": len(jobs),
    })
    return t
