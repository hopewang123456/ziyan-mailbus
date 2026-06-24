# 重启 mailbus 容器以加载新代码（Docker 部署）
# Usage: .\scripts\restart-mailbus-docker.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $root "docker-agents")
docker compose restart mailbus
Write-Host "mailbus restarted — Docker: http://127.0.0.1:9812/  |  Windows native: http://127.0.0.1:9814/"
