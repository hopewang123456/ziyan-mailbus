#!/usr/bin/env bash
# WSL 内启动 ComfyUI GPU 容器
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUILD=0
for arg in "$@"; do
  if [ "$arg" = "--build" ]; then BUILD=1; fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker 未安装" >&2
  exit 1
fi

if [ "$BUILD" = "1" ]; then
  docker compose -f docker-compose.comfyui-gpu.yml build
fi

docker compose -f docker-compose.comfyui-gpu.yml up -d --force-recreate
echo "waiting for ComfyUI (up to 120s) ..."
ready=0
for i in $(seq 1 24); do
  if curl -sf --connect-timeout 5 http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done
if [ "$ready" != "1" ]; then
  echo "WARN: ComfyUI not ready yet; check: docker logs mailbus-comfyui-gpu" >&2
fi
echo ""
echo "ComfyUI GPU (WSL): http://127.0.0.1:8188"
echo "Windows mailbus: powershell -File tools/sync-comfyui-url.ps1"
echo "GPU 分时: store/config.json mailbus_internal_llm.gpu_sharing"
echo "勿并行启动 Windows CPU 版 ComfyUI（ensure-comfyui.ps1 -Start）以免占 8188"
