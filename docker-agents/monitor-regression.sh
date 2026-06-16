#!/bin/bash
# 回归监控：服务健康 + 工作流任务链 + OpenClaw 身份
set -uo pipefail

BASE="http://127.0.0.1:9812"
PASS=0
FAIL=0
WARN=0

log()  { echo "[monitor] $*"; }
pass() { PASS=$((PASS+1)); log "PASS: $*"; }
fail() { FAIL=$((FAIL+1)); log "FAIL: $*"; }
warn() { WARN=$((WARN+1)); log "WARN: $*"; }

check_http() {
  local name="$1" url="$2" expect="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null || echo "000")
  if [ "$code" = "$expect" ]; then pass "$name HTTP $code"; else fail "$name HTTP $code (expect $expect)"; fi
}

log "========== 1. 服务健康 =========="
check_http mailbus    "$BASE/"
check_http openclaw-xiaoqi "http://127.0.0.1:18789/"
check_http openclaw-yige   "http://127.0.0.1:18790/"
check_http hermes-lingzhao "http://127.0.0.1:9120/chat"

log "========== 2. Docker 容器 =========="
running=$(docker ps --filter "name=docker-agents" --format "{{.Names}}" 2>/dev/null | wc -l)
if [ "$running" -ge 6 ]; then pass "containers running: $running"; else fail "containers running: $running (expect >=6)"; fi
docker ps --filter "name=docker-agents" --format "  {{.Names}} {{.Status}}" 2>/dev/null | head -10

log "========== 3. OpenClaw 身份配置 =========="
for pair in "xiaoqi:18789" "yige:18790"; do
  profile="${pair%%:*}"
  port="${pair##*:}"
  statedir="/workspace/data/.openclaw-${profile}"
  aid=$(docker exec docker-agents-openclaw-1 python3 -c "
import json, os
p='${statedir}/openclaw.json'
if not os.path.exists(p): print('MISSING'); exit()
d=json.load(open(p))
ids=[a.get('id') for a in d.get('agents',{}).get('list',[])]
print(','.join(ids) if ids else 'EMPTY')
" 2>/dev/null || echo "ERR")
  if [ "$aid" = "$profile" ]; then pass "openclaw ${port} agent.id=$profile"; else fail "openclaw ${port} agent.id=$aid (expect $profile)"; fi
done

log "========== 4. Hermes 灵昭身份 =========="
reply=$(docker exec docker-agents-hermes-1 hermes chat -Q -q "你是谁，一句话介绍" --profile lingzhao 2>&1 | tail -8 || true)
if echo "$reply" | grep -qiE "灵昭|方案设计"; then pass "hermes lingzhao identity OK"; else warn "hermes lingzhao: ${reply:0:150}"; fi

log "========== 5. 工作流任务链 =========="
curl -s --connect-timeout 5 "${BASE}/api/tasks" -o /tmp/monitor-tasks.json 2>/dev/null || echo '{"tasks":[]}' > /tmp/monitor-tasks.json
python3 <<'PY'
import json
try:
    d = json.load(open("/tmp/monitor-tasks.json"))
except Exception as e:
    print(f"  WARN: tasks API parse error: {e}")
    raise SystemExit(0)
tasks = [t for t in d.get("tasks", []) if str(t.get("task_id", "")).startswith("game-lvup")]
if not tasks:
    print("  WARN: no game-lvup tasks found")
else:
    for t in sorted(tasks, key=lambda x: x.get("created_at",""))[-3:]:
        print(f"  task={t['task_id']} assignee={t.get('assignee')} status={t.get('status')}")
PY

log "========== 6. 内置 scheduler =========="
curl -s --connect-timeout 5 "${BASE}/api/status" -o /tmp/monitor-status.json 2>/dev/null || echo '{}' > /tmp/monitor-status.json
python3 <<'PY'
import json, sys
try:
    d = json.load(open("/tmp/monitor-status.json"))
except Exception:
    d = {}
sched = d.get("scheduler") or {}
if sched.get("running"):
    jobs = sched.get("jobs") or {}
    scan = jobs.get("scan") or {}
    if scan.get("last_run_iso"):
        print(f"  scan last={scan.get('last_run_iso')} rc={scan.get('last_rc')}")
        sys.exit(0)
    print("  WARN: scheduler running but scan not yet executed")
    sys.exit(0)
print("  scheduler not running")
sys.exit(1)
PY
if [ $? -eq 0 ]; then pass "mailbus built-in scheduler"; else fail "mailbus scheduler inactive"; fi

log "========== 7. mailbus 最近日志 =========="
docker logs docker-agents-mailbus-1 --tail 8 2>&1 | head -8 | while read -r line; do echo "  $line"; done

log "========== SUMMARY: PASS=$PASS FAIL=$FAIL WARN=$WARN =========="
[ "$FAIL" -eq 0 ]
