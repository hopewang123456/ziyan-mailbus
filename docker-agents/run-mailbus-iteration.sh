#!/bin/bash
# mailbus 迭代 — 默认仅 Round1 诊断；Round2 须 Round1 执行+审计通过
set -euo pipefail

MAIL="/mnt/e/ai_tools/mail"
ROUND="${1:-1}"
DISPATCH="${2:-}"

log() { echo "[iteration] $*"; }

cd "$MAIL"

log "=== Round: $ROUND（Round2 需 round-1-gate.json 中 round2_unlocked=true）==="
FORCE_FLAG=""
if [ "${FORCE:-}" = "1" ]; then
  FORCE_FLAG="--force"
fi
python3 -m bus iteration --round "$ROUND" --data-dir store $FORCE_FLAG
rc=$?

if [ "$ROUND" = "2" ] && [ "$rc" -ne 0 ] && [ -z "$FORCE_FLAG" ]; then
  log "Round2 被拦截 — 请先完成 Round1 主任务 success + 灵鉴 audit"
  log "查看: cat store/iterations/round-1-gate.json"
  exit "$rc"
fi

if [ "$DISPATCH" = "dispatch-r2" ] || { [ "$DISPATCH" = "dispatch" ] && [ "$ROUND" = "2" ]; }; then
  if [ "$rc" -ne 0 ]; then
    log "Round2 未解锁，跳过 dispatch（主任务 success + 灵鉴 audit 后再 dispatch-r2）"
  else
  log "下发 Round2 工单给各 agent..."
  BACKLOG="$MAIL/store/iterations/round-2-backlog.json"
  MSG="【Round2 已解锁】请阅读 store/iterations/round-2-backlog.json 与 iteration-protocol.md。

Round1 已通过（hardening success + 灵鉴 audit warn）。
你的 R2 工单见 backlog items[]，完成后写对应 msg-results/iteration-r2-NNN.json。

优先级：P0 先于 P1；game-lvup 缺 msg-results 的由灵昭补写或确认 tools/fix-game-lvup.py 已回收。"

  python3 -m bus send xiaoqi --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"
  python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "【Round2 R2-001/002/003/006】阅读 round-2-backlog.json，推进 P0 项并写 msg-results。game-lvup-171754 若已有 msg-results 则确认 pipeline 推进到小七。"
  python3 -m bus send lingxiao --data-dir store --from mailbus --type task --priority normal --msg "【Round2 R2-004】验收内置 scheduler：/api/status scheduler.running=true，store/scheduler.log 无 traceback，monitor-regression.sh 第6项 PASS"
  python3 -m bus send lingjian --data-dir store --from mailbus --type task --priority normal --msg "【Round2 R2-007】审查 Round2 代码/配置变更，写 audit 或 msg-results/iteration-r2-007.json"
  python3 -m bus send lingyan --data-dir store --from mailbus --type task --priority urgent --msg "【Round2 R2-008】跑 monitor-regression.sh + task-flow-snapshot.sh 回归验证"
  fi
fi

if [ "$DISPATCH" = "dispatch-r1" ]; then
  log "下发 Round1 执行任务给灵昭（不是 Round2）..."
  MSG="【iteration-r1-$(date +%Y%m%d)】请完成 Round1，不要触发 Round2。

阅读：
- store/iterations/round-1-diagnosis.json
- store/iterations/round-1-gate.json
- store/rules/iteration-protocol.md

Round1 完成标准（全部满足后才允许 Round2）：
1. 主任务 mailbus-hardening-20260616 status=success
2. 灵鉴写入 audit_log（pass 或 warn）

你的动作：推进 hardening pipeline → 写 msg-results → 通知灵鉴审计。
⚠️ 禁止在 Round1 未通过时运行 bus iteration --round 2"

  python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"
fi

log "=== done (exit $rc) ==="
exit "$rc"
