FROM node:22

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

ARG OPENCLAW_VERSION=
RUN if [ -n "$OPENCLAW_VERSION" ]; then \
      npm install -g "openclaw@${OPENCLAW_VERSION}"; \
    else \
      npm install -g openclaw; \
    fi

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

WORKDIR /workspace

# 使用外部 entrypoint 脚本（预启动所有 gateway）
COPY entrypoint.sh /entrypoint.sh
COPY init-openclaw-profiles.sh /init-openclaw-profiles.sh
COPY load-hermes-env.sh /load-hermes-env.sh
RUN chmod +x /entrypoint.sh /init-openclaw-profiles.sh /load-hermes-env.sh

ENTRYPOINT ["/entrypoint.sh"]
