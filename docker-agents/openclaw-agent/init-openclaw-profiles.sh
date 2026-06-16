#!/bin/bash
# 为 xiaoqi / yige 生成独立 OpenClaw 状态目录，避免浏览器都进小七
set -euo pipefail

BASE="/workspace/data"
SRC="${BASE}/.openclaw/openclaw.json"

init_profile() {
  local profile="$1"
  local port="$2"
  local statedir="${BASE}/.openclaw-${profile}"

  mkdir -p "$statedir"
  python3 - "$profile" "$port" "$statedir" "$SRC" <<'PY'
import json, sys, shutil, os

profile, port, statedir, src = sys.argv[1:5]
with open(src, encoding="utf-8") as f:
    cfg = json.load(f)

cfg.setdefault("gateway", {})
cfg["gateway"]["port"] = int(port)
cfg["gateway"]["bind"] = "lan"

agents = cfg.get("agents", {}).get("list", [])
picked = [a for a in agents if a.get("id") == profile]
if not picked:
    ws = "/mnt/e/ai_tools/openclaw_space"
    if profile == "yige":
        ws = "/mnt/e/ai_tools/openclaw_space/a-yige"
    picked = [{"id": profile, "workspace": ws, "model": {"primary": "deepseek/deepseek-chat"}}]
cfg.setdefault("agents", {})["list"] = picked

out = os.path.join(statedir, "openclaw.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print(f"  init {profile} -> {out} (port {port})")
PY
}

if [ ! -f "$SRC" ]; then
  echo "[init-openclaw-profiles] missing $SRC" >&2
  exit 1
fi

init_profile "xiaoqi" 18789 "${BASE}/.openclaw-xiaoqi"
init_profile "yige" 18790 "${BASE}/.openclaw-yige"
