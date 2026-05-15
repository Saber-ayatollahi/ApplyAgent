# Install ApplyAgent git hooks into .git/hooks/ (Windows PowerShell).
# Re-running is safe: existing hook is overwritten with the canonical copy.

$ErrorActionPreference = "Stop"

try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    Write-Error "[install-hooks] ERROR: not inside a git repository."
    exit 1
}

if ([string]::IsNullOrEmpty($repoRoot)) {
    Write-Error "[install-hooks] ERROR: not inside a git repository."
    exit 1
}

# git rev-parse returns forward-slash paths on Windows; normalize for PS.
$repoRoot = $repoRoot -replace '/', '\'

$src = Join-Path $repoRoot "scripts\pre-commit"
$dst = Join-Path $repoRoot ".git\hooks\pre-commit"

if (-not (Test-Path $src)) {
    Write-Error "[install-hooks] ERROR: source hook not found: $src"
    exit 1
}

$hooksDir = Join-Path $repoRoot ".git\hooks"
if (-not (Test-Path $hooksDir)) {
    New-Item -ItemType Directory -Path $hooksDir -Force | Out-Null
}

# Plain copy (symlinks are flaky on Windows). Overwrite if present.
Copy-Item -Path $src -Destination $dst -Force

# chmod equivalent is a no-op on NTFS; git for Windows reads bit 0644 anyway.

Write-Host "[install-hooks] installed: $dst"
Write-Host "[install-hooks] source:    $src"
Write-Host "[install-hooks] bypass with: git commit --no-verify"
