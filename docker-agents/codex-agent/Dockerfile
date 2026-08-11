FROM node:22

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY
ARG CODEX_VERSION=
RUN if [ -n "$PROXY" ]; then export HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY"; fi; \
    apt-get update && apt-get install -y --no-install-recommends curl tmux ca-certificates && rm -rf /var/lib/apt/lists/* && \
    if [ -n "$CODEX_VERSION" ]; then \
      npm install -g "@openai/codex@${CODEX_VERSION}" @galaxy-yearn/codex-deepseek-gateway codexapp; \
    else \
      npm install -g @openai/codex @galaxy-yearn/codex-deepseek-gateway codexapp; \
    fi

ENV HTTP_PROXY= HTTPS_PROXY=

# ttyd: 从预编译 release 安装（可选；失败则备用 Web 终端不可用）
RUN curl -fsSL --connect-timeout 30 --max-time 120 \
      -o /usr/local/bin/ttyd \
      https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
    && chmod +x /usr/local/bin/ttyd \
    || { echo "[WARN] ttyd download failed; fallback web terminal unavailable"; touch /usr/local/bin/ttyd-none; }

COPY entrypoint.sh /entrypoint.sh
COPY render-codex-config.sh /usr/local/bin/render-codex-config.sh
COPY start-codex-ui.sh /usr/local/bin/start-codex-ui.sh
COPY start-codex-web.sh /usr/local/bin/start-codex-web.sh
COPY ensure-codex-browser.sh /usr/local/bin/ensure-codex-browser.sh
COPY sync-codex-home-mirror.sh /usr/local/bin/sync-codex-home-mirror.sh
COPY pin-codex-workspace.sh /usr/local/bin/pin-codex-workspace.sh
COPY wait-agentmemory.sh /usr/local/bin/wait-agentmemory.sh
COPY codex-ui-proxy.mjs /usr/local/share/codex/codex-ui-proxy.mjs
COPY deepseek-model-catalog.json /usr/local/share/codex/deepseek-model-catalog.json
COPY deepseek-model-aliases.json /usr/local/share/codex/deepseek-model-aliases.json
RUN chmod +x /entrypoint.sh /usr/local/bin/render-codex-config.sh /usr/local/bin/start-codex-ui.sh /usr/local/bin/start-codex-web.sh /usr/local/bin/ensure-codex-browser.sh /usr/local/bin/sync-codex-home-mirror.sh /usr/local/bin/pin-codex-workspace.sh /usr/local/bin/wait-agentmemory.sh

WORKDIR /mailbus/store

ENV CODEX_HOME=/home/node/.codex
ENV DEEPSEEK_GATEWAY_PORT=3000
ENV AGENTMEMORY_URL=http://iii-engine:3111

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "-c", "tail -f /dev/null"]
