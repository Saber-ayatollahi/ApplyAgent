"""Pure tracker mutations composed under safe_json.mutate_json. No I/O."""
from __future__ import annotations

from datetime import datetime, timezone


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"Rejected", "Withdrawn", "Offer", "Hired", "Expired"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_job(t: dict, job_id: str) -> dict | None:
    for j in t.get("jobs", []):
        if j.get("id") == job_id:
            return j
    return None


def is_active(job: dict) -> bool:
    # archived missing → False so un-migrated rows still count as active
    return not job.get("archived", False) and job.get("status") not in TERMINAL_STATUSES


def apply_followup_gate(job: dict) -> bool:
    return bool(job.get("archived", False)) or job.get("status") in TERMINAL_STATUSES


def archive(t: dict, job_id: str, reason: str = "manual") -> dict:
    job = find_job(t, job_id)
    if job is None:
        raise KeyError(job_id)
    job["archived"] = True
    job["archived_at"] = _now_iso()
    job["archive_reason"] = reason
    return t


def archive_many(t: dict, job_ids, reason: str = "manual") -> dict:
    """Archive every id in `job_ids` in one pass so a bulk-clear is a single
    atomic write (vs N mutate_json calls, each taking the file lock). Unknown
    ids are skipped silently — the caller derives ids from the same tracker,
    so a missing id just means it was already gone. Idempotent: re-archiving
    an already-archived row only refreshes its timestamp/reason."""
    wanted = set(job_ids)
    for j in t.get("jobs", []):
        if j.get("id") in wanted:
            j["archived"] = True
            j["archived_at"] = _now_iso()
            j["archive_reason"] = reason
    return t


def restore(t: dict, job_id: str) -> dict:
    job = find_job(t, job_id)
    if job is None:
        raise KeyError(job_id)
    job["archived"] = False
    job.pop("archived_at", None)
    job.pop("archive_reason", None)
    return t


def set_status(t: dict, job_id: str, status: str) -> dict:
    job = find_job(t, job_id)
    if job is None:
        raise KeyError(job_id)
    enum = (t.get("meta") or {}).get("status_enum")
    if enum and status not in enum:
        raise ValueError(f"unknown status: {status!r}")
    job["status"] = status
    return t


def set_archive_reason(t: dict, job_id: str, reason: str) -> dict:
    job = find_job(t, job_id)
    if job is None:
        raise KeyError(job_id)
    if not job.get("archived", False):
        raise ValueError(f"job {job_id!r} is not archived")
    job["archive_reason"] = reason
    return t
