# A2A 双栈对角对拍 Runbook（D13-③ / AA6）

- 日期：2026-10-27（M2d-a 验证流程固化）
- 适用：python ↔ java 互为 client/server 的 A2A 协议面对拍（JSON-RPC SendMessage / GetTask / CancelTask）
- 前置：JDK 25（`D:\jdk-25.0.4.1+1`）、Python 3.12+、mailbus 仓

## 1. 准备双 smoke store（不污染真实 store）

```bash
cd /e/ai_tools/mailbus
for S in .diag-java .diag-py; do
  mkdir -p $S/roles/json $S/tasks
done
mkdir -p .diag-java/inbox/agentA .diag-py/inbox/agentX

# java 侧 store（java agents 配置无 type 要求）
cat > .diag-java/config.json <<'EOF'
{"agents": {"agentA": {"type": "cli"}}, "dispatch": {"load_aware": true, "default_concurrency": 1}}
EOF

# python 侧 store（agents 必须有 type；本机写免 token）
cat > .diag-py/config.json <<'EOF'
{"agents": {"agentX": {"type": "cli"}}, "dispatch": {"load_aware": true, "default_concurrency": 1},
 "auth": {"allow_write_without_token": true}}
EOF

# 两边同一份职位表（候选各自指向本侧 agent）
cat > .diag-java/roles/json/role-types.json <<'EOF'
{"roles": {"1": {"key": "designer", "display": {"zh": "方案设计师"}, "candidates": ["agentA"]}}}
EOF
sed 's/agentA/agentX/' .diag-java/roles/json/role-types.json > .diag-py/roles/json/role-types.json
```

## 2. 起双 serve（python 用 9816——9814 常有真实实例占用）

```bash
# java（先 install：-pl run 不带 -am 用本地仓依赖）
cd java && JAVA_HOME=/d/jdk-25.0.4.1+1 mvn -q install -DskipTests
JAVA_HOME=/d/jdk-25.0.4.1+1 mvn -q -pl mailbus-boot spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9815 --mailbus.data-dir=E:/ai_tools/mailbus/.diag-java --mailbus.storage=memory --mailbus.task-scan.enabled=false" &

# python（--token 参数不进写鉴权链，用 config auth 免本机 token）
cd python && python -m bus serve --data-dir ../.diag-py --port 9816 &
```

健康探测：`curl http://127.0.0.1:9815/actuator/health` / `curl http://127.0.0.1:9816/api/status`

## 3. 对角 A：python-client 形状 → java server

```bash
cat > .diag-java/rpc.json <<'EOF'
{"jsonrpc":"2.0","id":"diag-a-1","method":"SendMessage","params":{"message":{"messageId":"m-1","role":"ROLE_USER","parts":[{"text":"对角冒烟：外部 A2A 需求"}],"metadata":{"mailbus":{"taskId":"ext-diag-java-1","planned_chain":[{"role_type":1}]}}}}}
EOF
curl -s -X POST -H "Content-Type: application/json" --data-binary @.diag-java/rpc.json \
  http://127.0.0.1:9815/api/a2a/rpc/agentA
```

预期：`result.task = {id:"ext-diag-java-1", status:"working", metadata.mailbus{taskId,stepId:s1}}`；
`.diag-java/tasks/ext-diag-java-1.json` 落盘（M 级默认待批 created/await_plan_approval）。

GetTask 富状态（M2d-b1）：`method:"GetTask", params:{"id":"ext-diag-java-1"}` →
`status:"input-required"` + `metadata.mailbus.hqType:"plan_approval"` + statusMessage「批准任务计划…」（与 python 富版同形）。

## 4. 对角 B：java-client 形状 → python server

```bash
cat > .diag-py/rpc.json <<'EOF'
{"jsonrpc":"2.0","id":"diag-b-1","method":"SendMessage","params":{"message":{"messageId":"m-2","role":"ROLE_USER","parts":[{"text":"对角冒烟：外部 A2A 需求"}],"metadata":{"mailbus":{"taskId":"ext-diag-py-1","planned_chain":[{"role_type":1}]}}}}}
EOF
curl -s -X POST -H "Content-Type: application/json" --data-binary @.diag-py/rpc.json \
  http://127.0.0.1:9816/api/a2a/rpc/agentX
```

预期：wire task 同形；`.diag-py/tasks/ext-diag-py-1.json` 落盘。
java 侧真实 client 为 `HttpA2AClient`（app 层，与 python `HttpA2AClient._rpc` 请求/错误分类逐字对齐，单测 `A2aRpcShapeTest` 已内嵌协议对拍）。

## 5. GetTask / CancelTask 对角

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"g1","method":"GetTask","params":{"id":"ext-diag-java-1"}}' \
  http://127.0.0.1:9815/api/a2a/rpc/agentA
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"c1","method":"CancelTask","params":{"id":"ext-diag-py-1"}}' \
  http://127.0.0.1:9816/api/a2a/rpc/agentX
```

状态映射（双侧同口径，M2d-b1 起 java 对齐 python）：pending hq（plan_approval/final_acceptance/a2a_input_required）或 accepting/blocked/paused → `input-required`；succeeded → `completed`；failed → `failed`；cancelled → `canceled`；其余 `working`。

## 6. 清理

```bash
# 停两个 serve 进程后：
rm -rf .diag-java .diag-py
```

## 已知边界（M2d-b 剩余）

- SendStreamingMessage/SSE：java 未实现（-32601），随 a2a-java SDK 深度集成落地
- a2a-java SDK 1.4.0.Final 集成（替换手写 JSON-RPC 面）待做
- 对角对拍进 CI 常态化（本 runbook 目前手动执行）
