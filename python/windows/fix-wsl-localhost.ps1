# Fix Windows localhost -> WSL Docker port forwarding (portproxy fallback when wslrelay is stale)
param(
    [switch]$ForceFix,
    [int[]]$Ports = @(9814, 3111, 9120, 9121, 9122, 9123, 9124, 9125, 9126, 9127, 9220, 9221, 9240, 9241, 9250, 9251, 9260, 9261, 18789, 18790)
)

function Test-HttpPort {
    param([int]$Port)
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Test-WslHttpPort {
    param([int]$Port, [string]$WslIp)
    try {
        $null = Invoke-WebRequest -Uri "http://${WslIp}:$Port/" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-WslIp {
    $raw = (& wsl -d Ubuntu hostname -I 2>$null)
    if (-not $raw) { return $null }
    return $raw.ToString().Trim().Split()[0]
}

function Get-PortProxyTarget {
    param([int]$Port)
    $line = netsh interface portproxy show v4tov4 | Select-String "127.0.0.1\s+$Port\s+"
    if (-not $line) { return $null }
    if ($line -match '127\.0\.0\.1\s+\d+\s+(\S+)\s+\d+') { return $Matches[1] }
    return $null
}

function Install-PortProxy {
    param([string]$WslIp, [int[]]$PortList)
    # Prefer soft refresh: only kill wslrelay when portproxy replace still fails.
    # Force-killing wslrelay mid-start drops all localhost tunnels ("启动到最后就断了").
    foreach ($p in $PortList) {
        netsh interface portproxy delete v4tov4 listenport=$p listenaddress=127.0.0.1 2>$null | Out-Null
        netsh interface portproxy add v4tov4 listenport=$p listenaddress=127.0.0.1 connectaddress=$WslIp connectport=$p | Out-Null
        Write-Host "  portproxy 127.0.0.1:$p -> ${WslIp}:$p"
    }
    $probe = $PortList[0]
    if (-not (Test-HttpPort -Port $probe)) {
        Write-Host "[fix-wsl-localhost] soft portproxy insufficient — restarting wslrelay"
        Get-Process wslrelay -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

function Invoke-FixAsAdmin {
    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -ForceFix"
    Start-Process powershell -Verb RunAs -ArgumentList $psArgs -Wait
}

$probe = $Ports[0]
$wslIp = Get-WslIp
if (-not $wslIp) {
    Write-Host "[fix-wsl-localhost] ERROR: WSL not running"
    exit 1
}

$proxyTarget = Get-PortProxyTarget -Port $probe
$needsSync = ($proxyTarget -and $proxyTarget -ne $wslIp)

if (-not $ForceFix -and -not $needsSync -and (Test-HttpPort -Port $probe)) {
    Write-Host "[fix-wsl-localhost] OK localhost:$probe"
    exit 0
}

if ($needsSync) {
    Write-Host "[fix-wsl-localhost] WSL IP changed ($proxyTarget -> $wslIp), refreshing portproxy..."
    $ForceFix = $true
}

if (-not $ForceFix -and (Test-HttpPort -Port $probe)) {
    Write-Host "[fix-wsl-localhost] OK localhost:$probe"
    exit 0
}

Write-Host "[fix-wsl-localhost] localhost:$probe not reachable (WSL IP $wslIp)"

if (-not (Test-WslHttpPort -Port $probe -WslIp $wslIp)) {
    Write-Host "[fix-wsl-localhost] ERROR: WSL service on ${wslIp}:$probe also down - run start-team first"
    exit 1
}

Write-Host "[fix-wsl-localhost] WSL service OK but Windows localhost broken (stale wslrelay)"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[fix-wsl-localhost] Requesting admin to install portproxy (click Yes on UAC)..."
    Invoke-FixAsAdmin
    if (Test-HttpPort -Port $probe) {
        Write-Host "[fix-wsl-localhost] Fixed"
        exit 0
    }
    Write-Host "[fix-wsl-localhost] Still failing. UAC denied or portproxy failed."
    exit 2
}

Install-PortProxy -WslIp $wslIp -PortList $Ports

if (Test-HttpPort -Port $probe) {
    Write-Host "[fix-wsl-localhost] Fixed via portproxy"
    exit 0
}

Write-Host "[fix-wsl-localhost] Still failing. Run: wsl --shutdown then restart team"
exit 3
