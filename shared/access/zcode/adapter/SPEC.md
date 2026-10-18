# zcode adapter SPEC

## What

`zcode` = ZCode 桌面应用自带的 agent CLI 运行时（`node <app>/resources/glm/zcode.cjs`），
以 headless 模式（`-p '<msg>' --mode yolo`）接入 mailbus，GLM 为内置后端（Z.AI OAuth）。

## Contract

- **宿主 only**：非 Docker；容器内 scan 无 node/zcode → direct 返回 None → 消息留
  pending，由宿主 scan（计划任务 `mailbus-host-scan` 每 5 分钟）补推。
- **隔离**：`ZCODE_HOME=~/.zcode-<agent>` per-agent（实测 OAuth 认证跟随，不随
  HOME 丢失；会话/记忆按 agent 隔离，与桌面 app 的 ~/.zcode 互不干扰）。
- **推送**：direct argv 优先（`direct_push._zcode_direct` → Popen，无 shell 转义面）；
  shell 模板仅 fallback。权限模式 `zcode.mode`（默认 yolo，无人值守语义）。
- **model**：GLM 内置，无 model flag；`models: ["glm"]` 占位。
- **活性**：`host_cli_active` 正则匹配进程表 `zcode(.cjs|.cmd)? ... -p`。

## Files

- `lib/adapters/frameworks/zcode_launch.py` — 全部 zcode 逻辑（home/cli 解析、
  push argv、shell 模板、活性检测）
- `lib/adapters/frameworks/registry.py` — `ZcodeAdapter` + `ADAPTERS["zcode"]`
- `lib/adapters/frameworks/direct_push.py` — `_zcode_direct` 分支
- config 触点：config_schema（AGENT_TYPES/allowed）、access_adapters、config_admin、
  init_store、native_scan（identity=AGENTS.md）、file_task_push、agent-types.json

## Platform config（store/config.json `mailbus_zcode`，可选）

```json
"mailbus_zcode": {
  "windows": {
    "zcode_cjs": "D:\\Zcode\\resources\\glm\\zcode.cjs",
    "node": "E:\\nodejs\\node.EXE",
    "homes": {"lingzhu": "E:\\ai_tools\\Agent\\zcode\\homes\\.zcode-lingzhu"}
  }
}
```

全部可选：缺省用内置 bundle 候选路径 + `~/.zcode-<agent>`。

## 编制内实例

- **灵枢 lingzhu**（coding-executor）：不进 stations.candidates，task pin 指派才接活。
