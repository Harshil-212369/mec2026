<#
.SYNOPSIS
  MEC 2026: install or upgrade only the tools that check-tools.ps1 marks FAIL,
  using winget. Shows the plan and asks before changing anything.

.USAGE
  Double-click scripts\install-tools.cmd
  or: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-tools.ps1 [-WithClaudeCode] [-WithPostmanCli] [-Yes]

  -WithClaudeCode  also install Claude Code (J and H; A does not need it)
  -WithPostmanCli  also install the Postman CLI (optional)
  -Yes             skip the confirmation prompt

  Windows may show admin (UAC) prompts for some installers: approve them.
  Open a NEW terminal afterwards so PATH changes take effect, then re-run check-tools.
  ASCII only.
#>
param(
    [switch]$WithClaudeCode,
    [switch]$WithPostmanCli,
    [switch]$Yes
)

$ErrorActionPreference = 'Continue'
$check = Join-Path $PSScriptRoot 'check-tools.ps1'

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host '[FAIL] winget not found. Install "App Installer" from the Microsoft Store, then re-run.' -ForegroundColor Red
    exit 1
}

$results = & $check -PassThru
if ($null -eq $results) { Write-Host '[FAIL] check-tools.ps1 returned nothing (is toolchain.json present?)' -ForegroundColor Red; exit 1 }

$plan = @($results | Where-Object { $_.Status -ne 'PASS' -and $_.Id })
$extras = @()
if ($WithClaudeCode -and ($results | Where-Object { $_.Tool -eq 'Claude Code' -and $_.Status -ne 'PASS' })) { $extras += 'Claude Code (official installer)' }
if ($WithPostmanCli -and ($results | Where-Object { $_.Tool -eq 'Postman CLI' -and $_.Status -ne 'PASS' })) { $extras += 'Postman CLI (official installer)' }

if (-not $plan.Count -and -not $extras.Count) {
    Write-Host '[PASS] Nothing to install. Everything required matches the team toolchain.' -ForegroundColor Cyan
    exit 0
}

Write-Host ''
Write-Host 'Planned changes:' -ForegroundColor Cyan
foreach ($p in $plan) { Write-Host ("  winget {0,-8} {1,-28} ({2}: {3} -> {4})" -f $p.Action, $p.Id, $p.Tool, $p.Mine, $p.Ref) }
foreach ($e in $extras) { Write-Host "  $e" }
Write-Host ''
if (-not $Yes) {
    $answer = Read-Host 'Proceed? (y/n)'
    if ($answer -notmatch '^(y|yes)$') { Write-Host 'Cancelled. Nothing changed.'; exit 0 }
}

$failed = @()
foreach ($p in $plan) {
    Write-Host "[RUN ] winget $($p.Action) --id $($p.Id)" -ForegroundColor Cyan
    winget $p.Action --id $p.Id -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        # winget returns non-zero for "no applicable upgrade" too; the re-check below is the real verdict.
        Write-Host "[WARN] winget exit $LASTEXITCODE for $($p.Id)" -ForegroundColor Yellow
        $failed += $p.Id
    }
}

if ($extras -contains 'Claude Code (official installer)') {
    Write-Host '[RUN ] Claude Code installer (https://claude.ai/install.ps1)' -ForegroundColor Cyan
    try { Invoke-RestMethod 'https://claude.ai/install.ps1' | Invoke-Expression }
    catch { Write-Host "[WARN] Claude Code install failed: $($_.Exception.Message)" -ForegroundColor Yellow; $failed += 'Claude Code' }
}
if ($extras -contains 'Postman CLI (official installer)') {
    Write-Host '[RUN ] Postman CLI installer (https://dl-cli.pstmn.io/install/win64.ps1)' -ForegroundColor Cyan
    try { Invoke-RestMethod 'https://dl-cli.pstmn.io/install/win64.ps1' | Invoke-Expression }
    catch { Write-Host "[WARN] Postman CLI install failed: $($_.Exception.Message)" -ForegroundColor Yellow; $failed += 'Postman CLI' }
}

Write-Host ''
if ($failed.Count) { Write-Host "[WARN] Check these: $($failed -join ', ')" -ForegroundColor Yellow }
Write-Host 'Done. Close this window, open a NEW one, and run scripts\check-tools.cmd again.' -ForegroundColor Cyan
Write-Host 'That second check is the real result (PATH only refreshes in new windows).'
