# Expose Device Bridge (:9814) to phone via Tailscale (or LAN).
# Forwards WSL mailbus :9814 to the Windows Tailscale interface (or 0.0.0.0).
# Firewall Tailscale-In is already allowed by Tailscale itself.
#
# Usage (admin required, UAC prompt):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\expose-device-bridge.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\expose-device-bridge.ps1 -Lan
param(
    [int]$Port = 9814,
    [switch]$Lan
)

$ErrorActionPreference = "Continue"

# Admin-elevated child output does not return to the caller; write a log file instead.
$log = Join-Path $PSScriptRoot "expose-result.txt"
function Log($msg) {
    Add-Content -Path $log -Value $msg
}
Remove-Item $log -ErrorAction SilentlyContinue

# Guard against empty port (encoding/param quirks).
if (-not $Port) {
    $Port = 9814
}

function Get-WslIp {
    $raw = (& wsl -d Ubuntu hostname -I 2>$null)
    if (-not $raw) { return $null }
    return ($raw.ToString().Trim() -split "\s+")[0]
}

function Get-TailscaleIp {
    $raw = (& tailscale ip -4 2>$null)
    if (-not $raw) { return $null }
    return $raw.ToString().Trim()
}

$wslIp = Get-WslIp
if (-not $wslIp) {
    Log "[expose-device-bridge] ERROR: WSL not running"
    exit 1
}

if ($Lan) {
    $listen = "0.0.0.0"
} else {
    $listen = Get-TailscaleIp
    if (-not $listen) {
        Log "[expose-device-bridge] ERROR: tailscale not running; use -Lan for LAN instead"
        exit 1
    }
}

# Idempotent: delete then re-add.
netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=$listen 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$Port listenaddress=$listen connectaddress=$wslIp connectport=$Port 2>&1 | Out-Null
$addRc = $LASTEXITCODE
Log ("[expose-device-bridge] portproxy " + $listen + ":" + $Port + " -> " + $wslIp + ":" + $Port + " (rc=" + $addRc + ")")

# Self-test.
$probeUrl = "http://" + $listen + ":" + $Port + "/api/health"
try {
    $resp = Invoke-WebRequest -Uri $probeUrl -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop
    Log ("[expose-device-bridge] OK " + $probeUrl + " -> " + $resp.StatusCode)
} catch {
    Log ("[expose-device-bridge] WARN: probe " + $probeUrl + " failed: " + $_.Exception.Message)
}

exit 0
