# Examples 路径说明（P3-S39）

| 用途 | SoT 路径 | 运行时 |
|------|----------|--------|
| order-intake 样例 | `mail/examples/order-intake.pursue.example.json` | `init --fresh` 后写入 `store/leads/order-intake.json`（空数组或测试 seed） |
| config v3 样例 | `mail/examples/config.example.json` | 参考用；运行时 SoT 为 `store/config.json`（由 init-store 生成） |
| workflows 样例 | `mail/examples/workflows-registry.example.json` | SoT 为 `mail/config/workflows/registry.json` → 镜像 `store/workflows/` |

**注意**

- 勿将 `mail/examples/` 当作运行时读取路径；测试应通过 `tests/test_helpers.py` 从 config/org seed。
- 旧路径 `store/examples/` 已废弃；validator 读 `store/leads/order-intake.json` + `mail/rules/schemas/` 回退。
