# Sync COMFYUI_BASE_URL for Windows mailbus -> WSL Docker ComfyUI
# Usage: .\tools\tools/ops/sync-comfyui-url.ps1 [-Quiet]
param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$args = @("tools/ops/tools/ops/sync-comfyui-url.py")
if ($Quiet) { $args += "--quiet" }
python @args
exit $LASTEXITCODE
