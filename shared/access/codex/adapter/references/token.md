# Codex — Token

- `--ephemeral`：不依赖上轮上下文，关键信息写 msg-results
- `--json` 输出：解析后只保留必要字段再写文件
- skills 从 `CODEX_HOME/skills` 按需加载
- auto_compact_token_limit ~96000（catalog 配置）；大 repo 先 narrow scope
- push 正文短；长工单在 msg-files
