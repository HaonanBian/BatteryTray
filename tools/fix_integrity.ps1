<#
.SYNOPSIS
    Diagnose and repair the Low mandatory-integrity label that the DSH/Codex
    workspace sandbox leaves on a workspace tree.

.DESCRIPTION
    Symptom: launching a PyInstaller onefile program from inside the workspace
    pops up "Error: Could not create temporary directory!" (a .NET program may
    instead fail with 0xE0434352).

    Cause: the workspace sandbox marked the whole workspace subtree with a Low
    integrity label (Mandatory Label\Low Mandatory Level). Windows forces every
    process to run at the integrity of its image file, so the exe runs at Low;
    a Low process cannot write to Medium locations such as %TEMP%, and the
    PyInstaller bootloader cannot create its _MEIxxxxxx directory.

    This script restores the workspace to Medium, removes the sandbox's
    "Everyone: DENY" entry and (optionally) the S-1-4-* capability SID grants.
    Executables that cannot be re-labelled without Administrator rights are
    rebuilt in place (delete + write the same bytes), which makes them inherit
    the parent folder's Medium label again.

.PARAMETER Path
    Workspace root. Defaults to the parent folder of this script.

.PARAMETER Apply
    Actually repair. Without it the script only reports what it finds.

.PARAMETER RemoveSandboxAces
    Also remove S-1-4-* (capability) SID entries from the workspace ACL.

.EXAMPLE
    .\fix_integrity.ps1
    Report only.

.EXAMPLE
    .\fix_integrity.ps1 -Apply
    Repair the workspace.

.NOTES
    Double-click fix_integrity.cmd next to this file to run it elevated.
#>
[CmdletBinding()]
param(
    [string] $Path = '',
    [switch] $Apply,
    [switch] $RemoveSandboxAces
)

$ErrorActionPreference = 'Continue'

if (-not $Path) { $Path = Split-Path -Parent $PSScriptRoot }
if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "Workspace not found: $Path" -ForegroundColor Red
    exit 1
}
$Path = (Resolve-Path -LiteralPath $Path).Path

# Folders that never need relabelling (huge, and no exe we start from there).
$skipDirs = @('.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache')

function Get-IntegrityLabel {
    param([string] $LiteralPath)
    $out = & icacls $LiteralPath 2>&1 | Out-String
    # Line looks like: "  Mandatory Label\Low Mandatory Level:(I)(NW)" - keep just "Low".
    if ($out -match 'Mandatory Label\\(.+?)\s+Mandatory Level:') { return $Matches[1].Trim() }
    return 'Medium'   # no explicit label == default (Medium)
}

function Get-LowExecutables {
    param([string] $Root)
    $result = @()
    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        try { $items = Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop } catch { continue }
        foreach ($item in $items) {
            if ($item.PSIsContainer) {
                if ($skipDirs -notcontains $item.Name) { $stack.Push($item.FullName) }
            } elseif ($item.Extension -ieq '.exe') {
                if ((Get-IntegrityLabel $item.FullName) -eq 'Low') { $result += $item.FullName }
            }
        }
    }
    return $result
}

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal] $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Host ''
Write-Host "BatteryTray workspace integrity check" -ForegroundColor Cyan
Write-Host "  workspace : $Path"
Write-Host "  admin     : $(Test-Administrator)"
Write-Host ""

$rootLabel = Get-IntegrityLabel $Path
$lowExes = @(Get-LowExecutables $Path)
$hasDenyEveryone = ((& icacls $Path 2>&1 | Out-String) -match '(?:Everyone|S-1-1-0):.*\(DENY\)')

Write-Host "Root label        : $rootLabel"
Write-Host "Low-labelled exes : $($lowExes.Count)"
foreach ($e in $lowExes) { Write-Host "    $e" -ForegroundColor Yellow }
Write-Host "Everyone DENY     : $hasDenyEveryone"
Write-Host ""

$needsFix = ($rootLabel -eq 'Low') -or ($lowExes.Count -gt 0) -or $hasDenyEveryone

if (-not $needsFix) {
    Write-Host "Nothing to fix - the workspace is healthy." -ForegroundColor Green
    Write-Host "If an exe still reports 'Could not create temporary directory!'," -ForegroundColor DarkGray
    Write-Host "check that the exe really lives under this workspace." -ForegroundColor DarkGray
    exit 0
}

if (-not $Apply) {
    Write-Host "Diagnosis only. To repair, run either of these:" -ForegroundColor Cyan
    Write-Host "    .\fix_integrity.ps1 -Apply" -ForegroundColor White
    Write-Host "    fix_integrity.cmd          (double-click, asks for Administrator)" -ForegroundColor White
    exit 2
}

Write-Host "Repairing..." -ForegroundColor Cyan

# 1) Remove the sandbox's deny entry for Everyone.
if ($hasDenyEveryone) {
    & icacls $Path /remove:d Everyone /T /C | Out-Null
    Write-Host "  [1/4] removed Everyone:DENY"
} else {
    Write-Host "  [1/4] no Everyone:DENY entry"
}

# 2) Re-label the root and its tree to Medium. /T walks every object and can
#    take a while on large trees; files we cannot relabel keep Low for now and
#    are handled by step 3.
& icacls $Path /setintegritylevel '(OI)(CI)M' | Out-Null
Write-Host "  [2/4] walking the tree with icacls /T (this can take a minute)..."
& icacls $Path /setintegritylevel '(OI)(CI)M' /T /C | Out-Null
if ((Get-IntegrityLabel $Path) -eq 'Low') {
    Write-Host "  [2/4] root is still Low - Administrator rights are required to relabel it" -ForegroundColor Yellow
} else {
    Write-Host "  [2/4] root is Medium now (files without WRITE_OWNER keep Low for now)"
}

# 3) Rebuild exes that are still Low: delete + rewrite the same bytes, so the
#    new file inherits Medium from its parent folder. Needs no Administrator.
$stillLow = @(Get-LowExecutables $Path)
$rebuilt = 0
foreach ($exe in $stillLow) {
    $name = [System.IO.Path]::GetFileName($exe)
    if (Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($exe)) -ErrorAction SilentlyContinue) {
        Write-Host "    skip (running): $name" -ForegroundColor Yellow
        continue
    }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($exe)
        Remove-Item -LiteralPath $exe -Force -ErrorAction Stop
        [System.IO.File]::WriteAllBytes($exe, $bytes)
        if ((Get-IntegrityLabel $exe) -eq 'Low') {
            Write-Host "    still Low after rebuild: $name" -ForegroundColor Yellow
        } else {
            Write-Host "    rebuilt: $name" -ForegroundColor Green
            $rebuilt++
        }
    } catch {
        Write-Host "    failed: $name - $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
Write-Host "  [3/4] rebuilt $rebuilt exe(s)"

# 4) Optional: drop capability SID grants left by the sandbox.
if ($RemoveSandboxAces) {
    $acl = & icacls $Path 2>&1 | Out-String
    $caps = [regex]::Matches($acl, '(S-1-4-\d+(?:-\d+)*)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
    foreach ($cap in $caps) {
        & icacls $Path /remove $cap /T /C | Out-Null
        Write-Host "    removed capability SID $cap"
    }
    Write-Host "  [4/4] capability SIDs handled: $($caps.Count)"
} else {
    Write-Host "  [4/4] capability SIDs left alone (use -RemoveSandboxAces to drop them)"
}

Write-Host ""
$rootLabel = Get-IntegrityLabel $Path
$lowAfter = @(Get-LowExecutables $Path)
Write-Host "Result: root=$rootLabel, low-labelled exes=$($lowAfter.Count)" -ForegroundColor Cyan
foreach ($e in $lowAfter) { Write-Host "    still Low: $e" -ForegroundColor Yellow }
if ($lowAfter.Count -eq 0) {
    Write-Host "Done. Launch release\BatteryTray-1.3.1.exe again to verify." -ForegroundColor Green
    exit 0
}
Write-Host "Some exes are still Low; run this script as Administrator to finish." -ForegroundColor Yellow
Write-Host ""
Write-Host "Manual fallback in an Administrator terminal:" -ForegroundColor Cyan
Write-Host ('    icacls "{0}" /setintegritylevel "(OI)(CI)M" /T /C' -f $Path)
Write-Host ('    icacls "{0}" /remove:d Everyone /T /C' -f $Path)
exit 3
