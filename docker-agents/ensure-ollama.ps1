# Ensure Windows host Ollama via mailbus adapter (stock ollama.exe only; do not patch Ollama).
param(
    [string]$DataDir = "E:\ai_tools\mail\store",
    [switch]$NoPull
)

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$script = Join-Path $repo "tools\ensure-ollama.py"

$py = $null
foreach ($name in @("python", "python3", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) {
    Write-Host "[ensure-ollama] ERROR: python not found"
    exit 2
}

$args = @($script, "--data-dir", $DataDir)
if ($NoPull) { $args += "--no-pull" }
& $py @args
exit $LASTEXITCODE
