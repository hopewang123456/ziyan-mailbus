# Restart native mailbus serve (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File tools/restart-mailbus.ps1 [port]
param([int]$Port = 9814)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-Mailbus {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/status" -UseBasicParsing -TimeoutSec 5
        return $r.StatusCode -eq 200
    } catch { return $false }
}

Write-Host "[restart] stopping processes on port $Port ..."
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

$LogDir = Join-Path $Root "store\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutLog = Join-Path $LogDir "mailbus-serve.out.log"
$ErrLog = Join-Path $LogDir "mailbus-serve.err.log"

Write-Host "[restart] starting mailbus on port $Port ..."
Start-Process python -ArgumentList @(
    (Join-Path $Root "bus.py"), "serve",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--data-dir", (Join-Path $Root "store")
) -WorkingDirectory $Root -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog

for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Mailbus) {
        Write-Host "[restart] OK http://127.0.0.1:$Port/"
        exit 0
    }
}
Write-Host "[restart] mailbus not ready; see $OutLog and $ErrLog" -ForegroundColor Red
exit 1
