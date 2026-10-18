#!/bin/bash
# Mailbus — dsh (DeepSeek Harness) container entrypoint
set -euo pipefail

export DSH_HOME="${DSH_HOME:-/home/dsh/.dsh}"
mkdir -p "$DSH_HOME"/{profiles,plugins,sessions,credentials}

cd /workspace

# 常驻 web 实例控制台（3080）。dsh 出于安全强制 web 绑 127.0.0.1
# （禁 --host 0.0.0.0，会暴露远程代码执行），故仅容器内可访问；
# mailbus 主链路是 headless push（docker exec），web 仅供容器内排障。
if [ "${DSH_WEB_ENABLED:-1}" = "1" ]; then
  nohup dsh web >/tmp/dsh-web.log 2>&1 </dev/null &
  echo "[entrypoint] dsh web started (pid=$!) — container-local 127.0.0.1:3080"
fi

echo "[entrypoint] dsh ready (headless push: docker exec mailbus-dsh dsh --profile headless 'MSG')"
tail -f /dev/null
