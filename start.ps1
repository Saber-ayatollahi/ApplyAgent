# ===========================================================================
# start.ps1 — Launch Saber's Job Search Dashboard (Streamlit)
# ===========================================================================
# - Keeps this terminal open so you can watch backend logs.
# - Mirrors every line of Streamlit / backend output to logs/app_<stamp>.log.
# - Opens http://localhost:8501 in your default browser once the server is up.
# - On Ctrl+C or when Streamlit exits, pauses at the bottom so you can read
#   the last ~20 lines instead of the window vanishing.
#
# Usage:
#   .\start.ps1                   # default (port 8501; auto-finds free port if busy)
#   .\start.ps1 -Port 8600        # explicit port
#   .\start.ps1 -KillExisting     # stop whatever currently holds the port
#   .\start.ps1 -NoBrowser        # don't auto-open browser
# ===========================================================================

param(
    [int]$Port = 8501,
    [switch]$NoBrowser,
    [switch]$KillExisting   # stop any process holding the requested port first
)

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

# ---------- Helpers ----------
function Test-PortFree([int]$p) {
    # True if no LISTEN on $p. Get-NetTCPConnection is the clean API on Win10+.
    $inUse = $null -ne (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
    return (-not $inUse)
}

function Get-PortOwners([int]$p) {
    # Return [pid, name] tuples for whatever holds the port.
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    $conns | ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Pid  = $_.OwningProcess
            Name = if ($proc) { $proc.ProcessName } else { 'unknown' }
        }
    } | Sort-Object Pid -Unique
}

function Find-FreePort([int]$start, [int]$maxTries = 10) {
    for ($i = 0; $i -lt $maxTries; $i++) {
        $try = $start + $i
        if (Test-PortFree $try) { return $try }
    }
    return $null
}

# ---------- Port selection ----------
# If the requested port is taken, optionally kill the holder (--KillExisting)
# or scan forward for the next free port. Prevents the opaque "Port XXXX is
# already in use" crash that kicks the user back to a closed terminal.
if (-not (Test-PortFree $Port)) {
    $owners = Get-PortOwners $Port
    $ownerTxt = if ($owners) {
        ($owners | ForEach-Object { "$($_.Name)(pid $($_.Pid))" }) -join ', '
    } else { 'unknown' }
    Write-Host ("[port] {0} is already in use by: {1}" -f $Port, $ownerTxt) -ForegroundColor Yellow

    if ($KillExisting -and $owners) {
        foreach ($o in $owners) {
            try {
                Stop-Process -Id $o.Pid -Force -ErrorAction Stop
                Write-Host ("[port] killed pid {0} ({1})" -f $o.Pid, $o.Name) -ForegroundColor Green
            } catch {
                Write-Host ("[port] could not kill pid {0}: {1}" -f $o.Pid, $_.Exception.Message) -ForegroundColor Red
            }
        }
        Start-Sleep -Seconds 1
    }

    if (-not (Test-PortFree $Port)) {
        $alt = Find-FreePort ($Port + 1) 20
        if ($null -eq $alt) {
            Write-Host ("[port] No free port found in range {0}..{1}. Use -KillExisting or -Port <n>." -f ($Port + 1), ($Port + 20)) -ForegroundColor Red
            Write-Host 'Press any key to exit...'
            try { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') } catch {}
            exit 1
        }
        Write-Host ("[port] switching to free port {0}" -f $alt) -ForegroundColor Cyan
        $Port = $alt
    }
}

# ---------- Log file ----------
$logsDir = Join-Path $PSScriptRoot 'logs'
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $logsDir "app_$stamp.log"

# Pointer file the UI reads to know which session log to tail.
$pointerFile = Join-Path $logsDir 'current.log'
$logFile | Out-File -FilePath $pointerFile -Encoding utf8 -Force

# ---------- Header ----------
Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  ApplyAgent — Job Search Dashboard' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ("  URL:     http://localhost:{0}" -f $Port)
Write-Host ("  Log:     {0}" -f $logFile)
Write-Host '  Stop:    Ctrl+C (this window will pause, not close)'
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# ---------- Preflight: is the `streamlit` Python module importable? ----------
# We DON'T rely on `streamlit` being on PATH. pip installs on Windows often
# drop the launcher into %APPDATA%\Python\Python3xx\Scripts\ which is not on
# PATH by default. Instead we invoke `python -m streamlit run ...` below, and
# only need the module to be importable here.
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host '[preflight] `python` not on PATH. Install Python 3.10+ and retry.' -ForegroundColor Red
    Write-Host 'Press any key to exit...'
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    exit 1
}

& python -c "import streamlit" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[preflight] streamlit not importable. Running pip install...' -ForegroundColor Yellow
    python -m pip install -r requirements.txt -r ui/requirements.txt
    & python -c "import streamlit" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[preflight] streamlit still not importable after pip install.' -ForegroundColor Red
        Write-Host '           Try: python -m pip install --upgrade streamlit' -ForegroundColor Red
        Write-Host 'Press any key to exit...'
        $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
        exit 1
    }
}
# Report version for the log
$stVersion = & python -c "import streamlit; print(streamlit.__version__)" 2>$null
Write-Host ('[preflight] streamlit {0} OK' -f $stVersion) -ForegroundColor Green

# ---------- Open browser after boot (async) ----------
if (-not $NoBrowser) {
    Start-Job -Name 'openBrowser' -ScriptBlock {
        param($p)
        Start-Sleep -Seconds 4
        Start-Process ("http://localhost:{0}" -f $p)
    } -ArgumentList $Port | Out-Null
}

# ---------- Run Streamlit, tee stdout/stderr to both console and logfile ----------
# `streamlit run` prints to stderr a lot; merge 2>&1 so everything ends up in
# the Tee-Object pipeline. `-ForegroundColor` does not survive a pipe, so we
# accept the streamlit output is plain text in this terminal. The UI log
# viewer reads the same file regardless.
try {
    & python -m streamlit run ui/app.py --server.port $Port --server.headless true 2>&1 |
        Tee-Object -FilePath $logFile -Append
}
catch {
    Write-Host ''
    Write-Host ('[start.ps1] Streamlit crashed: {0}' -f $_.Exception.Message) -ForegroundColor Red
}
finally {
    # Clean up browser-opener job if it's still pending
    Get-Job -Name 'openBrowser' -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Yellow
    Write-Host '  Streamlit exited.' -ForegroundColor Yellow
    Write-Host ('  Full log: {0}' -f $logFile)
    Write-Host '============================================================' -ForegroundColor Yellow
    Write-Host 'Press any key to close this window...'
    try {
        $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    } catch {
        # If we're in a non-interactive host (ISE, piped invocation), just fall through.
        Start-Sleep -Seconds 5
    }
}
