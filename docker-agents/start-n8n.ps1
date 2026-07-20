# 启动 n8n（Docker）— 无需全局 npm 安装
# 前置：Docker Desktop 已启动
# Usage: .\docker-agents\start-n8n.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
docker compose -f docker-compose.n8n.yml up -d
Write-Host "n8n UI: http://127.0.0.1:5678" -ForegroundColor Green
Write-Host "Deploy workflow: ..\tools\setup-n8n.ps1" -ForegroundColor Cyan
Write-Host "  (or WSL: bash docker-agents/ensure-n8n-workflow.sh)" -ForegroundColor DarkGray
