# OpenCode — Token

- push 正文 ≤600 字；工单在 msg-files
- 一次 `opencode run` = 一轮，规划在 run 内完成
- 少读大文件：先 Glob/Grep 定位再 Read
- 不重复读 AGENTS.md（已注入）；framework skill 按需读 references
- pipeline push timeout 可达 900s，但仍应分步 commit 便于 review
