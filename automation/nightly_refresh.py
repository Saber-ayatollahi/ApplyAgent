"""
nightly_refresh.py - Python replacement for nightly_refresh.ps1

Runs the three-stage nightly pipeline and streams all output to stdout,
which scan_runner captures to its log file. Works correctly with
DETACHED_PROCESS + stdout redirect (unlike PowerShell).

Stages:
  1. jd_scraper.py --expansion --gmail
  2. scan_delta.py
  3. morning_brief.py --top 5 --auto-add 3 --auto-tailor

Output strategy:
  Each subprocess is run with stdout=PIPE + stderr=STDOUT so we own the read
  loop and can flush every line to our own stdout explicitly. This avoids the
  fd-sharing / TextIOWrapper-position issues that silently swallow subprocess
  output when stdout is a redirected file (as it is under scan_runner).
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Grab the raw stdout binary stream so we can write bytes directly,
# bypassing any TextIOWrapper buffering inside nightly_refresh itself.
_OUTBUF = getattr(sys.stdout, "buffer", sys.stdout)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    _OUTBUF.write(line.encode("utf-8", errors="replace"))
    _OUTBUF.flush()


def run_stage(label, cmd):
    """
    Run cmd as a subprocess, streaming every line of its combined stdout+stderr
    back through our own stdout in real time.

    Uses PIPE (not stdout=sys.stdout) so we own the read loop and can flush
    explicitly after every line.  On Windows, CREATE_NEW_PROCESS_GROUP isolates
    the child from Ctrl+C / CTRL_C_EVENT signals that could kill it mid-run.
    """
    log(f">>> {label}: {' '.join(str(a) for a in cmd)}")

    kwargs = dict(
        cwd=str(ROOT),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # merge child stderr into the pipe
        stdin=subprocess.DEVNULL,
    )
    if sys.platform == "win32":
        # New process group => child is immune to CTRL_C_EVENT from any console.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, **kwargs)

    # Stream every line to our stdout as it arrives.
    try:
        for raw_line in iter(proc.stdout.readline, b""):
            _OUTBUF.write(raw_line)
            _OUTBUF.flush()
    finally:
        proc.stdout.close()

    rc = proc.wait()
    return rc


def rotate_url_history_if_weekly():
    """
    Rotate url_history.json if it is ≥7 days old.

    url_history.json is the dedup database that prevents jd_scraper from
    re-surfacing jobs it already scraped.  After ~7 days the seen-set is
    stale: old roles may have been filled, new postings may match the same
    URLs.  Rotating it lets those roles resurface in the next scrape cycle
    without losing any data — the old file is renamed with a date stamp.

    Called at the top of main() so the fresh database is in place before
    Stage 1 (jd_scraper) runs.
    """
    url_hist = ROOT / "automation" / "outputs" / "url_history.json"
    if not url_hist.exists():
        log("url_history.json not found — will be created fresh by jd_scraper.")
        return

    age_days = (datetime.now().timestamp() - url_hist.stat().st_mtime) / 86400
    if age_days >= 7:
        stamp = datetime.now().strftime("%Y%m%d")
        archive = url_hist.with_name(f"url_history_{stamp}.json")
        # Safety: don't clobber an existing archive from the same day
        if archive.exists():
            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive = url_hist.with_name(f"url_history_{suffix}.json")
        url_hist.rename(archive)
        log(
            f"✅ Weekly rotation: url_history.json → {archive.name} "
            f"({age_days:.1f}d old). Fresh dedup database created for this week."
        )
    else:
        log(
            f"url_history.json is {age_days:.1f}d old — no rotation needed "
            f"(rotates automatically when ≥7 days old)."
        )


def main():
    log("=== nightly_refresh starting ===")
    log(f"repo: {ROOT}")

    # Pick Python (prefer the venv if present)
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    python = str(venv_python) if venv_python.exists() else sys.executable
    log(f"python: {python}")

    # ------------------------------------------------------------------
    # Weekly URL-history rotation (must happen before Stage 1 scrape)
    # ------------------------------------------------------------------
    log("[0/3] Checking url_history age for weekly rotation...")
    rotate_url_history_if_weekly()

    # Hydrate API key from ~/.applyagent/config.json if not already in env
    if not os.environ.get("ANTHROPIC_API_KEY"):
        cfg_path = Path.home() / ".applyagent" / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                if cfg.get("anthropic_api_key"):
                    os.environ["ANTHROPIC_API_KEY"] = cfg["anthropic_api_key"]
                    log("API key loaded from ~/.applyagent/config.json")
            except Exception as e:
                log(f"Warning: could not read config.json: {e}")

    # ------------------------------------------------------------------
    # Stage 1 - scrape
    # ------------------------------------------------------------------
    log("[1/3] Scraping (web + Gmail alerts)...")
    rc = run_stage("jd_scraper", [python, "automation/jd_scraper.py", "--expansion", "--gmail"])
    if rc != 0:
        log(f"Scraper finished with exit code {rc}.")
        if rc not in (0, 2):   # 2 = paused (partial run), still usable
            log("Scraper returned a non-zero code. Checking if we have usable output...")

    # ------------------------------------------------------------------
    # Stage 2 - delta
    # ------------------------------------------------------------------
    log("[2/3] Computing delta...")
    run_stage("scan_delta", [python, "automation/scan_delta.py"])

    # Guard: verify today's delta file exists and is non-trivial
    today = datetime.now().strftime("%Y%m%d")
    delta_path = ROOT / "automation" / "outputs" / f"delta_{today}.json"
    if not delta_path.exists():
        log(f"ABORT: {delta_path} not found - skipping morning_brief.")
        sys.exit(1)
    delta_size = delta_path.stat().st_size
    if delta_size < 100:
        log(f"ABORT: delta file is only {delta_size} bytes - too small, skipping.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Stage 3 - morning brief
    # ------------------------------------------------------------------
    log("[3/3] Generating morning brief...")
    rc = run_stage(
        "morning_brief",
        [python, "automation/morning_brief.py", "--top", "5", "--auto-add", "3", "--auto-tailor"],
    )
    if rc != 0:
        log(f"morning_brief finished with exit code {rc}.")

    log("=== nightly_refresh finished ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("nightly_refresh interrupted by KeyboardInterrupt - exiting cleanly.")
        sys.exit(0)
