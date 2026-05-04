# bootstrap.ps1 — One-shot setup for Saber's Job Search System (Windows PowerShell).
# Usage:
#   cd C:\Users\ayatollS\Downloads\deep-research-report
#   .\bootstrap.ps1
#
# Optional flags:
#   .\bootstrap.ps1 -SetApiKey                # prompt for ANTHROPIC_API_KEY and persist it
#   .\bootstrap.ps1 -SkipInstall              # skip pip install
#   .\bootstrap.ps1 -SkipVerify               # skip verify.py at the end

param(
    [switch]$SetApiKey,
    [switch]$SkipInstall,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot
Set-Location $ROOT

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Saber's Job Search System — Bootstrap" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Python version check
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
$pyVersion = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Python is not on PATH. Install Python 3.9+ from python.org and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "  $pyVersion"
$pyMinor = & python -c "import sys; print(sys.version_info.minor)"
if ([int]$pyMinor -lt 9) {
    Write-Host "  WARNING: Python 3.9+ recommended. You have $pyVersion." -ForegroundColor Yellow
}

# 2. pip install
if (-not $SkipInstall) {
    Write-Host ""
    Write-Host "[2/5] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
    & python -m pip install --upgrade pip --quiet
    & python -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: pip install failed." -ForegroundColor Red
        exit 2
    }
    Write-Host "  Dependencies installed."
} else {
    Write-Host ""
    Write-Host "[2/5] Skipping pip install (--SkipInstall)" -ForegroundColor Yellow
}

# 3. API key
Write-Host ""
Write-Host "[3/5] ANTHROPIC_API_KEY..." -ForegroundColor Yellow
if ($SetApiKey) {
    $key = Read-Host "  Paste your ANTHROPIC_API_KEY (input hidden)" -AsSecureString
    $plainKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))
    [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $plainKey, "User")
    $env:ANTHROPIC_API_KEY = $plainKey
    Write-Host "  ANTHROPIC_API_KEY saved to User env (new shells will inherit)."
} else {
    if ($env:ANTHROPIC_API_KEY) {
        Write-Host "  Already set in current shell (length $($env:ANTHROPIC_API_KEY.Length))."
    } elseif ([Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")) {
        Write-Host "  Already set in User env (re-open PowerShell to load it into current shell)."
    } else {
        Write-Host "  NOT SET. Without this, fit_scorer.py and jd_tailor.py (non-dry-run) will fail."
        Write-Host "  Fix: re-run with -SetApiKey, or manually:"
        Write-Host '    [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY","sk-ant-...","User")' -ForegroundColor Gray
    }
}

# 4. Directory scaffolding
Write-Host ""
Write-Host "[4/5] Directory scaffolding..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "automation\outputs" | Out-Null
New-Item -ItemType Directory -Force -Path "automation\outputs\jd_cache" | Out-Null
New-Item -ItemType Directory -Force -Path "automation\outputs\fit_cache" | Out-Null
Write-Host "  automation\outputs\, jd_cache\, fit_cache\ ready."

# 5. Verify
if (-not $SkipVerify) {
    Write-Host ""
    Write-Host "[5/5] Running verify.py ..." -ForegroundColor Yellow
    & python verify.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  verify.py reported issues. See output above." -ForegroundColor Yellow
        exit 3
    }
} else {
    Write-Host ""
    Write-Host "[5/5] Skipping verify.py (--SkipVerify)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  BOOTSTRAP COMPLETE" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open dashboard:   streamlit run ui\app.py"
Write-Host "  2. Run a weekly scan: python automation\jd_scraper.py --expansion"
Write-Host "  3. Score:            python automation\fit_scorer.py --scan scan_YYYYMMDD.json"
Write-Host "  4. Promote:          python automation\auto_promote.py --commit --min-score 7 --expire-stale"
Write-Host "  5. Weekly report:    python automation\weekly_report.py"
Write-Host ""
