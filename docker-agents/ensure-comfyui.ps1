# ComfyUI — Windows 薄包装；Linux：python tools/mailbus.py docker up-comfyui
# -Start / 默认：compose up GPU 栈；-Smoke：可选 smoke 脚本
param(
  [switch]$Start,
  [switch]$DownloadModel,
  [switch]$Smoke
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$py = $null
foreach ($name in @("python", "python3", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { Write-Host "[ERROR] python not found"; exit 2 }

if ($DownloadModel) {
    Write-Host "[WARN] --download-model 请用 tools/ensure-comfyui.py（若存在）或手动拉模型；本入口仅 compose up"
}

& $py tools/mailbus.py docker up-comfyui
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Smoke) {
    $smoke = Join-Path $root "tools\smoke-comfyui-gpu.py"
    if (Test-Path $smoke) {
        & $py $smoke
        exit $LASTEXITCODE
    }
    Write-Host "[WARN] missing tools/smoke-comfyui-gpu.py"
}
exit 0
