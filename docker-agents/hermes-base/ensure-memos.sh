#!/bin/bash
# Ensure MemOS (memtensor) is wired for Hermes volume + start bridge daemon.
set -euo pipefail

OPT=/opt/memos-local-plugin
HERMES_HOME="${HERMES_HOME:-/home/hermes/.hermes}"
RUNTIME="${MEMOS_HOME:-$HERMES_HOME/memos-plugin}"
export HOME="${HOME:-/home/hermes}"
export HERMES_HOME
export MEMOS_HOME="$RUNTIME"

if [ ! -d "$OPT/adapters/hermes/memos_provider" ]; then
  echo "[memos] skip: $OPT not present in image"
  exit 0
fi

mkdir -p "$RUNTIME/data" "$RUNTIME/skills" "$RUNTIME/logs" "$RUNTIME/daemon" "$HERMES_HOME/plugins/memory"

if [ ! -f "$RUNTIME/config.yaml" ]; then
  if [ -f "$OPT/templates/config.hermes.yaml" ]; then
    cp "$OPT/templates/config.hermes.yaml" "$RUNTIME/config.yaml"
  elif [ -f "$OPT/templates/config.yaml" ]; then
    cp "$OPT/templates/config.yaml" "$RUNTIME/config.yaml"
  else
    printf '%s\n' 'embedding:' '  provider: local' 'viewer:' '  bindHost: 127.0.0.1' > "$RUNTIME/config.yaml"
  fi
  chmod 600 "$RUNTIME/config.yaml" || true
fi

PLUGIN_DIR="$(python3 -c 'from pathlib import Path; import plugins.memory as pm; print(Path(pm.__file__).parent)' 2>/dev/null || true)"
if [ -n "$PLUGIN_DIR" ]; then
  ln -sfn "$OPT/adapters/hermes/memos_provider" "$PLUGIN_DIR/memtensor"
fi
ln -sfn "$OPT/adapters/hermes/memos_provider" "$HERMES_HOME/plugins/memory/memtensor"
ln -sfn "$OPT" "$HERMES_HOME/plugins/memos-local-plugin"

python3 - <<'PY' || true
from pathlib import Path
import re
root = Path("/home/hermes/.hermes")
paths = [root / "config.yaml"]
if (root / "profiles").is_dir():
    paths += sorted((root / "profiles").glob("*/config.yaml"))
for p in paths:
    if not p.is_file():
        continue
    text = p.read_text(encoding="utf-8")
    if "provider: memtensor" in text:
        continue
    if "memory:" in text:
        if re.search(r"(?m)^\s+provider:\s*", text):
            text = re.sub(r"(?m)^(\s+provider:\s*).*$", r"\1memtensor", text, count=1)
        else:
            text = re.sub(r"(?m)^(memory:\s*\n)", r"\1  provider: memtensor\n", text, count=1)
    else:
        text = text.rstrip() + "\n\nmemory:\n  provider: memtensor\n"
    p.write_text(text, encoding="utf-8")
    print(f"[memos] patched {p}")
PY

# Start bridge if not already listening
if ! curl -fsS --max-time 1 http://127.0.0.1:18800/ >/dev/null 2>&1; then
  # Drop stale pid files that point at unrelated processes (causes "killing stale bridge" loops)
  if [ -f "$RUNTIME/daemon/bridge.pid" ]; then
    old_pid="$(cat "$RUNTIME/daemon/bridge.pid" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && ! ps -p "$old_pid" -o args= 2>/dev/null | grep -q "bridge"; then
      rm -f "$RUNTIME/daemon/bridge.pid"
    fi
  fi
  cd "$OPT"
  # Prefer non --daemon + nohup: --daemon path may exit after killing a stale pid
  if [ -f dist/bridge.cjs ]; then
    nohup node dist/bridge.cjs --agent=hermes --home="$MEMOS_HOME" \
      >"$RUNTIME/logs/bridge.out" 2>&1 &
  else
    nohup npx --yes tsx bridge.cts --agent=hermes --home="$MEMOS_HOME" \
      >"$RUNTIME/logs/bridge.out" 2>&1 &
  fi
  echo "[memos] bridge starting (viewer :18800)"
else
  echo "[memos] viewer already up on :18800"
fi
