---
created: 2026-08-05
updated: 2026-08-05
project: mailbus
type: docs
status: active
owner: 子言
---

# 迁移 checklist

- [ ] 目标框架已登记；runtime_plane 已选
- [ ] dry_run 打印 data_root / container_root / host_binds
- [ ] 独占路径/端口无冲突；shared_impact 已确认
- [ ] 源已 disable 并停进程
- [ ] 覆盖策略已选（全覆盖 / abort）
- [ ] 源处理：下架 / 彻底删除
- [ ] 迁后是否拉起已决定
- [ ] 密钥/pairing 人工核对
