# OpenCode — 能力边界

## 能做

- 微信小程序、TDD、单元测试、git patch 交付
- 文件读写、shell（`--dangerously-skip-permissions`）
- workspace：`/workspace/opencode` + mailbus store

## 不能做

- auto_ack（adapter 层禁止）
- 替代 lingyun 的超大跨仓库 refactor（应改派 pro）
- 修改 mailbus 规则/adapter（除非工单明确）

## 会话

- **无 mailbus 续聊**：每条 push 独立 `opencode run`
- 交互调试：`opencode` TUI（launch 用，非 push）

## 队友

- 大壮（Aider）：替补 review → `opencode/message-dali-dazhuang.md`
