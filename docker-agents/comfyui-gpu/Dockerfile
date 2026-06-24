# ComfyUI · PyTorch cu128 · RTX 50 系 (sm_120)
# 构建：wsl bash docker-agents/start-comfyui-gpu.sh --build
FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY}

RUN for i in 1 2 3; do \
      apt-get update && apt-get install -y --no-install-recommends \
        git libgl1 libglib2.0-0 \
      && break; \
      echo "apt retry $i"; sleep 10; \
    done \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ComfyUI
RUN git clone --depth 1 --branch v0.3.27 https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI

RUN sed -E 's/comfyui-frontend-package==1\.14\.5/comfyui-frontend-package==1.14.6/' requirements.txt > /tmp/req.txt \
    && grep -v -E '^(torch|torchvision|torchaudio)$' /tmp/req.txt > /tmp/req-notorch.txt \
    && python -m pip install --break-system-packages -r /tmp/req-notorch.txt

EXPOSE 8188
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
