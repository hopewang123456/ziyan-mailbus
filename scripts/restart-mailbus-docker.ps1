# 重启 mailbus 容器以加载新代码（Docker 部署）
# Usage: .\scripts\restart-mailbus-docker.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $root "docker-agents")
docker compose restart mailbus
$port = if ($env:MAILBUS_API_PORT) { $env:MAILBUS_API_PORT } else { "9814" }
Write-Host "mailbus restarted — API: http://127.0.0.1:${port}/ (Docker + native, `$MAILBUS_API_PORT)"
