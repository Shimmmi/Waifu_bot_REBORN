#Requires -Version 5.1
<#
.SYNOPSIS
  Checks Windows dev-machine prerequisites for the Waifu Bot desktop client.

.DESCRIPTION
  Verifies Git, Node.js (>=20), npm, Python 3.11+, Docker, Docker Compose,
  WSL2, and (best-effort) MSVC Build Tools for node-gyp / uiohook-napi.

  Run from repo root after installing components from docs/STEAM_CLIENT_DEV_SETUP.md:

    powershell -ExecutionPolicy Bypass -File scripts/check_windows_dev_env.ps1

  Exit code: 0 if all required checks pass, 1 otherwise.
#>

$ErrorActionPreference = "Continue"

function Write-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail = ""
    )
    $mark = if ($Ok) { "[OK]" } else { "[FAIL]" }
    $color = if ($Ok) { "Green" } else { "Red" }
    $line = "$mark $Name"
    if ($Detail) { $line += " - $Detail" }
    Write-Host $line -ForegroundColor $color
}

function Test-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$cmd
}

function Get-SemverMajor {
    param([string]$VersionText)
    if ($VersionText -match '(\d+)\.') {
        return [int]$Matches[1]
    }
    return $null
}

$failed = 0

Write-Host ""
Write-Host "Waifu Bot - Windows dev environment check" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Git
if (Test-Command git) {
    $v = (git --version 2>&1) -join " "
    Write-Check "Git" $true $v
} else {
    Write-Check "Git" $false "not found - install from https://git-scm.com/download/win"
    $failed++
}

# Node.js >= 20
if (Test-Command node) {
    $nodeVer = (node --version 2>&1) -join "" -replace '^v', ''
    $major = Get-SemverMajor $nodeVer
    $ok = ($null -ne $major) -and ($major -ge 20)
    Write-Check "Node.js (>= 20)" $ok "v$nodeVer"
    if (-not $ok) { $failed++ }
} else {
    Write-Check "Node.js (>= 20)" $false "not found - install LTS from https://nodejs.org/"
    $failed++
}

# npm
if (Test-Command npm) {
    $v = (npm --version 2>&1) -join ""
    Write-Check "npm" $true $v
} else {
    Write-Check "npm" $false "not found (ships with Node.js installer)"
    $failed++
}

# Python >= 3.11 (node-gyp uses `python` on Windows)
$pythonCmd = $null
foreach ($candidate in @("python", "py")) {
    if (Test-Command $candidate) {
        $pythonCmd = $candidate
        break
    }
}
if ($pythonCmd) {
    $pyOut = & $pythonCmd --version 2>&1 | Out-String
    $pyVer = if ($pyOut -match '(\d+\.\d+\.\d+)') { $Matches[1] } else { $pyOut.Trim() }
    if ($pyVer -match '^(\d+)\.(\d+)') {
        $pyMajorNum = [int]$Matches[1]
        $pyMinorNum = [int]$Matches[2]
        $ok = ($pyMajorNum -gt 3) -or ($pyMajorNum -eq 3 -and $pyMinorNum -ge 11)
    } else {
        $ok = $false
    }
    Write-Check "Python (>= 3.11, for node-gyp)" $ok $pyOut.Trim()
    if (-not $ok) { $failed++ }
} else {
    Write-Check "Python (>= 3.11, for node-gyp)" $false "not found - enable Add to PATH at install"
    $failed++
}

# Docker
if (Test-Command docker) {
    $v = (docker --version 2>&1) -join " "
    Write-Check "Docker" $true $v
} else {
    Write-Check "Docker" $false "not found - install Docker Desktop"
    $failed++
}

# Docker Compose v2
$composeOk = $false
$composeDetail = ""
if (Test-Command docker) {
    try {
        $composeOut = docker compose version 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0 -and $composeOut) {
            $composeOk = $true
            $composeDetail = $composeOut.Trim()
        }
    } catch {}
}
if (-not $composeOk) {
    Write-Check "Docker Compose v2" $false "run 'docker compose version' failed"
    $failed++
} else {
    Write-Check "Docker Compose v2" $true $composeDetail
}

# WSL2
$wslOk = $false
$wslDetail = ""
if (Test-Command wsl) {
    try {
        $wslOut = wsl --status 2>&1 | Out-String
        if ($wslOut -match "Default Version:\s*2") {
            $wslOk = $true
            $wslDetail = "Default Version: 2"
        } else {
            $wslDetail = "WSL installed but default version may not be 2 - run: wsl --set-default-version 2"
        }
    } catch {
        $wslDetail = $_.Exception.Message
    }
} else {
    $wslDetail = "wsl.exe not found - run 'wsl --install' as Administrator"
}
Write-Check "WSL2" $wslOk $wslDetail
if (-not $wslOk) { $failed++ }

# MSVC Build Tools (best-effort - node-gyp needs these for uiohook-napi)
$msvcOk = $false
$msvcDetail = ""
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vsWhere) {
    $installs = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    if ($installs) {
        $msvcOk = $true
        $msvcDetail = "VC++ tools found via vswhere"
    } else {
        $msvcDetail = "VS Build Tools present but 'Desktop development with C++' workload may be missing"
    }
} else {
    $msvcDetail = "vswhere not found - install VS Build Tools 2022 with C++ workload"
}
Write-Check "MSVC Build Tools (node-gyp)" $msvcOk $msvcDetail
if (-not $msvcOk) { $failed++ }

# Docker engine running (optional but useful)
if (Test-Command docker) {
    try {
        docker info 2>&1 | Out-Null
        $engineOk = ($LASTEXITCODE -eq 0)
        if ($engineOk) {
            Write-Check "Docker engine running" $true ""
        } else {
            Write-Check "Docker engine running" $false "start Docker Desktop and wait for Engine running"
            $failed++
        }
    } catch {
        Write-Check "Docker engine running" $false $_.Exception.Message
        $failed++
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "All checks passed. Next: docs/STEAM_CLIENT_DEV_SETUP.md - Steps 1-6." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failed check(s) failed. See docs/STEAM_CLIENT_DEV_SETUP.md - Step 0 (Windows)." -ForegroundColor Yellow
    exit 1
}
