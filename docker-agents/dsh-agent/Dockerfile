FROM node:22

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

ARG DSH_VERSION=
RUN if [ -n "$DSH_VERSION" ]; then \
      npm install -g "@deepseek-ai/dsh@${DSH_VERSION}"; \
    else \
      npm install -g @deepseek-ai/dsh; \
    fi

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

ENV DSH_HOME=/home/dsh/.dsh \
    NODE_ENV=production \
    NO_UPDATE_NOTIFIER=1

COPY entrypoint.sh /usr/local/bin/dsh-entrypoint
RUN chmod +x /usr/local/bin/dsh-entrypoint \
    && mkdir -p /workspace "$DSH_HOME"

WORKDIR /workspace
EXPOSE 3080

ENTRYPOINT ["/usr/local/bin/dsh-entrypoint"]
