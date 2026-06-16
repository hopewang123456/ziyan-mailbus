FROM python:3.12

ARG PROXY=http://172.17.0.1:7898
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

RUN pip config set global.timeout 600
RUN pip install --no-cache-dir hermes-agent

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=
# 跳过浏览器工具安装，CLI 模式不需要
ENV HERMES_SKIP_BROWSER_INSTALL=1

WORKDIR /home/hermes

COPY <<'SCRIPT' /entrypoint.sh
#!/bin/bash
# 不预启动 hermes，由 CLI 弹窗按需启动
tail -f /dev/null
SCRIPT
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
