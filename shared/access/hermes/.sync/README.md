# Hermes 共享技能（单源 + 生成）

本目录只保留 **一份** 共享技能源：`_shared/<skill>/SKILL.md`。

各 profile 的 `skills/` 是 **生成产物**，不再手工维护、也不入库：

```bash
# 在仓库根目录执行
python python/tools/sync_hermes_skills.py           # 物化到默认 6 个 profile
python python/tools/sync_hermes_skills.py --check    # 校验副本与单源是否漂移
```

> 历史：此前 6 个 profile × 3 个技能共 18 份完全相同的 SKILL.md 被逐个复制维护，
> 已改为单一源 + 生成脚本。修改技能请只改 `_shared/` 下的文件，再执行上面的命令。
