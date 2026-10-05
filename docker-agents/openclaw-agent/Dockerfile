# node:22 基底 + 构建时升级 Node 24：openclaw 2026.9.8+ 强制 Node >=24.16，
# 但 Docker Hub 拉取 node:24 常被网络阻断——改从 npmmirror 二进制镜像站装
# （构建网络到 npmmirror 稳定）。必须先删旧 npm 再解压：新旧 npm 混装会
# "Class extends value undefined" 崩溃。--allow-scripts：npm 11 默认拦截
# 全局安装的生命周期脚本，esbuild/koffi/protobufjs 原生依赖需要。
FROM node:22

# 与 openclaw 2026.9.8 要求(>=24.16 <25)同步升级；npmmirror /binaries/node 可查最新
# 坑：node 官方镜像自带 ENV NODE_VERSION=22.22.3，会覆盖同名 ARG（ENV > ARG），
# 必须 用 NODE_VER 这个不冲突的名字，否则下载的还是 22。
# 先落文件再解压，set -eux 保证任何一步失败即断。
ARG NODE_VER=24.21.0
RUN set -eux; \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack; \
    curl -fsSL -o /tmp/node24.tar.xz "https://cdn.npmmirror.com/binaries/node/v${NODE_VER}/node-v${NODE_VER}-linux-x64.tar.xz"; \
    tar -xJf /tmp/node24.tar.xz --strip-components=1 -C /usr/local; \
    rm /tmp/node24.tar.xz; \
    test "$(node --version)" = "v${NODE_VER}"; \
    npm --version

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

ARG OPENCLAW_VERSION=
ARG npm_config_registry=
RUN if [ -n "$OPENCLAW_VERSION" ]; then \
      npm install -g --allow-scripts=@google/genai,esbuild,koffi,protobufjs,openclaw "openclaw@${OPENCLAW_VERSION}"; \
    else \
      npm install -g --allow-scripts=@google/genai,esbuild,koffi,protobufjs,openclaw openclaw; \
    fi

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

WORKDIR /workspace

# 使用外部 entrypoint 脚本（预启动所有 gateway）
COPY entrypoint.sh /entrypoint.sh
COPY init-openclaw-profiles.sh /init-openclaw-profiles.sh
COPY load-hermes-env.sh /load-hermes-env.sh
RUN chmod +x /entrypoint.sh /init-openclaw-profiles.sh /load-hermes-env.sh

ENTRYPOINT ["/entrypoint.sh"]
