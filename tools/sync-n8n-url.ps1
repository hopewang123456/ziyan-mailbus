# Sync N8N_PUBLISH_WEBHOOK_URL for Windows mailbus -> WSL Docker n8n
# Usage: .\tools\sync-n8n-url.ps1 [-Quiet]
param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$args = @("tools/sync-n8n-url.py")
if ($Quiet) { $args += "--quiet" }
python @args
exit $LASTEXITCODE
