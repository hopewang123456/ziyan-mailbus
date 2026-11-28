/**
 * 外部 Agent A2A 接入提示词（与 docs/design/agent-onboarding-template.md 对齐）。
 *
 * 在「Agents 页 → 创建 Agent 邀请码」抽屉中展示，便于新 Agent 接入时直接复制，
 * 无需另找文档。运行期自动注入 mailbus 基址与本次邀请码。
 */
export interface A2aOnboardingOptions {
  /** mailbus 基址，例如 https://mailbus.example.com */
  mailbusBase: string;
  /** 一次性邀请码（注册后即失效） */
  inviteCode: string;
}

export function buildA2aOnboardingPrompt({
  mailbusBase,
  inviteCode,
}: A2aOnboardingOptions): string {
  const base = mailbusBase || "https://<mailbus 基址>";
  return `# Mailbus A2A 接入说明（外部 Agent）

你是接入 Mailbus 多智能体总线的外部 Agent。请严格按本说明实现，不要自行扩展协议。

mailbus 基址：${base}
一次性邀请码：${inviteCode}

## 0. 登记（仅一次）

POST ${base}/api/agents/register
Content-Type: application/json

{
  "invite_code": "${inviteCode}",
  "name": "你的名字",
  "framework": "hermes | codex | openclaw | claude_code | opencode | 其他",
  "model": "deepseek-v4",
  "endpoint": "http://<可从 mailbus 访问的地址>/a2a",
  "health_url": "http://<同上>/a2a/health"
}

成功响应（仅此一次，务必保存 endpoint_token，勿写日志/勿提交仓库）：
  agent_id / employee_id / endpoint_token

- 岗位、capabilities、permissions、data_scope 全部由邀请码决定，请求体不能自行提权
- 邀请码一次性；已用 409，已撤销/过期 410
- 提交的 endpoint 进入「待审批」：审批前可心跳，但 mailbus 暂停派单；审批通过且健康检查成功后才恢复
- 注册成功后 30 秒内必须发出首次心跳，否则按离线处理

## 1. 你要做什么

1. 暴露 POST {endpoint} 接收 task_assignment；提供 GET {endpoint}/health 返回 {"status":"ok"}
2. 收到任务后立即回 ack（受理确认），再异步执行
3. 执行完成后调用 POST ${base}/api/a2a/messages 回推 result
4. 每 30 秒发送一次 heartbeat，并回传当前可访问的 endpoint
5. 任务涉及文件时，按第 6 节读取/上传产物

执行循环：
  on POST {endpoint}:
      verify Authorization: Bearer <endpoint_token>
      if 已见过 idempotency_key: return 200（忽略重复投递）
      立即 ack(message_id)
      异步执行任务
      return 202
  worker(task):
      执行 task.prompt，产出 output 与 artifacts
      回推 result(run_id, attempt_no, status, output, artifacts)

## 2. 你不做什么

- 不发现、不枚举其他 Agent；不直连其他 Agent
- 不创建工作流、不决定下一个节点、不推进任务状态
- 不自行重试投递（mailbus 的 Outbox 负责重试）
- 不轮询任务（pull_only 模式除外）
- 不修改任务归属、优先级、超时等引擎字段

## 3. 鉴权

- 所有请求带 Authorization: Bearer <endpoint_token>
- agent_id 由 token 反查，不要在 body 里自报
- mailbus → 你 的投递同样带 Authorization: Bearer <endpoint_token>
- Content-Type: application/json（产物上传除外）
- token 不得出现在 URL、日志、异常堆栈里

## 4. 回调协议

### 4.1 接收 task_assignment（mailbus → POST {endpoint}）

{
  "message_id": "mb_<uuid>",
  "message_type": "task_assignment",
  "sent_at": "2026-11-24T14:00:00Z",
  "idempotency_key": "ia_<run_id>",
  "task": {
    "task_id": "task_<uuid>",
    "run_id": "run_<uuid>",
    "attempt_no": 1,
    "node_id": "node_x",
    "node_title": "节点标题",
    "prompt": "任务正文",
    "context": {
      "previous_result": "上游结果",
      "variables": {},
      "artifacts": [
        {"artifact_id": "art_1", "file_name": "需求.md", "download_url": "https://..."}
      ]
    },
    "workspace_dir": "<本地 Agent 才有>",
    "deadline": null,
    "priority": "normal",
    "artifact_upload_url": "https://.../a2a/artifacts/upload?exp=...&sig=..."
  }
}

- 必须按 run_id 隔离执行；同一节点的多次执行是不同 run_id
- download_url 仅外部 Agent 有；workspace_dir 仅本地 Agent 有
- 同一 idempotency_key 只执行一次

### 4.2 回 ack（收到即回，不要等执行完）

POST ${base}/api/a2a/messages
{"type": "ack", "message_id": "mb_<uuid>", "accepted": true}

### 4.3 回推 result

POST ${base}/api/a2a/messages
{
  "type": "result",
  "run_id": "run_<uuid>",
  "attempt_no": 1,
  "status": "completed",
  "output": "文本，或可解析的 JSON 字符串",
  "artifacts": [
    {"type": "path", "file_path": "01_result.md", "file_name": "结果.md"},
    {"type": "artifact", "artifact_id": "art_report", "file_name": "report.pdf"}
  ],
  "completed_at": "2026-11-24T14:03:22Z"
}

status：completed / failed / needs_human / needs_info / rejected

- run_id 与 attempt_no 必填；缺失返回 400 E_RESULT_IDENTITY_MISSING
- 只有当前活跃 run 的结果会被接受；旧 attempt 返回 409 stale_run，不要再重试
- 完全相同的 result 重复提交返回 200，引擎不会重复推进
- output 建议用 JSON 字符串，便于下游按 result.* 取字段

### 4.4 心跳（每 30 秒）

POST ${base}/api/a2a/messages
{"type": "heartbeat", "endpoint": "http://<你的地址>/a2a", "pending_tasks": 0}

- endpoint 用于动态发现；新 endpoint 需管理员审批才恢复派单
- 连续 90 秒无心跳 → 判离线；离线后再宽限 90 秒，在跑 run 判失败并重派
- 收到 task_cancel 后停止执行并回 result(status="failed")，output 写「已取消」

## 5. 错误处理与幂等

  你的响应             mailbus 行为
  200 / 202            成功，停止重试
  400 / 401 / 403 / 404 不重试，run failed
  409                  幂等命中，不重试
  422                  能力不匹配，换人
  429 / 5xx / 网络错误  指数退避重试（最长 10 分钟）

不要自己实现重试；重复投递靠 idempotency_key / run_id 去重。

## 6. 产物读写

本地 Agent（workspace_dir 存在）：
- 直接读写 workspace_dir 下文件
- result 里用 {"type": "path", "file_path": "相对 workspace 的路径"} 声明产物

外部 Agent（无 workspace_dir）：
- 读取：使用 context.artifacts[].download_url（有限期）
- 上传：PUT {artifact_upload_url}，body 为文件二进制；一次性 URL，24 小时有效，单文件 ≤100MB
- 上传成功返回 {"artifact_id":"art_..."}，在 result 中用 {"type":"artifact","artifact_id":"art_..."}
- 小文件可在 result 中内联：artifacts_inline（单文件 ≤5MB、总计 ≤10MB）
- 不支持在 result 中用 type=url 让 mailbus 抓取任意外部地址

## 7. 接入自检清单

1. GET {endpoint}/health 返回 200
2. 注册后控制台显示 endpoint 待审批；审批前无新任务，审批后恢复
3. 启动后 30 秒内控制台显示在线且 last_seen_at 更新
4. 收到 task_assignment 后 5 秒内回 ack
5. result 带 run_id 与 attempt_no，被接受并推进节点
6. 同一 idempotency_key 重投只执行一次
7. 旧 attempt 的 result 返回 409，且不改变任务状态
8. 本地 Agent 能写 workspace_dir；外部 Agent 上传后拿到 artifact_id 并在 result 引用
9. 杀掉进程 90 秒后控制台显示离线；按已审批 endpoint 恢复后自动回在线
10. heartbeat 上报新 endpoint 后进入待审批，未经审批不会向新地址派单
`;
}
