# mailbus-j Windows installer (python/windows counterpart, M4).
# Registers "mailbus-j-serve" at logon. schtasks ONLOGON needs admin, so the
# primary path is the per-user Startup folder (python wsl_keepalive lesson);
# an elevated schtasks variant is used when -UseSchtasks is passed explicitly.
# Usage: powershell -ExecutionPolicy Bypass -File register-task.ps1 [-JarPath ..] [-DataDir ..] [-Port ..] [-UseSchtasks]
param(
    [string]$JarPath = "E:\ai_tools\mailbus\java\mailbus-boot\target\mailbus-boot-0.1.0-SNAPSHOT.jar",
    [string]$DataDir = "E:\ai_tools\mailbus\java\store",
    [int]$Port = 9815,
    [switch]$UseSchtasks
)

$ErrorActionPreference = "Stop"
$taskName = "mailbus-j-serve"

if (-not (Test-Path $JarPath)) {
    Write-Error "jar not found: $JarPath (run mvn -pl mailbus-boot -am package first)"
}

$java = (Get-Command java -ErrorAction SilentlyContinue).Source
if (-not $java) { $java = "java" }
$args_ = "-jar `"$JarPath`" --server.port=$Port --mailbus.data-dir=$DataDir"

if ($UseSchtasks) {
    schtasks /create /tn $taskName /tr "`"$java`" $args_" /sc onlogon /f | Out-Null
    Write-Host "registered $taskName via schtasks (logon trigger)"
} else {
    $startup = [Environment]::GetFolderPath("Startup")
    $vbs = Join-Path $startup "mailbus-j-serve.vbs"
    # ASCII-only VBS (wscript chokes on UTF-8 comments)
    $content = "'mailbus-j serve launcher (no console window)`n" +
        "Set s = CreateObject(`"WScript.Shell`")`n" +
        "s.Run `"`"`"$java`"`" -jar `"`"`"$JarPath`"`" --server.port=$Port --mailbus.data-dir=$DataDir`"`", 0, False`n"
    Set-Content -Path $vbs -Value $content -Encoding ASCII
    Write-Host "installed startup launcher: $vbs"
}
Write-Host "start now:   run the vbs (or schtasks /run /tn $taskName)"
Write-Host "unregister:  powershell -File unregister-task.ps1"
