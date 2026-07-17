# Verify local Windows machine can build the Waifu Activity debug APK.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fail = 0

function Ok($m) { Write-Host "[OK] $m" }
function Bad($m) { Write-Host "[FAIL] $m"; $script:Fail = 1 }
function Warn($m) { Write-Host "[WARN] $m" }

Write-Host "== Waifu Mobile Android env check (Windows) =="
Write-Host "mobile_client: $Root"

if (Get-Command node -ErrorAction SilentlyContinue) {
  $v = (node -v).TrimStart("v")
  $major = [int]($v.Split(".")[0])
  if ($major -ge 20) { Ok "Node $v" } else { Bad "Node $v (need >= 20)" }
} else { Bad "node not found" }

if (Get-Command java -ErrorAction SilentlyContinue) {
  $jl = & java -version 2>&1 | Select-Object -First 1
  Ok "Java: $jl"
} else { Bad "java not found (install JDK 17)" }

$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if ($sdk -and (Test-Path $sdk)) {
  Ok "ANDROID_HOME=$sdk"
  $adb = Join-Path $sdk "platform-tools\adb.exe"
  if ((Test-Path $adb) -or (Get-Command adb -ErrorAction SilentlyContinue)) { Ok "adb available" }
  else { Bad "adb not found" }
} else { Bad "ANDROID_HOME / ANDROID_SDK_ROOT not set" }

if (Test-Path (Join-Path $Root "android")) { Ok "mobile_client/android/ present" }
else { Warn "mobile_client/android/ missing — run: npm ci; npx cap add android" }

if (Test-Path (Join-Path $Root "node_modules\@capacitor\cli\package.json")) { Ok "node_modules installed" }
else { Warn "node_modules missing — run: npm ci" }

if ($Fail -ne 0) {
  Write-Host "Environment check FAILED."
  exit 1
}
Write-Host "Environment check PASSED."
exit 0
