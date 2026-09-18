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

# 预装 Chromium / Node / 编译链（MemOS better-sqlite3）
RUN apt-get update && apt-get install -y -qq chromium nodejs npm build-essential python3-setuptools g++ make curl 2>&1 | tail -8; \
    if ! which node >/dev/null 2>&1; then \
        echo "=== nodejs not found via apt, trying nodesource ===" && \
        apt-get install -y -qq curl gnupg && \
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
        apt-get install -y -qq nodejs; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    which npx || npm install -g npm@latest; \
    npm install -g node-gyp@11; \
    if [ -d /usr/share/nodejs/node-gyp ] && [ ! -L /usr/share/nodejs/node-gyp ]; then \
      mv /usr/share/nodejs/node-gyp /usr/share/nodejs/node-gyp.debian.bak; \
    fi; \
    ln -sfn /usr/local/lib/node_modules/node-gyp /usr/share/nodejs/node-gyp

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

# MemOS local plugin → /opt（镜像内 Linux FS；运行时数据在 volume $HERMES_HOME/memos-plugin）
ARG MEMOS_VERSION=2.0.16
RUN set -eux; \
    npm config set registry https://registry.npmmirror.com; \
    npm config set fetch-timeout 600000; \
    mkdir -p /tmp/memos-pack /opt/memos-local-plugin; \
    cd /tmp/memos-pack; \
    npm pack "@memtensor/memos-local-plugin@${MEMOS_VERSION}"; \
    tar -xzf memtensor-memos-local-plugin-*.tgz; \
    cp -a package/. /opt/memos-local-plugin/; \
    cd /opt/memos-local-plugin; \
    npm install --omit=dev --no-fund --no-audit --ignore-scripts; \
    cd node_modules/better-sqlite3; \
    /usr/bin/node /usr/share/nodejs/node-gyp/bin/node-gyp.js rebuild --release; \
    cd /opt/memos-local-plugin; \
    ORT_VER="$(node -p "require('./node_modules/onnxruntime-node/package.json').version")"; \
    curl -fsSL -o /tmp/ort.tgz "https://registry.npmmirror.com/onnxruntime-node/-/onnxruntime-node-${ORT_VER}.tgz"; \
    mkdir -p /tmp/ort-pack && tar -xzf /tmp/ort.tgz -C /tmp/ort-pack; \
    SRC="$(find /tmp/ort-pack -path '*napi-v6/linux/x64/onnxruntime_binding.node' | head -1)"; \
    mkdir -p node_modules/onnxruntime-node/bin/napi-v6/linux/x64; \
    cp -a "$(dirname "$SRC")/." node_modules/onnxruntime-node/bin/napi-v6/linux/x64/; \
    PLUGIN_DIR="$(python3 -c 'from pathlib import Path; import plugins.memory as pm; print(Path(pm.__file__).parent)')"; \
    ln -sfn /opt/memos-local-plugin/adapters/hermes/memos_provider "${PLUGIN_DIR}/memtensor"; \
    cp /opt/memos-local-plugin/adapters/hermes/plugin.yaml /opt/memos-local-plugin/adapters/hermes/memos_provider/plugin.yaml 2>/dev/null || true; \
    if [ -f /opt/memos-local-plugin/dist/bridge.cjs ]; then \
      echo /opt/memos-local-plugin/dist/bridge.cjs > /opt/memos-local-plugin/adapters/hermes/bridge_path.txt; \
    else \
      echo /opt/memos-local-plugin/bridge.cts > /opt/memos-local-plugin/adapters/hermes/bridge_path.txt; \
    fi; \
    rm -rf /tmp/memos-pack /tmp/ort-pack /tmp/ort.tgz; \
    du -sh /opt/memos-local-plugin

WORKDIR /home/hermes

# 首次运行预热
RUN hermes chat -Q --help >/dev/null 2>&1 || true

# 使用外部 entrypoint 脚本（预启动所有 dashboard）
COPY entrypoint.sh /entrypoint.sh
COPY sync-identities.sh /sync-identities.sh
COPY ensure-memos.sh /ensure-memos.sh
RUN chmod +x /entrypoint.sh /sync-identities.sh /ensure-memos.sh

ENTRYPOINT ["/entrypoint.sh"]
