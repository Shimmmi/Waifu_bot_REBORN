#Requires -Version 5.1
<#
.SYNOPSIS
  Verifies the local Docker staging API is up before npm run dev.

.DESCRIPTION
  Checks Docker engine, waifu_staging_api container, and HTTP endpoints that
  Electron loads on startup (/health, /webapp/overlay.html, nav webp).
  Run from repo root after:

    docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build

  Usage:

    powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1

  Exit code: 0 if all checks pass, 1 otherwise.
#>

$ErrorActionPreference = "Continue"

$BackendUrl = if ($env:WAIFU_BACKEND_URL) { $env:WAIFU_BACKEND_URL.TrimEnd("/") } else { "http://127.0.0.1:18000" }
$ComposeFile = "docker-compose.staging.yml"
$EnvFile = ".env.staging"
$failed = 0

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

Write-Host ""
Write-Host "Waifu Bot - staging backend check ($BackendUrl)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Docker engine
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) { throw "docker info exit $LASTEXITCODE" }
    Write-Check "Docker engine" $true "running"
} catch {
    Write-Check "Docker engine" $false "not running - start Docker Desktop and wait for Running"
    Write-Host ""
    Write-Host "Fix: open Docker Desktop, then re-run this script." -ForegroundColor Yellow
    exit 1
}

# Compose file
if (-not (Test-Path $ComposeFile)) {
    Write-Check "Compose file" $false "$ComposeFile not found (run from repo root)"
    exit 1
}
Write-Check "Compose file" $true $ComposeFile

# Container status
$psOut = docker compose -f $ComposeFile --env-file $EnvFile ps --format json 2>&1
$apiRunning = $false
if ($LASTEXITCODE -eq 0 -and $psOut) {
    foreach ($line in ($psOut -split "`n")) {
        if (-not $line.Trim()) { continue }
        try {
            $row = $line | ConvertFrom-Json
            if ($row.Service -eq "api" -and $row.State -match "running") {
                $apiRunning = $true
            }
        } catch {
            # older compose may not emit json per line; fall back to text
        }
    }
}
if (-not $apiRunning) {
    $textPs = docker compose -f $ComposeFile --env-file $EnvFile ps 2>&1 | Out-String
    if ($textPs -match "waifu_staging_api" -and $textPs -match "Up") {
        $apiRunning = $true
    }
}
if (-not $apiRunning) {
    Write-Check "waifu_staging_api container" $false "not Up - run: docker compose -f $ComposeFile --env-file $EnvFile up -d --build"
    Write-Host ""
    Write-Host "If api keeps exiting, inspect logs:" -ForegroundColor Yellow
    Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile logs api --tail 80" -ForegroundColor Gray
    $failed++
} else {
    Write-Check "waifu_staging_api container" $true "Up"
}

function Test-Http {
    param(
        [string]$Path,
        [string]$Label,
        [string]$BodyMustContain = ""
    )
    $url = "$BackendUrl$Path"
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
        $ok = ($resp.StatusCode -eq 200)
        if ($ok -and $BodyMustContain -and ($resp.Content -notmatch [regex]::Escape($BodyMustContain))) {
            $ok = $false
            $detail = "200 but body missing '$BodyMustContain' (old image? run up -d --build)"
        } else {
            $detail = "HTTP $($resp.StatusCode)"
        }
        Write-Check $Label $ok $detail
        if (-not $ok) { return $false }
        return $true
    } catch {
        $msg = $_.Exception.Message
        if ($msg -match "empty|refused|connect") {
            $detail = "no response - backend down or port 18000 not mapped (ERR_EMPTY_RESPONSE in Electron)"
        } else {
            $detail = $msg
        }
        Write-Check $Label $false $detail
        return $false
    }
}

if (-not (Test-Http -Path "/health" -Label "GET /health")) { $failed++ }
if (-not (Test-Http -Path "/webapp/overlay.html" -Label "GET /webapp/overlay.html" -BodyMustContain "ov-menu-btn")) { $failed++ }
if (-not (Test-Http -Path "/static/game/ui/nav/profile.webp" -Label "GET nav profile.webp")) { $failed++ }

Write-Host ""
if ($failed -eq 0) {
    Write-Host "Staging backend is ready. You can run: cd desktop_client; npm run dev" -ForegroundColor Green
    Write-Host ""
    Write-Host "config.local.json should contain only backendUrl + steamTicketDev (no overlay key)." -ForegroundColor Gray
    Write-Host "See desktop_client/config.example.json" -ForegroundColor Gray
    exit 0
}

Write-Host "$failed check(s) failed. Do NOT run npm run dev until /health returns 200." -ForegroundColor Red
Write-Host ""
Write-Host "Typical fix:" -ForegroundColor Yellow
Write-Host "  git pull origin feature/steam-client" -ForegroundColor Gray
Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile up -d --build" -ForegroundColor Gray
Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile exec api alembic upgrade head" -ForegroundColor Gray
exit 1
