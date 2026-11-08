# MEC 2026 - one-step setup for judges and teammates (Windows PowerShell 5.1+)
# Creates .venv in the repo root and installs the pinned packages from requirements.txt.
# Needs: Python 3.11 or newer, and internet access the first time (pip download).
# No database server is needed: the engine runs in memory; optional logging uses
# Python's built-in sqlite3 module, which ships with Python.
# AI-assisted: Claude Code (Anthropic, Claude Opus), reviewed/modified by Harshil.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Get-PythonCmd {
    # Prefer the py launcher with 3.14 (team version), then any Python 3, then 'python'.
    $candidates = @(@('py', '-3.14'), @('py', '-3'), @('python'))
    foreach ($c in $candidates) {
        $exe = $c[0]
        $pyArgs = @()
        if ($c.Count -gt 1) { $pyArgs = $c[1..($c.Count - 1)] }
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $ver = & $exe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
        $parts = $ver.Trim().Split('.')
        if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) {
            return [pscustomobject]@{ Exe = $exe; Args = $pyArgs }
        }
        Write-Host "[WARN] $exe $pyArgs is Python $ver (need 3.11+), trying next"
    }
    return $null
}

$py = Get-PythonCmd
if (-not $py) {
    Write-Host "[FAIL] Python 3.11+ not found. Install it from https://www.python.org/downloads/ then re-run."
    exit 1
}
$pyExe = $py.Exe
$pyArgs = @($py.Args)
Write-Host "[PASS] Using: $pyExe $pyArgs"

$venvPy = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating .venv ..."
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] venv creation failed"; exit 1 }
}

& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $repo 'requirements.txt') --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] pip install failed (check internet access)"; exit 1 }

& $venvPy -c "import fastapi, uvicorn, sqlite3; print('[PASS] imports ok, sqlite', sqlite3.sqlite_version)"
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] import check failed"; exit 1 }
Write-Host "[PASS] Setup done. Run commands are in README.md."
