# nightly_refresh.ps1 — End-to-end nightly job-hunt refresh.
#
# What it does (in order):
#   1. Activates the project venv (if present) or falls back to system Python.
#   2. Runs jd_scraper.py --expansion → writes scan_<today>.json.
#   3. Runs scan_delta.py → writes delta_<today>.json.
#   4. Runs morning_brief.py --top 5 → writes brief_<today>.md.
#
# Output lands in automation/outputs/ and the Streamlit UI reads it on next load.
#
# Prereqs:
#   $env:ANTHROPIC_API_KEY must be set in the user's environment, OR the key must
#   already be saved in ~/.applyagent/config.json (the UI writes it there).
#
# Manual run:
#   powershell -ExecutionPolicy Bypass -File automation\nightly_refresh.ps1
#
# Install as a scheduled task — see install_schedule.ps1 (same folder).

$ErrorActionPreference = "Continue"  # best-effort: don't bail on the first warning
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
Set-Location $repoRoot

# Pick Python
$python = if (Test-Path "$repoRoot\.venv\Scripts\python.exe") {
    "$repoRoot\.venv\Scripts\python.exe"
} else {
    "python"
}

# Hydrate API key from ~/.applyagent/config.json if not already in env
if (-not $env:ANTHROPIC_API_KEY) {
    $cfgPath = Join-Path $HOME ".applyagent\config.json"
    if (Test-Path $cfgPath) {
        try {
            $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
            if ($cfg.anthropic_api_key) {
                $env:ANTHROPIC_API_KEY = $cfg.anthropic_api_key
            }
        } catch { }
    }
}

$logDir = Join-Path $repoRoot "automation\outputs\runs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "nightly_refresh_$stamp.log"

function Log($msg) {
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] $msg" -f (Get-Date)
    Add-Content -Path $log -Value $line
    Write-Host $line
}

Log "=== nightly_refresh starting ==="
Log "repo: $repoRoot"
Log "python: $python"

# Stage 1 — scrape
Log "[1/3] Scraping..."
& $python "automation\jd_scraper.py" --expansion 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Log "Scraper failed with exit code $LASTEXITCODE — aborting."
    exit 1
}

# Stage 2 — delta
Log "[2/3] Computing delta..."
& $python "automation\scan_delta.py" 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Log "scan_delta failed with exit code $LASTEXITCODE — continuing to brief anyway."
}

# Stage 3 — brief (auto-add top 3 + auto-tailor drafts)
Log "[3/3] Generating morning brief (auto-add + auto-tailor top 3)..."
& $python "automation\morning_brief.py" --top 5 --auto-add 3 --auto-tailor 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Log "morning_brief failed with exit code $LASTEXITCODE"
    exit 1
}

Log "=== nightly_refresh finished ==="
exit 0
