# mailbus python runtime image (D14 双后端并跑).
# Build from the mailbus repo root:
#   docker build -t mailbus-py:latest -f python/docker/Dockerfile .
ARG BASE=docker.m.daocloud.io/library/python:3.13-slim
FROM ${BASE}

WORKDIR /app
COPY python/ ./python/
COPY shared/config/ /app/shared/config/

WORKDIR /app/python
RUN pip install --no-cache-dir -e .

# 端口规约（D14）：python=9814 / java=9815，并行跑互不冲突
EXPOSE 9814
VOLUME ["/app/shared/store"]

# store 为运行时卷（数据不进镜像）；首次启动初始化骨架（空 store 时 serve 会因 0 agent 退出）
CMD ["sh", "-c", "test -f /app/shared/store/config.json || python -m bus.cli init --data-dir /app/shared/store; python -m bus.cli serve --data-dir /app/shared/store --port 9814 --host 0.0.0.0"]
