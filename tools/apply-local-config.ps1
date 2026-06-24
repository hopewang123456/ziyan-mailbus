# 一键检查本地 mailbus 配置（Windows）
# Usage: .\tools\apply-local-config.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$mailRoot = Split-Path -Parent $root
Set-Location $mailRoot

Write-Host "== mailbus 本地配置检查 ==" -ForegroundColor Cyan

& (Join-Path $mailRoot "tools\sync-comfyui-url.ps1") -Quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ComfyUI 未就绪（可稍后 wsl bash docker-agents/start-comfyui-gpu.sh）" -ForegroundColor Yellow
}

& (Join-Path $mailRoot "tools\sync-n8n-url.ps1") -Quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "n8n 未就绪（可稍后 wsl bash docker-agents/start-n8n.sh）" -ForegroundColor Yellow
}

$envFile = Join-Path $mailRoot ".env"
$dockerEnv = Join-Path $mailRoot "docker-agents\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "创建 .env（从 docker-agents/.env 同步）..." -ForegroundColor Yellow
    if (Test-Path $dockerEnv) {
        Copy-Item $dockerEnv $envFile
        (Get-Content $envFile) -replace 'host.docker.internal', '127.0.0.1' | Set-Content $envFile
    } else {
        Copy-Item (Join-Path $mailRoot "docker-agents\.env.example") $envFile
        Write-Host "请编辑 $envFile 填入 API Key" -ForegroundColor Red
    }
}

python -c @"
from lib.env_bootstrap import load_mailbus_env
load_mailbus_env()
from lib.internal_llm.probe import probe_all
h = probe_all('store')
for p in h.get('providers', []):
    print(f\"  {p.get('name')}: {'OK' if p.get('ok') else 'FAIL'} {p.get('error') or ''}\")
"@

Write-Host "`n配置检查完成。启动: python bus.py serve --port 9814 --data-dir store" -ForegroundColor Green
