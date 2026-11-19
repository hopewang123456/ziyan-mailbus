# Runbook — Trae 通过 MCP 接入 mailbus

> D17 · 适用：Python 栈、Windows/Linux/WSL

mailbus 自带 MCP server，Trae（以及任何支持 MCP 的客户端：Claude Code、Cursor、Cline 等）
作为平级 agent 接入总线。角色（dispatcher / executor / reviewer）仍由 store 里的
agent 卡配置决定，与接入方式无关。

## 1. 前置：注册 agent

```bash
mailbus agent-add trae-1 --type trae
```

`type=trae` 的语义：MCP 拉模式、无 push CLI、无 auto_ack、交付 SoT 为 `msg-results`。

## 2. 在 Trae 里配置 MCP server

在 Trae 的 MCP 设置（项目级 `.trae/mcp.json` 或用户级 MCP 配置）中任选一种：

### python 栈（推荐，stdio）

```json
{
  "mcpServers": {
    "mailbus": {
      "command": "mailbus",
      "args": ["mcp", "--agent", "trae-1"]
    }
  }
}
```

需要非默认 store 时追加 `--data-dir /abs/path/to/store`。
Windows 下若 `mailbus` 不在 PATH，改 `command` 为 `python`，
`args` 改为 `["-m", "bus", "mcp", "--agent", "trae-1"]` 并设置 `PYTHONPATH` 指向 `mailbus/python`。

### python 栈（streamable HTTP，远程/多客户端）

```bash
mailbus mcp --agent trae-1 --transport http --host 127.0.0.1 --port 9816
```

Trae 侧配置 URL：`http://127.0.0.1:9816/mcp`

## 3. 验证

```bash
python tools/mcp_surface_diff.py --offline
```

Trae 会话内手工闭环：

1. `mailbus_inbox` → 应返回收件箱快照
2. `mailbus_send`（to=另一个 agent）→ 返回 `msg_id`
3. `mailbus_wait`（timeout_s=10）→ 有消息立即返回，否则 `status=timeout`
4. `mailbus_step_result`（真实工单）→ 落 `store/msg-results/{msg_id}.json`

## 4. 拉模式注意事项

MCP 客户端无法被总线 push。要让 Trae 及时处理任务，二者至少满足其一：

- Trae 侧规则/系统提示要求「会话开始先调 `mailbus_inbox`」
- 长任务用 `mailbus_wait` 轮询（≤60s，超时后重新调用）
- 配合 `mailbus serve` 的推送通道把工单同时投递到 Trae 的 inbox 文件（`file_task=True`）

## 5. 排障

| 现象 | 处理 |
|---|---|
| `agent 'x' 未在总线注册` | `mailbus agent-add x --type trae` |
| 工具列表里没有 `mailbus_config_get` | 正常：管理面默认不注册，需 `--enable-admin` |
| 写操作被鉴权拒绝 | MCP server 会自行解析 store token；确认 store 的 token 文件可读，或配 `auth.allow_write_without_token` + loopback |
| 端口冲突（HTTP 形态） | 换 `--port` |

## 6. 边界

- 管理类写工具（agent-add / 改配置）在 D17 只保留只读 `mailbus_config_get`；写管理能力与细粒度权限点在 D20 统一收口。
- MCP 工具面唯一 SoT：`shared/contracts/mcp-tools-v0.json`。新增工具先改契约，再改实现。
