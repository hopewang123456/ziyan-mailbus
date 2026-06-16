FROM node:22

ARG PROXY=http://172.17.0.1:7898
ENV HTTP_PROXY=$PROXY HTTPS_PROXY=$PROXY NO_PROXY=localhost,127.0.0.1,::1

RUN npm install -g opencode-ai

ENV HTTP_PROXY= HTTPS_PROXY= NO_PROXY=

WORKDIR /workspace

CMD ["bash", "-c", "tail -f /dev/null"]
