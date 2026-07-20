# OpenCode — 交付 SoT（L1 exclusive）

**dali 完成依据：patch + replies。** msg-results 不是 pipeline 主 SoT。

## 步骤

1. `git add -A && git commit -m "fix: <说明>"`
2. `git format-patch HEAD~1 --output-directory /mailbus/store/patches/`
3. `store/replies/{sender}.json`：

```json
{
  "agent": "dali",
  "msg_ids": ["<id>"],
  "reply": "已完成: <简述>",
  "patch": "/mailbus/store/patches/<file>",
  "timestamp": "<ISO8601>"
}
```

## sender 路径

| 发件方 | replies 文件 |
|--------|--------------|
| 灵霄 lingxiao | `store/replies/lingxiao.json` |
| 灵昭 lingzhao | `store/replies/lingzhao.json` |
| 小七 xiaoqi | `store/replies/xiaoqi.json` |

## 失败

- commit 前测试失败 → 修复或 `status: failed` 写 replies 说明原因
