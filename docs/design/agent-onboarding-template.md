# Agent 接入模板（A2a 标准接入）

> 版本 v1.1 · 2026-11-24（最终接入契约）
> 配套：[agent-unification-design.md](./agent-unification-design.md) 第 5 章 A2a 协议、第 8 章引导模板
> 用途：把本文件交给任一 Agent（或粘贴为 system_prompt / Skill），让它按统一标准接入 mailbus。
> 使用前替换：`{MAILBUS_BASE}`、`{ENDPOINT_TOKEN}`、`{AGENT_ID}`。

---

## 0. 登记（邀请码自助注册）

1. 向管理员索取**一次性邀请码**（控制台生成，含岗位、业务技能、权限、data_scope、有效期；明文只展示一次）。
2. 调用注册接口：

```
POST {MAILBUS_BASE}/api/agents/register
Content-Type: application/json

{
  "invite_code": "mbreg_...",
  "name": "灵昭",
  "framework": "hermes",
  "model": "deepseek-v4",
  "endpoint": "http://192.168.1.100:7890/a2a",
  "health_url": "http://192.168.1.100:7890/a2a/health"
}
```

3. 成功响应（仅此一次，务必保存）：

```json
{
  "agent_id": "agent_...",
  "employee_id": "emp_...",
  "endpoint_token": "mbk_...",
  "agent_type": "external",
  "channel_type": "a2a",
  "endpoint_review_status": "pending"
}
```

- 岗位、业务技能 `capabilities`、权限 `permissions`、`data_scope` 全部来自邀请码，**请求体不能自行提权**
- 邀请码一次性，用后即废；默认长期有效，管理员可随时作废；已用返回 409，已撤销/过期返回 410
- `endpoint_token` 不要写进日志、不要提交到仓库；明文只在注册/轮转成功时返回一次，丢失只能由管理员轮转
- 注册提交的 `endpoint` 进入**待审批**状态；管理员审批前可以心跳，但 mailbus 暂停新任务投递
- 注册成功后 30 秒内必须发出首次心跳，否则按离线处理；endpoint 审批通过且健康检查成功后才恢复派单
- 注册记录长期保留，不因离线或长时间无心跳被自动删除；只有管理员在协同端删除才会移除

---

## 1. 你要做什么

1. 在 `{endpoint}` 暴露一个 HTTP 入口，接收 mailbus 推送的 `task_assignment`
2. 收到后**立即**回 `ack`（受理确认），再异步执行任务
3. 执行完成后，调用 `POST {MAILBUS_BASE}/api/a2a/messages` 回推 `result`
4. 每 30 秒发送一次 `heartbeat`，并回传当前可访问的 `endpoint`
5. 任务涉及文件时，按第 6 节读取/上传产物

执行循环（伪代码）：

```
on POST {endpoint}:
    verify Bearer == {ENDPOINT_TOKEN}
    if idempotency_key seen: return 200 (忽略重复投递)
    ack(message_id)
    enqueue(task)
    return 202

worker(task):
    run_id     = task.run_id
    attempt_no = task.attempt_no
    try:
        output, files = execute(task.prompt, task.context)
        post_result(run_id, attempt_no, "completed", output, files)
    except NeedHuman as e:
        post_result(run_id, attempt_no, "needs_human", str(e))
    except Exception as e:
        post_result(run_id, attempt_no, "failed", str(e))
```

---

## 2. 你不做什么

- 不发现、不枚举其他 Agent；不直连别的 Agent
- 不创建工作流、不决定下一个节点、不推进任务状态
- 不自行重试投递失败（mailbus 的 Outbox 负责重试）
- 不轮询任务（`service` 模式）；只有 `pull_only` 才通过 MCP 拉取
- 不修改任务归属、优先级、超时等引擎字段

---

## 3. 连接信息与鉴权

| 项 | 值 |
|---|---|
| mailbus 基址 | `{MAILBUS_BASE}` |
| 回调入口 | `POST {MAILBUS_BASE}/api/a2a/messages` |
| 你的接收入口 | `{endpoint}`（需可从 mailbus 访问） |
| 鉴权 | `Authorization: Bearer {ENDPOINT_TOKEN}` |
| agent_id | 由 token 反查，**不要**在 body 里自报 |

- mailbus → 你：同样带 `Authorization: Bearer {ENDPOINT_TOKEN}`
- 所有请求 `Content-Type: application/json`（产物上传除外，见第 6 节）
- 用 HTTPS 或内网可信网络；token 不得出现在 URL、日志、异常堆栈里

---

## 4. 回调协议

### 4.1 接收 task_assignment

mailbus 会向 `{endpoint}` POST：

```json
{
  "message_id": "mb_<uuid>",
  "message_type": "task_assignment",
  "sent_at": "2026-11-24T14:00:00Z",
  "idempotency_key": "ia_<run_id>",
  "task": {
    "task_id": "task_<uuid>",
    "run_id": "run_<uuid>",
    "attempt_no": 1,
    "node_id": "node_market",
    "node_title": "市场研究",
    "position": "产品经理",
    "role": {"role_id": "role_comp", "role_name": "竞品分析", "capabilities": ["competition_analysis"]},
    "employee_id": "emp_lingzhao",
    "prompt": "分析竞争对手...",
    "context": {
      "previous_result": "...",
      "variables": {"market": "智能硬件"},
      "artifacts": [
        {"artifact_id": "art_1", "file_path": "01_node_req_lingzhao.md", "file_name": "需求.md",
         "description": "需求文档", "created_by": "emp_lingzhao",
         "download_url": "https://.../artifacts/art_1"}
      ]
    },
    "workspace_dir": "<本地绝对路径，仅本地 Agent>",
    "deadline": null,
    "priority": "normal",
    "artifact_upload_url": "https://.../a2a/artifacts/upload?exp=...&sig=..."
  }
}
```

约定：

- 必须按 `run_id` 隔离执行；同一节点的多次执行是不同 `run_id`
- `download_url` 仅外部 Agent 有；`workspace_dir` 仅本地 Agent 有
- `artifact_upload_url` 可能为空；需要上传时按第 6 节使用
- 同一 `idempotency_key` 只执行一次

### 4.2 回 ack

```json
{"type": "ack", "message_id": "mb_<uuid>", "accepted": true}
```

`POST {MAILBUS_BASE}/api/a2a/messages`，收到即回，不要等任务执行完。

### 4.3 回推 result

```json
{
  "type": "result",
  "run_id": "run_<uuid>",
  "attempt_no": 1,
  "status": "completed",
  "output": "文本，或可解析的 JSON 字符串",
  "artifacts": [
    {"type": "path", "file_path": "02_compete_lingjin.md", "file_name": "竞品分析.md", "description": "..."},
    {"type": "artifact", "artifact_id": "art_report", "file_name": "report.pdf", "description": "已通过签名 URL 上传"}
  ],
  "completed_at": "2026-11-24T14:03:22Z"
}
```

`status` 取值：

| status | 含义 | 后续 |
|---|---|---|
| `completed` | 正常完成 | 引擎推进下一节点 |
| `failed` | 执行失败 | 按 `max_retries` 换人重派 |
| `needs_human` | 需要人决策 | 转人工处理 |
| `needs_info` | 缺少输入 | 转人工补充 |
| `rejected` | 明确拒绝执行 | 转人工 |

- `run_id` 与 `attempt_no` **必填**；缺失返回 400 `E_RESULT_IDENTITY_MISSING`
- 只有当前活跃 run 的结果会被接受；旧 attempt 返回 409 `stale_run`，**不要再重试**
- 完全相同的 result 重复提交返回 200，引擎不会重复推进
- `output` 建议用 JSON 字符串，便于下游条件规则取 `result.*` 字段

### 4.4 心跳

每 30 秒：

```json
{"type": "heartbeat", "endpoint": "http://192.168.1.100:7890/a2a", "pending_tasks": 0}
```

- `endpoint` 用于动态发现：容器 IP、端口变化后由心跳上报新地址
- **新 endpoint 必须经管理员审批才恢复新任务投递**；心跳只会把它标记为待审批，不代表地址已生效
- 连续 90 秒无心跳 → mailbus 判离线；离线后再宽限 90 秒，仍未恢复则在跑 run 判失败并重派
- 收到 `task_cancel` 后停止执行并回 `result(status="failed")`，`output` 写「已取消」

---

## 5. 错误处理与幂等

| 你的响应 | mailbus 行为 |
|---|---|
| 200 / 202 | 成功，停止重试 |
| 400 / 401 / 403 / 404 | 不重试，run failed |
| 409 | 视为幂等命中，不重试 |
| 422 | 能力不匹配，换人 |
| 429 / 5xx / 网络错误 | 指数退避重试（最长 10 分钟） |

- 不要自己实现重试；重复投递靠 `idempotency_key` / `run_id` 去重
- 长任务建议每 10 分钟写一次日志到 `workspace_dir/logs/`（若存在）
- 不要在失败时删除已有产物；重试会新建 attempt，旧产物由 mailbus 管理

---

## 6. 产物读写

### 本地 Agent（`workspace_dir` 存在）

- 直接读写 `{workspace_dir}` 下的文件
- 建议命名：`<序号>_<节点名>_<员工>.<扩展名>`
- result 里用 `{"type": "path", "file_path": "相对 workspace 的路径"}` 声明产物

### 外部 Agent（无 `workspace_dir`）

- 读取：使用 `context.artifacts[].download_url`（有限期，过期由 mailbus 重新投递时刷新）
- 上传：`PUT {artifact_upload_url}`，body 为文件二进制，`Content-Type` 用文件实际类型
  - 一次性 URL，24 小时有效，单文件 ≤100MB；用后即废
  - 上传成功返回 200 与 `{"artifact_id":"art_..."}`；保存该 ID，并在 result 中用 `{"type":"artifact","artifact_id":"art_..."}` 引用
  - 过期/签名错误返回 401/403，需重新拉取任务获取新 URL
  - 不支持在 result 中用 `type=url` 让 mailbus 抓取任意外部地址
- 小文件兜底：可在 result 中内联

```json
"artifacts_inline": [
  {"name": "summary.md", "mime": "text/markdown", "base64": "..."}
]
```

单文件 ≤5MB、总计 ≤10MB，超限返回 413。

---

## 7. endpoint 与健康检查

- 暴露 `GET {endpoint}/health`，返回 `{"status": "ok"}`（可带 `agent_id`、版本）
- 启动后 60 秒内必须可访问，否则 mailbus 按离线处理
- URL 支持固定 IP、容器名、`${ENV}` 占位与域名；端口变化用心跳回传，变更后等待管理员审批
- mailbus 会在注册、审批和投递前校验 URL、DNS 解析、云元数据地址和可信网段；不要配置未经批准的内网/元数据地址或用重定向绕过
- `pull_only` 模式不需要对 mailbus 暴露 endpoint，改用 MCP 拉取（见第 10 节）

---

## 8. Token 轮转与吊销

- 管理员手动轮转 token，旧 token 宽限 24 小时，期间两者都可用
- 被吊销立即失效，下一个请求即 401；不要缓存旧 token 长期使用
- 收到 401 时停止重试并告警，等待管理员更新配置

---

## 9. 接入自检清单

1. `GET {endpoint}/health` 返回 200
2. 注册后控制台显示 endpoint 待审批；管理员审批前没有新任务投递，审批后恢复
3. 启动后 30 秒内，控制台看到在线 + `last_seen_at` 更新
4. 收到 `task_assignment` 后 5 秒内回 `ack`
5. `result` 带 `run_id` 与 `attempt_no`，被接受并推进节点
6. 同一 `idempotency_key` 重投只执行一次
7. 旧 attempt 的 result 返回 409，且不改变任务状态
8. 本地 Agent 能在 `workspace_dir` 写文件；外部 Agent PUT 上传后拿到 `artifact_id` 并在 result 中引用
9. 杀掉进程 90 秒后控制台显示离线；以**已审批的原 endpoint** 恢复后自动回在线
10. heartbeat 上报新 endpoint 后进入待审批，未经审批不会向新地址派发任务

---

## 10. 各框架派生

### 10.1 hermes（skill / rule）

把本文件转成 `skills/mailbus-a2a/SKILL.md`，保留：登记信息、回调入口、task_assignment/result/heartbeat 三个 schema、幂等与错误码。执行器负责起 HTTP 服务并调度任务。

### 10.2 Trae / Cursor（MCP）

```json
{
  "mcpServers": {
    "mailbus": {
      "url": "{MAILBUS_BASE}/api/mcp",
      "headers": {"Authorization": "Bearer {ENDPOINT_TOKEN}"}
    }
  }
}
```

只保留 4 个工具：`mailbus_inbox`（拉待办）、`mailbus_send`（发消息）、`mailbus_ack`（受理）、`mailbus_result`（回结果）。旧 12 个工具已下线，调用会返回 404。

### 10.3 豆包（system_prompt）

把本文件第 1–6 节粘贴为 system_prompt，并追加：

```
你无法主动发 HTTP 请求。每次任务只输出一个 JSON 代码块，
字段严格遵循 result schema（run_id / attempt_no / status / output / artifacts_inline），
由接入层转发到 {MAILBUS_BASE}/api/a2a/messages。
不要输出解释性文字以外的任何格式。
```

### 10.4 元宝（Skill.md）

与本文件同构，增加一段「能力声明」：

```
capabilities: [competition_analysis, market_research]
```

管理员据此在角色里绑定对应 capability；未绑定的能力不会被派单。

### 10.5 pull_only（只能主动拉取）

- 不暴露 endpoint；通过 MCP `mailbus_inbox` 每 30 秒拉一次
- 拉到任务先 `mailbus_ack`，完成后 `mailbus_result`
- 心跳由拉取行为隐式产生（最近拉取时间即在线依据），超过阈值判离线
