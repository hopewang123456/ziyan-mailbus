#!/bin/bash
# ziyan AI Team - Hermes container entrypoint
# 自动拉起 hermes_profile 编制内全部 dashboard（与 ORGANIZATION.md 一致）

sleep 3

bash /sync-identities.sh

# 可选：把 framework skills 同步到 access/hermes/.sync（镜像缓存，非运行时 SoT）。
# Hermes 实际加载: profiles/<id>/skills → Vault views/roles 或 library（junction）。
# 默认 symlink；仅当 HERMES_SKILL_COPY=1 时写实体副本。
if [ -x /mailbus/tools/sync-hermes-framework-skill.sh ]; then
  for agent in lingzhao lingjin lingxi lingtuo lingxun lingzhang; do
    HERMES_AGENT="$agent" HERMES_FRAMEWORK_SKILLS_DIR="/mailbus/access/hermes/.sync/${agent}/skills" \
      bash /mailbus/tools/sync-hermes-framework-skill.sh || true
  done
fi

echo "[entrypoint] Starting Hermes dashboards..."
PYTHON=python3.12
CLI=( "$PYTHON" -m hermes_cli.main -p default dashboard )

start_dash() {
  local profile="$1" port="$2"
  if curl -sf --connect-timeout 2 "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
    echo "  ${profile} (${port}) already up"
    return 0
  fi
  nohup "${CLI[@]}" --port "$port" --host 0.0.0.0 --open-profile "$profile" --insecure --skip-build \
    >/tmp/hermes-dash-"${profile}".log 2>&1 &
  echo "  ${profile} (${port}) starting pid=$!"
  local i
  for i in $(seq 1 15); do
    if curl -sf --connect-timeout 2 "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
      echo "  ${profile} (${port}) ready"
      return 0
    fi
    sleep 2
  done
  echo "  WARNING: ${profile} (${port}) not ready — see /tmp/hermes-dash-${profile}.log"
  tail -3 "/tmp/hermes-dash-${profile}.log" 2>/dev/null || true
}

start_dash lingzhao 9120
start_dash lingjin  9121
start_dash lingxi   9122
start_dash lingxun  9125
start_dash lingtuo  9126
start_dash lingzhang 9127

echo "[entrypoint] Hermes profile dashboards launched (6 agents)"
echo "[entrypoint] lingjian/lingyan → Codex/Claude Code（非 Hermes 容器）"

exec tail -f /dev/null
