#!/bin/bash
# ziyan AI Team - Hermes container entrypoint
# 自动拉起所有 profile 的 dashboard

sleep 3

bash /sync-identities.sh

echo "[entrypoint] Starting Hermes dashboards..."
HERMES=/usr/local/bin/hermes

nohup $HERMES dashboard --port 9120 --profile lingzhao --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingzhao (9120) started"

nohup $HERMES dashboard --port 9121 --profile lingjin --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingjin (9121) started"

nohup $HERMES dashboard --port 9122 --profile lingxi --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingxi (9122) started"

nohup $HERMES dashboard --port 9123 --profile lingjian --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingjian (9123) started"

nohup $HERMES dashboard --port 9124 --profile lingyan --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingyan (9124) started"

nohup $HERMES dashboard --port 9125 --profile lingxun --host 0.0.0.0 --insecure >/dev/null 2>&1 &
echo "  lingxun (9125) started"

echo "[entrypoint] All Hermes dashboards launched"

# 保持容器运行
tail -f /dev/null
