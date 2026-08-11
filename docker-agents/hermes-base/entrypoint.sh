#!/bin/bash
# ziyan AI Team - Hermes container entrypoint
# 自动拉起 hermes_profile 编制内全部 dashboard（与 ORGANIZATION.md 一致）

sleep 3

bash /sync-identities.sh

# 确保 config.yaml 存在，设置默认 provider/model 为 deepseek
CONFIG_FILE="/home/hermes/.hermes/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "[entrypoint] Creating default config.yaml (deepseek-v4-pro)"
  cat > "$CONFIG_FILE" <<'EOFYAML'
model: deepseek-v4-pro
provider: deepseek
EOFYAML
fi

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
python3.12 -m lib.adapters.frameworks.hermes_dashboard start-all

echo "[entrypoint] Hermes profile dashboards launched (6 agents)"
echo "[entrypoint] lingjian/lingyan → Codex/Claude Code（非 Hermes 容器）"

exec tail -f /dev/null
