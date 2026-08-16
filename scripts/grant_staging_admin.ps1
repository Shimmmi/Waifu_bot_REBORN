# Print ADMIN_IDS line for a Steam dev player (staging).
# Usage: .\scripts\grant_staging_admin.ps1 [-SteamTicketDev "7656119..."]
param(
  [string]$SteamTicketDev = "",
  [string]$EnvFile = ".env.staging"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $SteamTicketDev) {
  $cfgPath = Join-Path $RepoRoot "desktop_client\config.local.json"
  if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    $SteamTicketDev = [string]$cfg.steamTicketDev
  }
}

if (-not $SteamTicketDev) {
  Write-Error "Set steamTicketDev in desktop_client/config.local.json or pass -SteamTicketDev"
}

Write-Host "Looking up player_id for external_id (Steam dev): $SteamTicketDev"

$compose = @("compose", "-f", "docker-compose.staging.yml", "exec", "-T", "db")
$sql = @"
SELECT p.id, p.external_id
FROM players p
WHERE p.external_id = 'steam:$SteamTicketDev'
   OR p.external_id = '$SteamTicketDev'
LIMIT 1;
"@

$raw = & docker @compose psql -U waifu -d waifu -t -A -c $sql 2>$null
if (-not $raw) {
  Write-Host ""
  Write-Host "Player not found. Log in once with npm run dev, then re-run this script."
  exit 1
}

$parts = $raw.Trim() -split '\|'
$playerId = $parts[0]
Write-Host ""
Write-Host "Found player_id: $playerId"
Write-Host ""
Write-Host "Add to $EnvFile (ADMIN_IDS accepts negative Steam player ids):"
Write-Host "ADMIN_IDS=$playerId"
Write-Host ""
Write-Host "Then: docker compose -f docker-compose.staging.yml up -d --build api"
