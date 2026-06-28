# mailbus 外部工具（External Tools）

> **工具层，非编制。** Coze / Dify / n8n webhook 等在此注册；编制内 agent 通过 **grants + adapters** 按需调用。

## 目录结构

```
external-tools/
├── README.md                 # 本文件
├── registry.example.json     # 工具与 provider 注册表（复制为 registry.json）
├── grants.example.json       # agent → tool 授权（复制为 grants.json）
├── schema/
│   ├── registry.schema.json
│   └── adapter.schema.json
├── adapters/                 # 按 agent × tool 单独适配（输入映射、落盘路径等）
│   ├── lingtuo/
│   ├── lingzhang/
│   └── yige/
└── logs/                     # 调用日志（运行时写入，可挂载到 store）
```

容器内根路径：`/mailbus/external-tools/`（与 `store/` 同级）。

## 快速开始

1. 复制 `registry.example.json` → `registry.json`，填写 workflow_id / bot_id
2. 复制 `grants.example.json` → `grants.json`，调整授权
3. 在 `adapters/<agent>/<tool>.json` 编写该配对的字段映射
4. 环境变量：`DIFY_BASE_URL`、`DIFY_API_KEY`、`COZE_API_BASE`、`COZE_API_TOKEN` 等

## 检索（mailbus 内置）

- `mailbus search --scope catalog --query dify` — FTS 检索外部工具
- `mailbus search --scope all --query coze` — 消息 + 目录
- `GET /api/search?q=dify&scope=all` — 看板搜索
- `GET /api/external-tools` — 工具注册表与 agent 配对列表

每次 `bus scan` 会重建 catalog 索引（`search.db` 内 `catalog` 表）。

## 调用

```bash
python3 tools/tools/ops/external-tools-cli.py list --agent lingtuo
python3 tools/tools/ops/external-tools-cli.py invoke --agent lingtuo --tool dify-lead-enrich \
  --inputs '{"title":"test","intake_id":"intake-20260615-abc123"}' --dry-run
```

```python
from lib.external_tools import invoke_tool, list_adapters_for_agent

invoke_tool("/mailbus/store", agent_id="lingtuo", tool_id="dify-lead-enrich", inputs={...})
```

## 新增 agent × tool 配对

1. 在 `registry.json` 的 `tools[]` 注册 tool（若尚未存在）
2. 在 `grants.json` 给 agent 授权
3. **新建** `adapters/<agent_id>/<tool_id>.json`（必填，便于单独演进）
4. 在该 agent 的 `identities/*.md` 增加「外部工具」一节

## 原则

- 不把 Coze/Dify 注册进 `config.agents`
- 工具输出为中间产物；正式落盘仍走 agent 规则路径
- API key 只走 env，禁止写入 registry / adapter / identity
