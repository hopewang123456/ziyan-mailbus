# ComfyUI Windows 入口
# Usage: .\docker-agents\ensure-comfyui.ps1 [-Start] [-DownloadModel] [-Smoke]
# 注意：WSL GPU 容器已启用时勿 -Start（会抢 8188 端口）
param(
  [switch]$Start,
  [switch]$DownloadModel,
  [switch]$Smoke
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$gpu = wsl docker inspect mailbus-comfyui-gpu --format "{{.State.Running}}" 2>$null
if ($gpu -eq "true" -and ($Start -or $Smoke)) {
  Write-Host "[WARN] mailbus-comfyui-gpu 已在 WSL 运行；跳过 Windows CPU 启动。用 tools/sync-comfyui-url.ps1 同步 URL。" -ForegroundColor Yellow
  if ($Smoke) {
    python tools/smoke-comfyui-gpu.py
    exit $LASTEXITCODE
  }
  exit 0
}

# 加载 env
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
      $k = $matches[1].Trim(); $v = $matches[2].Trim().Trim('"')
      if ($v -and -not [Environment]::GetEnvironmentVariable($k)) {
        Set-Item -Path "Env:$k" -Value $v
      }
    }
  }
}

$args = @("tools/ensure-comfyui.py")
if ($DownloadModel) { $args += "--download-model" }
if ($Start -or $Smoke) { $args += "--start" }
if ($Smoke) { $args += "--smoke" }
python @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "ComfyUI: http://127.0.0.1:8188" -ForegroundColor Green
