#!/bin/bash
# ziyan AI Team - Hermes container entrypoint
# 自动拉起 hermes_profile 编制内全部 dashboard（与 ORGANIZATION.md 一致）

sleep 3

bash /sync-identities.sh

if [ -x /mailbus/tools/sync-hermes-framework-skill.sh ]; then
  for agent in lingzhao lingjin lingxi lingtuo lingxun lingzhang; do
    HERMES_AGENT="$agent" HERMES_FRAMEWORK_SKILLS_DIR="/mailbus/access/hermes/.sync/${agent}/skills" \
      HERMES_SKILL_COPY=1 \
      bash /mailbus/tools/sync-hermes-framework-skill.sh || true
  done
fi

echo "[entrypoint] Starting Hermes dashboards..."
HERMES=/usr/local/bin/hermes

start_dash() {
  local profile="$1" port="$2"
  nohup "$HERMES" dashboard --port "$port" --profile "$profile" --host 0.0.0.0 --insecure \
    >/tmp/hermes-dash-"${profile}".log 2>&1 &
  echo "  ${profile} (${port}) started"
}

start_dash lingzhao 9120
start_dash lingjin  9121
start_dash lingxi   9122
start_dash lingtuo  9126
start_dash lingxun  9125
start_dash lingzhang 9127

echo "[entrypoint] Hermes profile dashboards launched (6 agents)"
echo "[entrypoint] lingjian/lingyan → Codex/Claude Code（非 Hermes 容器）"

tail -f /dev/null
