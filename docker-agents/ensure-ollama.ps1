# Ensure Windows host Ollama via mailbus adapter (stock ollama.exe only; do not patch Ollama).
param(
    [string]$DataDir = "E:\ai_tools\mail\store",
    [switch]$NoPull,
    [int]$WaitSeconds = 90
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

function Test-OllamaApi {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Start-OllamaHost {
    $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    $ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"
    $started = $false
    if (-not (Test-OllamaApi)) {
        if (Test-Path $ollamaApp) {
            Write-Host "[ensure-ollama] starting Ollama desktop app..."
            Start-Process -FilePath $ollamaApp -WindowStyle Hidden -ErrorAction SilentlyContinue
            $started = $true
        }
        if (-not $started -and (Test-Path $ollamaExe)) {
            Write-Host "[ensure-ollama] starting ollama serve..."
            Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
            $started = $true
        }
        if (-not $started) {
            Write-Host "[ensure-ollama] WARN: Ollama not installed — download from https://ollama.com/download"
            return
        }
        $loops = [Math]::Max(15, [Math]::Ceiling($WaitSeconds / 2))
        for ($i = 0; $i -lt $loops; $i++) {
            Start-Sleep -Seconds 2
            if (Test-OllamaApi) {
                Write-Host "[ensure-ollama] API ready after $((($i + 1) * 2))s"
                return
            }
        }
        Write-Host "[ensure-ollama] WARN: API still down after ${WaitSeconds}s"
    }
}

if (-not (Test-OllamaApi)) {
    Start-OllamaHost
}

$pyArgs = @($script, "--data-dir", $DataDir, "--wait-seconds", "$WaitSeconds")
if ($NoPull) { $pyArgs += "--no-pull" }
& $py @pyArgs
exit $LASTEXITCODE
