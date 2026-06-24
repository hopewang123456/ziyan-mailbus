#!/bin/bash
# 一键应用 pipeline 基础设施修复（仅 mailbus：compose + rules + 修复脚本）
# 不修改 Hermes/OpenClaw/Cline/OpenCode 源码
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
MAIL="$(dirname "$DIR")"
cd "$DIR"

log() { echo "[infra-fix] $*"; }

log "1. 重建 agent 容器（新 volume 挂载）"
docker compose up -d hermes openclaw dali lingxiao mailbus

log "2. 等待容器就绪"
sleep 5

log "3. 验证 store 挂载"
bash "$DIR/verify-agent-store-mount.sh"

log "4. 同步规则到 store/rules"
cp -f "$MAIL/rules/pipeline-agent-paths.md" "$MAIL/store/rules/"
cp -f "$MAIL/rules/closed-loop-task-design.md" "$MAIL/store/rules/"

log "5. 修复 v3 卡住状态（如存在）"
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/repair-pipeline-stuck.py \
  --data-dir /mailbus/store --task-id game-stellar-20260618 --fix || true

log "=== 完成 ==="
log "重推 Step1: docker exec docker-agents-mailbus-1 python3 /mailbus/tools/pipeline-push-step1.py --data-dir /mailbus/store --task-id game-stellar-20260618 --agent lingzhao"
log "验证: bash $DIR/verify-agent-store-mount.sh"
