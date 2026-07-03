#Requires -Version 5.1
<#
.SYNOPSIS
  Verifies the local Docker staging API is up before npm run dev.

.DESCRIPTION
  Checks Docker engine, waits for the waifu_staging_api container to report
  "healthy" (see the healthcheck in docker-compose.staging.yml), then
  double-checks the HTTP endpoints that Electron loads on startup (/health,
  /webapp/overlay.html, nav webp) with a few retries — Docker Desktop for
  Windows can transiently reset connections for a couple of seconds right
  after a container (re)starts even once it's marked healthy.

  Run after:

    docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build

  Usage (works from any directory, e.g. also from desktop_client/):

    powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1

  Exit code: 0 if all checks pass, 1 otherwise.
#>

$ErrorActionPreference = "Continue"

# Resolve repo root from this script's own location, not the caller's CWD —
# so `docker compose -f docker-compose.staging.yml --env-file .env.staging`
# (relative paths) resolves correctly even if run from desktop_client/ or
# elsewhere (see docs troubleshooting: "couldn't find env file" when run
# from the wrong directory).
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {

$BackendUrl = if ($env:WAIFU_BACKEND_URL) { $env:WAIFU_BACKEND_URL.TrimEnd("/") } else { "http://127.0.0.1:18000" }
$ComposeFile = "docker-compose.staging.yml"
$EnvFile = ".env.staging"
$ContainerName = "waifu_staging_api"
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
Write-Host "Repo root: $RepoRoot" -ForegroundColor Gray
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
    Write-Check "Compose file" $false "$ComposeFile not found under $RepoRoot"
    exit 1
}
Write-Check "Compose file" $true $ComposeFile

# Wait for the api container to report "healthy" (docker-compose.staging.yml
# healthcheck: curl -f http://localhost:8000/health). This absorbs both the
# few seconds Uvicorn needs to import + start 14 background task loops, and
# is a much more reliable signal than "container state is Up" (which is true
# the instant the process forks, long before it accepts connections).
$maxWaitSeconds = 60
$pollIntervalSeconds = 2
$elapsed = 0
$health = "unknown"
Write-Host ""
Write-Host "Waiting for $ContainerName to become healthy (up to ${maxWaitSeconds}s)..." -ForegroundColor Cyan
while ($elapsed -lt $maxWaitSeconds) {
    $health = (docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>&1 | Out-String).Trim()
    if ($health -eq "healthy") { break }
    if ($health -match "No such object") {
        Write-Check "$ContainerName container" $false "not found - run: docker compose -f $ComposeFile --env-file $EnvFile up -d --build"
        Write-Host ""
        Write-Host "If api keeps exiting, inspect logs:" -ForegroundColor Yellow
        Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile logs api --tail 80" -ForegroundColor Gray
        exit 1
    }
    Start-Sleep -Seconds $pollIntervalSeconds
    $elapsed += $pollIntervalSeconds
}

if ($health -eq "healthy") {
    Write-Check "$ContainerName container" $true "healthy (waited ${elapsed}s)"
} else {
    Write-Check "$ContainerName container" $false "status=$health after ${maxWaitSeconds}s - container is up but never became healthy"
    Write-Host ""
    Write-Host "Inspect logs:" -ForegroundColor Yellow
    Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile logs api --tail 80" -ForegroundColor Gray
    $failed++
}

function Test-HttpWithRetry {
    param(
        [string]$Path,
        [string]$Label,
        [string]$BodyMustContain = "",
        # Generous budget: the container healthcheck above only proves Uvicorn
        # is listening *inside* the container (curl against its own
        # localhost) - on Docker Desktop for Windows the separate host-side
        # port-forward (vpnkit/WinNAT actually making 127.0.0.1:18000
        # reachable) can lag behind that by well more than a few seconds
        # after a rebuild, even once `docker compose ps` says "healthy".
        [int]$Retries = 20,
        [int]$DelaySeconds = 2
    )
    $url = "$BackendUrl$Path"
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
            $ok = ($resp.StatusCode -eq 200)
            if ($ok -and $BodyMustContain -and ($resp.Content -notmatch [regex]::Escape($BodyMustContain))) {
                $ok = $false
                $detail = "200 but body missing '$BodyMustContain' (old image? run up -d --build)"
            } else {
                $detail = "HTTP $($resp.StatusCode)"
            }
            if ($ok) {
                Write-Check $Label $true $detail
                return $true
            }
            # 200-but-wrong-body won't fix itself on retry; fail fast.
            Write-Check $Label $false $detail
            return $false
        } catch {
            $msg = $_.Exception.Message
            # Locale-independent: Russian Windows reports "Соединение было неожиданно
            # закрыто" — the old English-only regex never matched, so we failed on
            # the first attempt instead of retrying for ~40s.
            $isTransient = $false
            $ex = $_.Exception
            while ($ex) {
                if ($ex -is [System.Net.WebException]) {
                    $status = $ex.Status
                    if ($status -in @(
                        [System.Net.WebExceptionStatus]::ConnectionClosed,
                        [System.Net.WebExceptionStatus]::ConnectFailure,
                        [System.Net.WebExceptionStatus]::ReceiveFailure,
                        [System.Net.WebExceptionStatus]::SendFailure,
                        [System.Net.WebExceptionStatus]::Timeout,
                        [System.Net.WebExceptionStatus]::PipelineFailure,
                        [System.Net.WebExceptionStatus]::KeepAliveFailure,
                        [System.Net.WebExceptionStatus]::NameResolutionFailure
                    )) {
                        $isTransient = $true
                        break
                    }
                }
                $ex = $ex.InnerException
            }
            if (-not $isTransient) {
                $isTransient = $msg -match "closed|reset|empty|refused|connect|timeout|закрыт|сброс|отказ|соедин|недоступ|неожидан"
            }
            if ($isTransient -and $i -lt $Retries) {
                if ($i -eq 1 -or $i % 5 -eq 0) {
                    Write-Host "  retry $Label ($i/$Retries)..." -ForegroundColor DarkYellow
                }
                Start-Sleep -Seconds $DelaySeconds
                continue
            }
            $detail = if ($isTransient) {
                "no response after $Retries attempts ($($Retries * $DelaySeconds)s) - backend down, or (on Windows) the Docker Desktop host port-forward is stuck; try 'wsl --shutdown' then restart Docker Desktop"
            } else {
                $msg
            }
            Write-Check $Label $false $detail
            return $false
        }
    }
    return $false
}

function Test-ApiInsideContainer {
    param([string]$Label = "GET /health (inside container via docker exec)")
    try {
        $out = docker exec $ContainerName curl -sf http://localhost:8000/health 2>&1 | Out-String
        $out = $out.Trim()
        if ($LASTEXITCODE -eq 0 -and $out -match "ok|healthy|status") {
            Write-Check $Label $true "curl OK — Uvicorn listens inside container"
            return $true
        }
        if ($LASTEXITCODE -eq 0 -and $out.Length -gt 0) {
            Write-Check $Label $true "HTTP body received inside container"
            return $true
        }
    } catch {
        # fall through
    }
    Write-Check $Label $false "curl inside container failed (api may be crashed)"
    return $false
}

if (-not (Test-HttpWithRetry -Path "/health" -Label "GET /health")) { $failed++ }
if (-not (Test-HttpWithRetry -Path "/webapp/overlay.html" -Label "GET /webapp/overlay.html" -BodyMustContain "ov-menu-btn")) { $failed++ }
if (-not (Test-HttpWithRetry -Path "/static/game/ui/nav/profile.webp" -Label "GET nav profile.webp")) { $failed++ }

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

if ($failed -gt 0 -and $health -eq "healthy") {
    Write-Host "Diagnosis (container reports healthy but host HTTP failed):" -ForegroundColor Cyan
    $null = Test-ApiInsideContainer
    Write-Host ""
    Write-Host "If 'inside container' is [OK]: Uvicorn is fine — Docker Desktop host port-forward" -ForegroundColor Yellow
    Write-Host "to 127.0.0.1:18000 is stuck (common on Windows after rebuild). Telegram webhook" -ForegroundColor Yellow
    Write-Host "errors in 'docker logs api' do NOT block /health or the Steam desktop client." -ForegroundColor Gray
    Write-Host ""
}

Write-Host "Fix host port-forward (most common on Windows):" -ForegroundColor Yellow
Write-Host "  wsl --shutdown" -ForegroundColor Gray
Write-Host "  # wait ~10s, restart Docker Desktop, then:" -ForegroundColor Gray
Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile up -d --wait" -ForegroundColor Gray
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/check_staging_backend.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "Otherwise (run from repo root, not desktop_client/):" -ForegroundColor Yellow
Write-Host "  git pull origin feature/steam-client" -ForegroundColor Gray
Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile up -d --build" -ForegroundColor Gray
Write-Host "  docker compose -f $ComposeFile --env-file $EnvFile exec api alembic upgrade head" -ForegroundColor Gray
exit 1

} finally {
    Pop-Location
}
