# Migrate Cursor chat/memory/data from C: to E: via directory junctions.
# Optional tool — not part of mailbus startup. MUST close Cursor completely before running.
param(
    [string]$TargetRoot = "D:\cursor-data",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Test-IsJunction {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $item = Get-Item $Path -Force
    return ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
}

function Get-JunctionTarget {
    param([string]$Path)
    if (-not (Test-IsJunction $Path)) { return $null }
    return (cmd /c "dir `"$Path`" /AL" 2>$null | Select-String '\[(.+)\]' | ForEach-Object { $_.Matches[0].Groups[1].Value })
}

function Stop-CursorIfRunning {
    $procs = Get-Process -Name "Cursor" -ErrorAction SilentlyContinue
    if (-not $procs) { return }
    if (-not $Force) {
        Write-Host "[migrate-cursor] ERROR: Cursor is still running ($($procs.Count) processes)."
        Write-Host "Close Cursor completely, then run this script again."
        exit 1
    }
    Write-Host "[migrate-cursor] Stopping Cursor..."
    $procs | Stop-Process -Force
    Start-Sleep -Seconds 3
}

function Migrate-Dir {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-IsJunction $Source) {
        $target = Get-JunctionTarget $Source
        if ($target -and ($target -like "$TargetRoot*")) {
            Write-Host "[skip] already migrated: $Source -> $target"
            return
        }
        Write-Host "[migrate-cursor] ERROR: $Source is a junction to unexpected target: $target"
        exit 1
    }

    if (-not (Test-Path $Source)) {
        Write-Host "[skip] missing: $Source"
        return
    }

    $parent = Split-Path $Destination -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    if (Test-Path $Destination) {
        Write-Host "[migrate-cursor] ERROR: destination already exists: $Destination"
        exit 1
    }

    Write-Host "[move] $Source"
    Write-Host "    -> $Destination"

    & robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:2 /XJ /MT:8 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host "[migrate-cursor] ERROR: robocopy failed (code $LASTEXITCODE)"
        exit 1
    }

    $backup = "$Source.pre-migrate-bak"
    if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
    Rename-Item $Source $backup
    cmd /c "mklink /J `"$Source`" `"$Destination`"" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Rename-Item $backup $Source
        Write-Host "[migrate-cursor] ERROR: mklink failed for $Source"
        exit 1
    }

    Remove-Item $backup -Recurse -Force
    Write-Host "[ok] junction: $Source -> $Destination"
}

Write-Host "========================================"
Write-Host "  Cursor data migration C: -> E:"
Write-Host "  Target: $TargetRoot"
Write-Host "========================================"

Stop-CursorIfRunning

$migrations = @(
    @{ Source = Join-Path $env:USERPROFILE ".cursor"; Destination = Join-Path $TargetRoot ".cursor" },
    @{ Source = Join-Path $env:APPDATA "Cursor"; Destination = Join-Path $TargetRoot "Roaming\Cursor" },
    @{ Source = Join-Path $env:LOCALAPPDATA "Cursor"; Destination = Join-Path $TargetRoot "Local\Cursor" }
)

foreach ($m in $migrations) {
    Migrate-Dir -Source $m.Source -Destination $m.Destination
}

Write-Host ""
Write-Host "Done. Restart Cursor — data now lives on E:."
