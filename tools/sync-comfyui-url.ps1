# Sync COMFYUI_BASE_URL for Windows mailbus -> WSL Docker ComfyUI
# Usage: .\tools\sync-comfyui-url.ps1 [-Quiet]
param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$args = @("tools/sync-comfyui-url.py")
if ($Quiet) { $args += "--quiet" }
python @args
exit $LASTEXITCODE
