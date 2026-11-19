FROM python:3.12-slim

# docker CLI (sock 控制)；构建上下文不再依赖本地 docker 二进制文件
ARG DOCKER_VERSION=27.5.1
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" \
     | tar -xz --strip-components=1 -C /usr/local/bin docker/docker \
  && chmod +x /usr/local/bin/docker \
  && apt-get purge -y curl \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# 运行依赖由镜像提供；源码经 ../..:/mailbus 挂载
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

WORKDIR /mailbus/python

EXPOSE 9814

CMD ["python3", "-m", "uvicorn", "mailbus.bootstrap.main:app", "--host", "0.0.0.0", "--port", "9814"]
