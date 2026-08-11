FROM node:22

ARG PROXY=
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

ARG OPENCODE_VERSION=
RUN if [ -n "$OPENCODE_VERSION" ]; then \
      npm install -g "opencode-ai@${OPENCODE_VERSION}"; \
    else \
      npm install -g opencode-ai; \
    fi

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "-c", "tail -f /dev/null"]
