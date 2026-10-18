#!/bin/bash
set -eux
CONTAINER=docker-agents-hermes-1

# Try fix onnxruntime via curl -L (follow redirects)
docker exec -u root "$CONTAINER" bash -c '
  set -e
  ORT=/opt/memos-local-plugin/node_modules/onnxruntime-node
  if [ ! -d "$ORT" ]; then echo no-ort; exit 0; fi
  VER=$(node -p "require(\"$ORT/package.json\").version")
  echo ort-version=$VER
  # official release asset naming
  PLATFORM=linux-x64
  OUT="$ORT/bin/napi-v3/$PLATFORM"
  mkdir -p "$OUT"
  URL="https://github.com/microsoft/onnxruntime/releases/download/v${VER}/onnxruntime-linux-x64-${VER}.tgz"
  # transformers often needs the node binding from npm package dist; try jsdelivr/ghproxy
  CANDIDATES=(
    "https://cdn.jsdelivr.net/npm/onnxruntime-node@${VER}/bin/napi-v3/${PLATFORM}/onnxruntime_binding.node"
    "https://registry.npmmirror.com/onnxruntime-node/-/onnxruntime-node-${VER}.tgz"
  )
  # Extract from npmmirror full package tarball which may include prebuilt binding
  cd /tmp
  rm -rf ort-pack ort.tgz
  if curl -fsSL -o ort.tgz "https://registry.npmmirror.com/onnxruntime-node/-/onnxruntime-node-${VER}.tgz"; then
    mkdir -p ort-pack && tar -xzf ort.tgz -C ort-pack
    find ort-pack -name "onnxruntime_binding.node" | head
    NODEFILE=$(find ort-pack -path "*napi-v3*linux-x64*onnxruntime_binding.node" | head -1 || true)
    if [ -n "$NODEFILE" ]; then
      cp -a "$(dirname "$NODEFILE")/." "$OUT/"
      echo copied-prebuilt
      ls -la "$OUT"
    else
      echo no-prebuilt-in-tarball
      find ort-pack -type f -name "*.node" | head
    fi
  else
    echo download-failed
  fi
'

echo wire-provider

docker exec -u root "$CONTAINER" bash -c '
  set -e
  OPT=/opt/memos-local-plugin
  HERMES_HOME=/home/hermes/.hermes
  RUNTIME=$HERMES_HOME/memos-plugin
  export HOME=/home/hermes
  export HERMES_HOME
  export MEMOS_HOME=$RUNTIME

  mkdir -p "$RUNTIME/data" "$RUNTIME/skills" "$RUNTIME/logs" "$RUNTIME/daemon" "$HERMES_HOME/plugins/memory"

  # seed config
  if [ ! -f "$RUNTIME/config.yaml" ]; then
    if [ -f "$OPT/templates/config.hermes.yaml" ]; then
      cp "$OPT/templates/config.hermes.yaml" "$RUNTIME/config.yaml"
    elif [ -f "$OPT/templates/config.yaml" ]; then
      cp "$OPT/templates/config.yaml" "$RUNTIME/config.yaml"
    else
      printf "%s\n" "embedding:" "  provider: local" "viewer:" "  bindHost: 127.0.0.1" > "$RUNTIME/config.yaml"
    fi
    chmod 600 "$RUNTIME/config.yaml" || true
  fi

  ADAPTER=$OPT/adapters/hermes
  if [ -f "$OPT/dist/bridge.cjs" ]; then
    echo "$OPT/dist/bridge.cjs" > "$ADAPTER/bridge_path.txt"
  else
    echo "$OPT/bridge.cts" > "$ADAPTER/bridge_path.txt"
  fi
  cp "$ADAPTER/plugin.yaml" "$ADAPTER/memos_provider/plugin.yaml" 2>/dev/null || true

  PLUGIN_DIR=$(python3 -c "from pathlib import Path; import plugins.memory as pm; print(Path(pm.__file__).parent)")
  echo PLUGIN_DIR=$PLUGIN_DIR
  ln -sfn "$ADAPTER/memos_provider" "$PLUGIN_DIR/memtensor"
  ln -sfn "$ADAPTER/memos_provider" "$HERMES_HOME/plugins/memory/memtensor"
  ln -sfn "$OPT" "$HERMES_HOME/plugins/memos-local-plugin"

  python3 - <<PY
from plugins.memory import load_memory_provider
p = load_memory_provider("memtensor")
assert p and p.name == "memtensor", p
print("provider-ok", p.name)
PY

  python3 - <<PY
from pathlib import Path
import re
root = Path("/home/hermes/.hermes")
paths = [root / "config.yaml"] + sorted((root / "profiles").glob("*/config.yaml"))
for p in paths:
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    if not p.is_file():
        continue
    if "provider: memtensor" in text:
        print("ok", p)
        continue
    if re.search(r"(?m)^memory:\s*$", text) or "\nmemory:\n" in text or text.startswith("memory:\n"):
        if re.search(r"(?m)^\s+provider:\s*", text):
            text = re.sub(r"(?m)^(\s+provider:\s*).*$", r"\1memtensor", text, count=1)
        else:
            text = re.sub(r"(?m)^(memory:\s*\n)", r"\1  provider: memtensor\n", text, count=1)
    else:
        text = text.rstrip() + "\n\nmemory:\n  provider: memtensor\n"
    p.write_text(text, encoding="utf-8")
    print("patched", p)
PY

  hermes memory status || true
'

# start bridge
docker exec -u root -d "$CONTAINER" bash -c '
  export HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes MEMOS_HOME=/home/hermes/.hermes/memos-plugin
  cd /opt/memos-local-plugin
  if [ -f dist/bridge.cjs ]; then
    nohup node dist/bridge.cjs --agent=hermes --daemon --home="$MEMOS_HOME" >"$MEMOS_HOME/logs/bridge.out" 2>&1 &
  else
    nohup npx --yes tsx bridge.cts --agent=hermes --daemon --home="$MEMOS_HOME" >"$MEMOS_HOME/logs/bridge.out" 2>&1 &
  fi
  echo bridge-started
'
sleep 3
docker exec -u root "$CONTAINER" bash -c '
  export HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes MEMOS_HOME=/home/hermes/.hermes/memos-plugin
  hermes memory status || true
  ls -la /home/hermes/.hermes/plugins/memory/
  curl -fsS --max-time 2 http://127.0.0.1:18800/ >/dev/null && echo VIEWER_OK || echo VIEWER_NOT_YET
  tail -30 /home/hermes/.hermes/memos-plugin/logs/bridge.out 2>/dev/null || true
'

echo DONE
