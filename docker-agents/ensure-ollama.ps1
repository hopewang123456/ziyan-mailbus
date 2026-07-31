# Ensure Ollama — Windows 薄包装（可额外拉起桌面端）；跨平台核心：
#   python tools/mailbus.py docker ensure-ollama
param(
    [string]$DataDir = "",
    [switch]$NoPull,
    [int]$WaitSeconds = 90
)
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repo

# Best-effort: start Windows Ollama app if API down
function Test-OllamaApi {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}
if (-not (Test-OllamaApi)) {
    $ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"
    if (Test-Path $ollamaApp) {
        Write-Host "[ensure-ollama] starting Ollama desktop app..."
        Start-Process -FilePath $ollamaApp -WindowStyle Hidden -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    }
}

$py = $null
foreach ($name in @("python", "python3", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { Write-Host "[ensure-ollama] ERROR: python not found"; exit 2 }

$argv = @("tools/mailbus.py", "docker", "ensure-ollama", "--wait-seconds", "$WaitSeconds")
if ($DataDir) { $argv += @("--data-dir", $DataDir) }
if (-not $NoPull) { $argv += "--pull" }
& $py @argv
exit $LASTEXITCODE
