# Quality Harness — deploy-hooks 运行手册

> 批量把 post-commit hook 装到多个 git 仓库。脚本：`tools/harness/deploy-hooks.py`。

## 前置

- 本机已 clone **mail**（mailbus 根目录，含 `tools/harness/install-hook.py`）
- 目标仓库均为 git 仓库（含 `.git/`）
- 可选：`MAILBUS_PUBLISH=1` 或 `--publish` 才会真实 POST 报告到 mailbus API

## 用 manifest（推荐）

示例 manifest：`config/mailbus/harness-projects.example.json`（已含 **mail 自身**、mailbus-core、opencode、Agent-Reach）。

```bash
cd mail

# 仅校验路径、打印计划
python tools/harness/deploy-hooks.py \
  --manifest config/mailbus/harness-projects.example.json \
  --dry-run

# 实际安装 hook（默认 dry-run 发布，不写 API）
python tools/harness/deploy-hooks.py \
  --manifest config/mailbus/harness-projects.example.json
```

`mailbus_root` 字段指向 mail  checkout；各 `projects[].repo` 相对 manifest 所在目录解析。

## 指定单个或多个仓库

```bash
python tools/harness/deploy-hooks.py --projects /path/to/repo-a /path/to/repo-b
python tools/harness/deploy-hooks.py --projects . --mailbus-root /path/to/mail
```

## 常用选项

| 选项 | 说明 |
|------|------|
| `--dry-run` | 只验证 git 仓库并打印计划，不写 hook |
| `--publish` | 对所有目标启用真实 POST（等价 hook 内 `MAILBUS_PUBLISH=1`） |
| `--mailbus-root` | 覆盖 manifest 中的 mailbus 根路径 |

## 验收

每个目标仓库应出现 `.git/hooks/post-commit`（或 core.hooksPath 指向的脚本），commit 后触发 Layer 1 pytest。详见 [harness-final-plan.md](./harness-final-plan.md)。

## 相关

- [quality-harness-pipeline-spec.md](./quality-harness-pipeline-spec.md) — 报告 → pipeline
- [harness-final-plan.md](./harness-final-plan.md) — 三层门禁与验收清单
