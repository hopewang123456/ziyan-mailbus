# 推送纪律（省 token）

来源：[`mail/rules/model-routing.md`](../../../../rules/model-routing.md)

## CLI 字符上限

| 键 | 默认 | 说明 |
|----|------|------|
| `cli_msg_max_chars` | 600 | 单条 push 正文 |
| `cli_combined_max_chars` | 4000 | 整包上限 |
| `summary_max_chars` | 200 | pipeline 每步 summary |

## 写消息时

1. 正文只写 **task_id / msg_id + 文件路径**
2. 方案、工单、验收清单 → `store/tasks/` 或 `store/msg-files/`
3. 结果细节 → `msg-results` 的 `details` 或独立 md

## 不调用 LLM（零 token）

- `notice-*`、`heartbeat-*`、`patrol-*`、`remind-*` 等系统前缀
- `action.no_llm: true`
- 详见 model-routing.md「不调用 LLM」节

## 模型档位

- 默认 **flash**（deepseek-chat）
- Pro 需：`action.model_tier: pro` + `MAILBUS_ALLOW_PRO=1` + agent 装备 pro 模型

## Agent 侧省 token

- 先 `memory.py search` / AgentMemory，再动手
- Skill：**按需 Read** references，不要一次加载全部
- 不重复读取 AGENTS.md / CLAUDE.md（sync 已注入）
- OpenClaw：`HEARTBEAT.md` 保持短小

## 编码分工

- **Cursor 直连**：重编码、大 refactor
- **mailbus push**：流转、验收、跨 agent 协作
