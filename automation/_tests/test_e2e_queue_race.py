"""Regression test: queue_pending_archive vs drain race condition.

Previously queue_pending_archive() lacked an exclusive lock while
drain_pending_archives() did read-then-truncate, causing silent data
loss under contention. Now fixed — this test passes deterministically.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_queue_drain_race_no_data_loss(tmp_path: Path):
    """Spawn a queuer and a draining loop in parallel. After both finish,
    the count of (drained + remaining) entries must equal the count queued.
    """
    queue_code = '''
import sys
from pathlib import Path
ROOT = Path(sys.argv[1]); TMP = Path(sys.argv[2]); n = int(sys.argv[3])
sys.path.insert(0, str(ROOT))
import automation.suppressions as supp
supp.PENDING_ARCHIVES_PATH = TMP / "pending.jsonl"
for i in range(n):
    supp.queue_pending_archive(f"job-{i}", f"r{i}")
print("done", flush=True)
'''
    drain_code = '''
import sys, time, json
from pathlib import Path
ROOT = Path(sys.argv[1]); TMP = Path(sys.argv[2])
sys.path.insert(0, str(ROOT))
import automation.suppressions as supp
supp.PENDING_ARCHIVES_PATH = TMP / "pending.jsonl"
total = 0
for _ in range(20):
    out = supp.drain_pending_archives()
    total += len(out)
    time.sleep(0.005)
print(json.dumps({"drained": total}), flush=True)
'''
    qf = tmp_path / "qw.py"
    df = tmp_path / "dw.py"
    qf.write_text(queue_code, encoding="utf-8")
    df.write_text(drain_code, encoding="utf-8")

    n_queue = 200
    qp = subprocess.Popen(
        [sys.executable, str(qf), str(ROOT), str(tmp_path), str(n_queue)],
        stdout=subprocess.PIPE, text=True,
    )
    dp = subprocess.Popen(
        [sys.executable, str(df), str(ROOT), str(tmp_path)],
        stdout=subprocess.PIPE, text=True,
    )
    qp.communicate()
    do, _ = dp.communicate()

    drained = json.loads(do.strip())["drained"]
    pending_path = tmp_path / "pending.jsonl"
    remaining_text = pending_path.read_text(encoding="utf-8") if pending_path.exists() else ""
    remaining = sum(1 for l in remaining_text.splitlines() if l.strip())
    assert drained + remaining == n_queue, (
        f"queue/drain race lost {n_queue - drained - remaining} entries: "
        f"drained={drained}, remaining={remaining}, expected={n_queue}"
    )
