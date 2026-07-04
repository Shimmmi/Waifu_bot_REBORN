#Requires -Version 5.1
<#
.SYNOPSIS
  Build webapp, rebuild staging Docker api, run health checks (no Electron).

.DESCRIPTION
  Run from repository root after git pull on feature/steam-client.
  Steps: build_webapp.sh, build_steam_pages.sh, docker compose --build,
  alembic upgrade, check_staging_backend.ps1, verify_steam_webapp_deploy.sh.

  Does NOT start npm run dev — run that manually in desktop_client/.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/deploy_steam_client.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $RepoRoot "docker-compose.staging.yml"))) {
    Write-Error "Run from repository root (docker-compose.staging.yml not found)."
    exit 1
}

Set-Location $RepoRoot
Write-Host "=== deploy_steam_client (root: $RepoRoot) ===" -ForegroundColor Cyan

function Invoke-BashScript {
    param([string]$ScriptPath)
    if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
        Write-Error "bash not found. Install Git for Windows or use WSL."
        exit 1
    }
    Write-Host ">> bash $ScriptPath" -ForegroundColor Yellow
    & bash $ScriptPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Invoke-BashScript "./scripts/build_webapp.sh"
Invoke-BashScript "./scripts/build_steam_pages.sh"

Write-Host ">> docker compose up -d --build --wait" -ForegroundColor Yellow
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build --wait
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ">> alembic upgrade head" -ForegroundColor Yellow
docker compose -f docker-compose.staging.yml --env-file .env.staging exec api alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ">> check_staging_backend.ps1" -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/check_staging_backend.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Invoke-BashScript "./scripts/verify_steam_webapp_deploy.sh"

Write-Host ""
Write-Host "[OK] Deploy complete. Start Electron:" -ForegroundColor Green
Write-Host "  cd desktop_client" -ForegroundColor Green
Write-Host "  npm run dev" -ForegroundColor Green
