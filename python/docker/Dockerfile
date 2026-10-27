# mailbus python runtime image (D14 双后端并跑).
# Build from the mailbus repo root:
#   docker build -t mailbus-py:latest -f python/docker/Dockerfile .
ARG BASE=python:3.13-slim
FROM ${BASE}

WORKDIR /app
COPY python/ ./python/
COPY shared/config/ ./shared/config/
COPY shared/store/ ./shared/store/

WORKDIR /app/python
RUN pip install --no-cache-dir -e .

# 端口规约（D14）：python=9814 / java=9815，并行跑互不冲突
EXPOSE 9814
VOLUME ["/app/shared/store"]

ENTRYPOINT ["python", "-m", "bus.cli", "serve", "--data-dir", "/app/shared/store", "--port", "9814", "--host", "0.0.0.0"]
