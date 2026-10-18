# identities（人设 / 身份文件）

出厂默认身份根目录。开源仓库只放 **示例**，不要提交真实员工 SOUL / 私密档案。

## 结构

```
identities/
  README.md                 # 本文件
  examples/
    agent-demo.md           # 最小示例人设
```

## 配置

- **默认：** `store/config.json` → `asset_paths.identity.mode=default`（本目录）
- **自定义：** 设置页改路径指向本机 Vault 等；保存后只走自定义

详见驾驶舱「资产路径」与 `migrate/env.template`。
