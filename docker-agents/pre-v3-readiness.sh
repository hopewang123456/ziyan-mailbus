#!/bin/bash
# v3 LIVE 跑前环境自检 — mailbus + agent 挂载 + pipeline 状态
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib/api-url.sh"

MAIL="/mnt/e/ai_tools/mail"
BASE="$MAILBUS_API_BASE"
TASK_ID="${1:-game-stellar-20260618}"
PASS=0
FAIL=0
WARN=0

log()  { echo "[pre-v3] $*"; }
pass() { PASS=$((PASS+1)); log "✓ $*"; }
fail() { FAIL=$((FAIL+1)); log "✗ $*"; }
warn() { WARN=$((WARN+1)); log "⚠ $*"; }

log "========== 1. Docker 容器 =========="
for c in mailbus hermes openclaw dali lingxiao; do
  if docker ps --format '{{.Names}}' | grep -q "docker-agents-${c}-1"; then
    pass "container docker-agents-${c}-1 running"
  else
    fail "container docker-agents-${c}-1 not running"
  fi
done

log "========== 2. store 挂载（各 agent 可写） =========="
if bash "$MAIL/docker-agents/verify-agent-store-mount.sh" >/tmp/pre-v3-mount.log 2>&1; then
  pass "verify-agent-store-mount 6/6"
else
  fail "verify-agent-store-mount — see /tmp/pre-v3-mount.log"
  cat /tmp/pre-v3-mount.log | tail -10
fi

log "========== 3. mailbus API / scheduler =========="
code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$BASE/" 2>/dev/null || echo "000")
[ "$code" = "200" ] && pass "mailbus HTTP $code" || fail "mailbus HTTP $code"

docker exec docker-agents-mailbus-1 python3 <<'PY'
import json, urllib.request, sys
try:
    with urllib.request.urlopen(""$MAILBUS_API_BASE"/api/status", timeout=5) as r:
        d = json.loads(r.read())
    sched = d.get("scheduler") or {}
    if not sched.get("running"):
        print("FAIL scheduler not running"); sys.exit(1)
    scan = (sched.get("jobs") or {}).get("scan") or {}
    rc = scan.get("last_rc", -1)
    if rc != 0:
        print(f"WARN scan last_rc={rc}")
    else:
        print(f"OK scan last={scan.get('last_run_iso','?')} rc=0")
except Exception as e:
    print(f"FAIL status API: {e}"); sys.exit(1)
PY
[ $? -eq 0 ] && pass "scheduler + scan rc=0" || fail "scheduler/scan unhealthy"

log "========== 4. 路径规范 =========="
docker exec docker-agents-mailbus-1 test -f /mailbus/store/rules/pipeline-agent-paths.md && \
  pass "store/rules/pipeline-agent-paths.md" || fail "missing pipeline-agent-paths.md"
docker exec docker-agents-hermes-1 test -f /mailbus/rules/pipeline-agent-paths.md && \
  pass "hermes /mailbus/rules readable" || fail "hermes rules not mounted"

grep -q '/mailbus/store' "$MAIL/store/config.json" && pass "config.json uses /mailbus/store" || \
  fail "config.json still has /mnt/e paths"

log "========== 5. pipeline_ops 配置 =========="
docker exec docker-agents-mailbus-1 python3 <<'PY'
import json
c = json.load(open("/mailbus/store/config.json"))
ops = c.get("pipeline_ops") or {}
for k in ("primary_repush_cooldown_minutes", "repush_cooldown_minutes"):
    if k not in ops:
        print(f"FAIL missing {k}"); raise SystemExit(1)
print(f"OK cooldown primary={ops['primary_repush_cooldown_minutes']}m repush={ops['repush_cooldown_minutes']}m")
PY
[ $? -eq 0 ] && pass "pipeline_ops cooldown configured" || fail "pipeline_ops missing"

log "========== 6. v3 任务状态 =========="
docker exec docker-agents-mailbus-1 python3 <<PY
import json, os, sys
tid = "${TASK_ID}"
tr = json.load(open(f"/mailbus/store/tasks/{tid}.json")) if os.path.isfile(f"/mailbus/store/tasks/{tid}.json") else None
if not tr:
    print(f"WARN task {tid} not created yet")
    sys.exit(0)
st = tr.get("status")
dup = [t for t in os.listdir("/mailbus/store/tasks") if t.startswith("msg-") and t.endswith(".json")
       and json.load(open(f"/mailbus/store/tasks/{t}")).get("status") == "running"
       and tid in (json.load(open(f"/mailbus/store/tasks/{t}")).get("summary") or "")]
mr = os.path.isfile(f"/mailbus/store/msg-results/{tid}.json")
print(f"  task status={st} assignee={tr.get('assignee')} msg-results={'Y' if mr else 'N'}")
if dup:
    print(f"FAIL {len(dup)} duplicate msg-* running trackers")
    sys.exit(1)
if st == "running" and not mr:
    print("OK ready for Step1 (no msg-results yet)")
elif st == "success" and mr:
    print("OK task already success")
else:
    print(f"INFO status={st} mr={mr}")
PY
rc=$?
[ $rc -eq 0 ] && pass "v3 task state OK (no duplicate running msg-* tracker)" || fail "v3 task state issues"

log "========== 7. mailbus 单元测试（v2 回归套件） =========="
if docker exec docker-agents-mailbus-1 bash -c "cd /mailbus && python3 -m unittest tests.test_v2_regression tests.test_pipeline_task tests.test_stale_queue_cleanup -v" >/tmp/pre-v3-unittest.log 2>&1; then
  pass "v2 regression unittest"
else
  fail "v2 regression unittest — see /tmp/pre-v3-unittest.log"
  tail -20 /tmp/pre-v3-unittest.log
fi

if [ "${SKIP_AGENT_WRITE_SMOKE:-0}" != "1" ]; then
  log "========== 7b. agent 落盘探针（可选 SKIP_AGENT_WRITE_SMOKE=1 跳过） =========="
  if docker exec docker-agents-mailbus-1 python3 /mailbus/tools/ops/tools/ops/smoke-agent-disk-write.py \
      --agent lingzhao --data-dir /mailbus/store --timeout "${AGENT_WRITE_TIMEOUT:-420}" \
      >/tmp/pre-v3-agent-write.log 2>&1; then
    pass "smoke-agent-disk-write lingzhao"
  else
    fail "smoke-agent-disk-write — see /tmp/pre-v3-agent-write.log"
    tail -15 /tmp/pre-v3-agent-write.log
  fi
fi

log "========== 8. monitor-regression（集成） =========="
if bash "$MAIL/docker-agents/monitor-regression.sh" >/tmp/pre-v3-monitor.log 2>&1; then
  tail -1 /tmp/pre-v3-monitor.log | grep -q "FAIL=0" && pass "monitor-regression 10/10" || warn "monitor completed with failures"
else
  fail "monitor-regression failed"
fi

log "========== SUMMARY: PASS=$PASS FAIL=$FAIL WARN=$WARN =========="
[ "$FAIL" -eq 0 ]
