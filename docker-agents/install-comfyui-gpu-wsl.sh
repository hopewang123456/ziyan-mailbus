#!/usr/bin/env bash
# WSL 一键：Docker 代理 + NVIDIA Container Toolkit + ComfyUI GPU
# 用法（Windows）：wsl -u root bash /mnt/e/ai_tools/mail/docker-agents/install-comfyui-gpu-wsl.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIN_HOST="$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)"
CLASH_PORT="${CLASH_PORT:-7897}"
PROXY="http://${WIN_HOST}:${CLASH_PORT}"
DAEMON_JSON="/etc/docker/daemon.json"

echo "[1/6] 同步 apt / Docker 代理 → ${PROXY}"
cat > /etc/apt/apt.conf.d/95proxies <<EOF
Acquire::http::Proxy "${PROXY}/";
Acquire::https::Proxy "${PROXY}/";
EOF

python3 - <<'PY' "$DAEMON_JSON" "$PROXY"
import json, sys
path, proxy = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {}
proxies = cfg.setdefault("proxies", {})
proxies["http-proxy"] = proxy
proxies["https-proxy"] = proxy
proxies.setdefault(
    "no-proxy",
    "localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
)
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("  updated", path)
PY

echo "[2/6] 添加 NVIDIA Container Toolkit 源"
install -d /usr/share/keyrings
curl -fsSL -x "${PROXY}" https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL -x "${PROXY}" https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list

echo "[3/6] 安装 nvidia-container-toolkit"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nvidia-container-toolkit

echo "[4/6] 配置 Docker NVIDIA runtime"
nvidia-ctk runtime configure --runtime=docke

echo "[5/6] 重启 Docker"
systemctl restart docker || service docker restart
sleep 2

echo "[6/6] 验证 GPU"
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi -L

echo ""
echo "Docker GPU 就绪。普通用户构建 ComfyUI："
echo "  cd ${SCRIPT_DIR} && bash start-comfyui-gpu.sh"
