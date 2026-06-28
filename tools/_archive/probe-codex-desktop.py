import subprocess, sys, json
ps = r"""
$apps = Get-StartApps | Where-Object { $_.Name -match 'Codex|OpenAI' -or $_.AppId -match 'Codex|OpenAI' }
$apps | Select-Object Name, AppId | ConvertTo-Json -Compress
"""
r = subprocess.run(
    ["powershell", "-NoProfile", "-Command", ps],
    capture_output=True, encoding="utf-8", errors="replace", timeout=30,
)
print("rc", r.returncode)
print("out", r.stdout[:2000])
print("err", r.stderr[:500])
for name in ("codex", "codex-app"):
    import shutil
    p = shutil.which(name)
    if p: print("which", name, p)
