FROM python:3.12

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

ARG HERMES_VERSION=
RUN pip config set global.timeout 600
RUN if [ -n "$HERMES_VERSION" ]; then \
      pip install --no-cache-dir "hermes-agent==${HERMES_VERSION}"; \
    else \
      pip install --no-cache-dir hermes-agent; \
    fi

# 预装 Chromium 和 Node.js，避免首次启动交互提示
RUN apt-get update && apt-get install -y -qq chromium nodejs npm 2>&1 | tail -5; \
    if ! which node >/dev/null 2>&1; then \
        echo "=== nodejs not found via apt, trying nodesource ===" && \
        apt-get install -y -qq curl gnupg && \
        curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
        apt-get install -y -qq nodejs; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    which npx || npm install -g npm@latest

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

WORKDIR /home/hermes

# 首次运行预热
RUN hermes chat -Q --help >/dev/null 2>&1 || true

# 使用外部 entrypoint 脚本（预启动所有 dashboard）
COPY entrypoint.sh /entrypoint.sh
COPY sync-identities.sh /sync-identities.sh
RUN chmod +x /entrypoint.sh /sync-identities.sh

ENTRYPOINT ["/entrypoint.sh"]
