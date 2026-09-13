# Auto-rebuild portproxy rules after WSL/PC restart (NAT mode).
# - Ensures WSL is started, waits for its IP
# - Rebuilds localhost rules + Tailscale device-bridge rule (idempotent)
# - Logs to rebuild-result.txt
# Pure ASCII to avoid PS5.1 encoding issues.
$ErrorActionPreference = "Continue"
$log = Join-Path $PSScriptRoot "rebuild-result.txt"
function Log($msg) { Add-Content -Path $log -Value $msg }
Remove-Item $log -ErrorAction SilentlyContinue

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

# 1) Ensure WSL is up (boots the distro if not running)
$null = (& wsl -d Ubuntu -e echo "wake" 2>$null)
Log "[rebuild] wsl wake triggered"

# 2) Wait for WSL IP (up to 60s, Docker stack may need time too)
$wslIp = $null
for ($i = 0; $i -lt 30; $i++) {
    $wslIp = Get-WslIp
    if ($wslIp) { break }
    Start-Sleep -Seconds 2
}
if (-not $wslIp) { Log "[rebuild] ERROR: WSL IP not ready after 60s"; exit 1 }
Log ("[rebuild] WSL IP = " + $wslIp)

# 3) localhost -> WSL (browser access from Windows)
$localPorts = @(9812, 3111, 9120, 9121, 9122, 9123, 9124, 9125, 18789, 18790)
foreach ($p in $localPorts) {
    netsh interface portproxy delete v4tov4 listenport=$p listenaddress=127.0.0.1 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenport=$p listenaddress=127.0.0.1 connectaddress=$wslIp connectport=$p 2>&1 | Out-Null
}
Log ("[rebuild] localhost rules rebuilt -> " + $wslIp)

# 4) Tailscale :9814 -> WSL (phone access via tailnet)
$tsIp = Get-TailscaleIp
if ($tsIp) {
    netsh interface portproxy delete v4tov4 listenport=9814 listenaddress=$tsIp 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenport=9814 listenaddress=$tsIp connectaddress=$wslIp connectport=9814 2>&1 | Out-Null
    Log ("[rebuild] " + $tsIp + ":9814 -> " + $wslIp + ":9814 (Tailscale)")
} else {
    Log "[rebuild] WARN: tailscale not running, skip :9814 rule"
}

# 5) summary
$count = (netsh interface portproxy show v4tov4 2>$null | Select-String -Pattern "\d+\.\d+\.\d+\.\d+\s+\d+\s+\d+\.\d+\.\d+\.\d+\s+\d+").Count
Log ("[rebuild] done, " + $count + " rules active")

exit 0
