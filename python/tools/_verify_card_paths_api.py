#!/usr/bin/env python3
import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
cfg_path = ROOT / "store" / "config.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
for aid, a in (cfg.get("agents") or {}).items():
    if isinstance(a.get("paths"), dict) and a["paths"]:
        a["custom_paths"] = True
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
subprocess.run(
    ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc", "docker restart docker-agents-mailbus-1"],
    check=False,
)
time.sleep(8)
req = urllib.request.Request("http://127.0.0.1:9814/api/settings/section/agents")
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
print("agents", len(data.get("agents") or []))
for it in data.get("agents") or []:
    paths = it.get("paths") or {}
    native = str(it.get("native_config_path") or "")
    print(
        f"{it['id']:10} custom={it.get('custom_paths')} "
        f"paths={len(paths)} native=...{native[-50:]}"
    )
