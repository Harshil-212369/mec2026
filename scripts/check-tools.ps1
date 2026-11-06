<#
.SYNOPSIS
  MEC 2026: compare this laptop's Windows toolchain with H's reference versions
  in toolchain.json. Read-only: it changes nothing.

.USAGE
  Teammates: double-click scripts\check-tools.cmd, then paste the summary in the group chat.
  PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-tools.ps1

  H only, once: record your own versions as the team reference
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-tools.ps1 -WriteReference

  Used by install-tools.ps1: -PassThru returns the result objects instead of printing.

  Match policy (why):
    Git        >= reference      (newer is fine; older misses security fixes)
    Node       same major        (26.x; a different major can change npm/lockfile behaviour)
    Python     3.14 via py       (same minor = same wheels and language features)
    VS Code    installed         (version does not affect the build)
    Browser    Chrome or Firefox (organizers' email)
    Postman    desktop app       (organizers' email); Postman CLI optional
    Claude     Claude Code       (H and J only; A uses GPT in VS Code)

  ASCII only: Windows PowerShell 5.1 misreads non-ASCII in BOM-less scripts.
#>
param(
    [switch]$WriteReference,
    [switch]$PassThru
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$refPath = Join-Path $root 'toolchain.json'

# ---------- helpers ----------------------------------------------------------

function Invoke-Quiet {
    <# First output line of an exe (stdout+stderr), or $null if it cannot run. #>
    param([string]$Exe, [string[]]$ArgList)
    try {
        $out = & $Exe @ArgList 2>&1 | Select-Object -First 1
        if ($null -eq $out) { return $null }
        return "$out".Trim()
    } catch { return $null }
}

function Get-SemVer {
    <# First x.y.z in a string as [version], or $null. #>
    param([string]$Text)
    if ($Text -match '(\d+)\.(\d+)\.(\d+)') { return [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])" }
    return $null
}

function Find-Exe {
    <# First executable on PATH for $Name, else the first existing fallback path, else $null. #>
    param([string]$Name, [string[]]$Fallbacks = @())
    $cmd = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    foreach ($f in $Fallbacks) { if ($f -and (Test-Path $f)) { return $f } }
    return $null
}

function Find-Installed {
    <# DisplayName + version of the first uninstall entry matching $Pattern, or $null. #>
    param([string]$Pattern)
    $keys = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    foreach ($k in $keys) {
        $hit = Get-ItemProperty $k -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like $Pattern } | Select-Object -First 1
        if ($hit) { return ("{0} {1}" -f $hit.DisplayName, $hit.DisplayVersion).Trim() }
    }
    return $null
}

function Find-Browser {
    <# Names of installed browsers among Chrome/Firefox, via the App Paths registry. #>
    $found = @()
    foreach ($b in @(@{ Name = 'Chrome'; Exe = 'chrome.exe' }, @{ Name = 'Firefox'; Exe = 'firefox.exe' })) {
        foreach ($hive in 'HKCU:', 'HKLM:') {
            $p = Get-ItemProperty "$hive\Software\Microsoft\Windows\CurrentVersion\App Paths\$($b.Exe)" -ErrorAction SilentlyContinue
            if ($p -and $p.'(default)' -and (Test-Path ($p.'(default)'.Trim('"')))) { $found += $b.Name; break }
        }
    }
    return $found
}

function Get-PyVersions {
    <# Minor versions the py launcher knows, e.g. @('3.14','3.12'). Empty if py is missing. #>
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { return @() }
    $txt = (& py -0p 2>&1 | Out-String)
    return @([regex]::Matches($txt, '-V:(3\.\d+)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
}

# ---------- collect this machine's versions ----------------------------------

$actual = [ordered]@{}
$gitLine  = Invoke-Quiet 'git' @('--version');  $actual.git  = Get-SemVer $gitLine
$nodeLine = Invoke-Quiet 'node' @('-v');        $actual.node = Get-SemVer $nodeLine
$actual.nodeLts = if ($actual.node) { Invoke-Quiet 'node' @('-p', 'process.release.lts || "none"') } else { $null }
$npmLine  = Invoke-Quiet 'npm.cmd' @('-v');     $actual.npm  = Get-SemVer $npmLine
$actual.python = Get-PyVersions
$codeLine = Invoke-Quiet 'code' @('--version'); $actual.vscode = Get-SemVer $codeLine
$actual.browsers = Find-Browser
$actual.postmanApp = Find-Installed 'Postman*'
if (-not $actual.postmanApp -and (Test-Path "$env:LOCALAPPDATA\Postman\Postman.exe")) { $actual.postmanApp = 'Postman (per-user)' }
$pmCli = Find-Exe 'postman' @("$env:LOCALAPPDATA\Microsoft\WindowsApps\postman.exe")
$actual.postmanCli = if ($pmCli) { Get-SemVer (Invoke-Quiet $pmCli @('-v')) } else { $null }
$claudeExe = Find-Exe 'claude' @("$env:USERPROFILE\.local\bin\claude.exe")
$actual.claude = if ($claudeExe) { Get-SemVer (Invoke-Quiet $claudeExe @('--version')) } else { $null }

# ---------- H: write the reference -------------------------------------------

if ($WriteReference) {
    $missing = @()
    if (-not $actual.git)  { $missing += 'git' }
    if (-not $actual.node) { $missing += 'node' }
    if ($actual.python -notcontains '3.14') { $missing += 'python 3.14' }
    if ($missing.Count) {
        Write-Host "[FAIL] Cannot write reference; missing on this machine: $($missing -join ', ')" -ForegroundColor Red
        exit 1
    }
    $ref = [ordered]@{
        recordedBy  = $env:USERNAME
        recordedAt  = (Get-Date -Format 'yyyy-MM-dd HH:mm')
        git         = "$($actual.git)"
        nodeMajor   = $actual.node.Major
        node        = "$($actual.node)"
        npm         = "$($actual.npm)"
        python      = '3.14'
        vscode      = "$($actual.vscode)"
        postmanCli  = "$($actual.postmanCli)"
        claudeCode  = "$($actual.claude)"
    }
    $ref | ConvertTo-Json | Set-Content -Path $refPath -Encoding ASCII
    Write-Host "[PASS] Reference written to $refPath" -ForegroundColor Cyan
    Get-Content $refPath
    exit 0
}

# ---------- compare against the reference ------------------------------------

if (-not (Test-Path $refPath)) {
    Write-Host "[FAIL] $refPath not found. Run 'git pull' (H commits it)." -ForegroundColor Red
    exit 2
}
$ref = Get-Content $refPath -Raw | ConvertFrom-Json
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    <# One row: Tool, Status (PASS/WARN/FAIL), Mine, Reference, Fix text, and the winget action for install-tools.ps1. #>
    param([string]$Tool, [string]$Status, [string]$Mine, [string]$Ref, [string]$Fix, [string]$Action = '', [string]$Id = '')
    $results.Add([pscustomobject]@{ Tool = $Tool; Status = $Status; Mine = $Mine; Ref = $Ref; Fix = $Fix; Action = $Action; Id = $Id })
}

function Show-Value { param($v) if ($null -eq $v -or "$v" -eq '') { 'missing' } else { "$v" } }

# Git: >= reference
$refGit = [version]$ref.git
if (-not $actual.git)              { Add-Result 'Git' 'FAIL' 'missing' $ref.git 'Install Git' 'install' 'Git.Git' }
elseif ($actual.git -lt $refGit)   { Add-Result 'Git' 'FAIL' "$($actual.git)" ">= $($ref.git)" 'Upgrade Git' 'upgrade' 'Git.Git' }
else                               { Add-Result 'Git' 'PASS' "$($actual.git)" ">= $($ref.git)" '' }

# Node: same major
$refMajor = [int]$ref.nodeMajor
if (-not $actual.node)                  { Add-Result 'Node.js' 'FAIL' 'missing' "$refMajor.x LTS" 'Install Node LTS' 'install' 'OpenJS.NodeJS.LTS' }
elseif ($actual.node.Major -lt $refMajor) { Add-Result 'Node.js' 'FAIL' "$($actual.node)" "$refMajor.x LTS" 'Upgrade Node LTS' 'upgrade' 'OpenJS.NodeJS.LTS' }
elseif ($actual.node.Major -gt $refMajor) { Add-Result 'Node.js' 'WARN' "$($actual.node)" "$refMajor.x LTS" "Newer major than the team; tell H before installing packages" }
elseif ($actual.nodeLts -eq 'none')     { Add-Result 'Node.js' 'WARN' "$($actual.node) (not LTS)" "$refMajor.x LTS" 'Use the LTS build' 'install' 'OpenJS.NodeJS.LTS' }
else                                    { Add-Result 'Node.js' 'PASS' "$($actual.node) ($($actual.nodeLts))" "$refMajor.x LTS" '' }

# npm: informational (ships with Node)
Add-Result 'npm' ($(if ($actual.npm) { 'PASS' } else { 'FAIL' })) (Show-Value $actual.npm) (Show-Value $ref.npm) ($(if ($actual.npm) { '' } else { 'Comes with Node; reinstall Node' }))

# Python: 3.14 via the py launcher
$pyList = if ($actual.python.Count) { $actual.python -join ', ' } else { 'missing' }
if ($actual.python -contains $ref.python) { Add-Result 'Python' 'PASS' $pyList $ref.python '' }
else { Add-Result 'Python' 'FAIL' $pyList $ref.python 'Install Python 3.14 (side by side with others)' 'install' 'Python.Python.3.14' }

# VS Code: installed
if ($actual.vscode) { Add-Result 'VS Code' 'PASS' "$($actual.vscode)" 'installed' '' }
else { Add-Result 'VS Code' 'FAIL' 'missing' 'installed' 'Install VS Code' 'install' 'Microsoft.VisualStudioCode' }

# Browser
if ($actual.browsers.Count) { Add-Result 'Browser' 'PASS' ($actual.browsers -join ', ') 'Chrome or Firefox' '' }
else { Add-Result 'Browser' 'FAIL' 'missing' 'Chrome or Firefox' 'Install Chrome' 'install' 'Google.Chrome' }

# Postman desktop (required) and CLI (optional)
if ($actual.postmanApp) { Add-Result 'Postman app' 'PASS' $actual.postmanApp 'installed' '' }
else { Add-Result 'Postman app' 'FAIL' 'missing' 'installed' 'Install Postman' 'install' 'Postman.Postman' }
if ($actual.postmanCli) { Add-Result 'Postman CLI' 'PASS' "$($actual.postmanCli)" 'optional' '' }
else { Add-Result 'Postman CLI' 'WARN' 'missing' 'optional' 'Optional: install-tools.cmd -WithPostmanCli' }

# Claude Code: H and J
if ($actual.claude) { Add-Result 'Claude Code' 'PASS' "$($actual.claude)" 'H and J' '' }
else { Add-Result 'Claude Code' 'WARN' 'missing' 'H and J' 'J: install-tools.cmd -WithClaudeCode (A: ignore)' }

# Store stub for python (common Windows trap; not fixable by winget)
$pyBare = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pyBare -and $pyBare.Source -like '*\Microsoft\WindowsApps\*') {
    Add-Result 'python alias' 'WARN' 'Store stub' 'off' 'Settings > Apps > Advanced app settings > App execution aliases: turn off python.exe and python3.exe'
}

if ($PassThru) { return $results }

# ---------- print ------------------------------------------------------------

Write-Host ''
Write-Host '=== MEC 2026 tool check ===' -ForegroundColor Cyan
Write-Host ("Machine: {0} | Reference recorded by {1} on {2}" -f $env:USERNAME, $ref.recordedBy, $ref.recordedAt)
Write-Host ''
Write-Host ("{0,-13} {1,-6} {2,-28} {3,-18} {4}" -f 'Tool', 'Status', 'This laptop', 'Team reference', 'Fix')
Write-Host ('-' * 100)
foreach ($r in $results) {
    switch ($r.Status) { 'PASS' { $c = 'Cyan' } 'WARN' { $c = 'Yellow' } 'FAIL' { $c = 'Red' } default { $c = 'Gray' } }
    Write-Host ("{0,-13} " -f $r.Tool) -NoNewline
    Write-Host ("{0,-6} " -f $r.Status) -ForegroundColor $c -NoNewline
    Write-Host ("{0,-28} {1,-18} {2}" -f $r.Mine, $r.Ref, $r.Fix)
}
$fails = @($results | Where-Object Status -eq 'FAIL').Count
$warns = @($results | Where-Object Status -eq 'WARN').Count
Write-Host ''
if ($fails) {
    Write-Host "$fails FAIL, $warns WARN. Next: double-click scripts\install-tools.cmd, then run this check again in a NEW window." -ForegroundColor Red
    exit 1
}
Write-Host "0 FAIL, $warns WARN. Matches the team toolchain." -ForegroundColor Cyan
exit 0
