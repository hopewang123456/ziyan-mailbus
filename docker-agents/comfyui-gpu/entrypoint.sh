#!/usr/bin/env bash
set -euo pipefail
cd /opt/ComfyUI
if [ ! -f main.py ]; then
  echo "ComfyUI 未挂载到 /opt/ComfyUI" >&2
  exit 1
fi

need_install=0
if ! python -c "import safetensors, torch" 2>/dev/null; then
  need_install=1
fi

if [ "$need_install" = "1" ]; then
  echo "[comfyui-gpu] 安装 Python 依赖…"
  sed -E 's/comfyui-frontend-package==1\.14\.5/comfyui-frontend-package==1.14.6/' requirements.txt \
    | grep -v -E '^(torch|torchvision|torchaudio)$' > /tmp/requirements-notorch.txt
  python -m pip install --break-system-packages -r /tmp/requirements-notorch.txt
fi

exec python main.py --listen 0.0.0.0 --port 8188
