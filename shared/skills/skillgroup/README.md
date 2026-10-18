# Skillgroup — 技能共享组

本目录是 **技能共享组（skillgroup）** 的默认根。规则：

- 每个**一级子目录 = 一个组**，组名即子目录名（可跨框架复用）。
- 组下每个子目录（或 `*.md`）= 一个技能；技能目录通常含 `SKILL.md`。

装配语义（见 `lib/adapters/config/assemble.py`）：

```
skills = 角色私有 ∪ skillgroup(多选) ∪ 框架公共
        同名覆盖：角色 > 组 > 框架
```

角色卡在 Cockpit 里多选要挂载的组（存到 `store/config.json` 的 `agents.<id>.skill_groups[]`）。

本机（SoT 在 Obsidian Vault）可用 `MAILBUS_SKILLGROUP_ROOT` 环境变量把根指到 Vault 对应目录，
例如 `03-shared/skillgroup`，避免与仓库 junction 双源。未设置时回落到此默认路径。

## 示例

```
skills/skillgroup/
├── writing/            # 组 "writing"
│   ├── style-guide/SKILL.md
│   └── translation/SKILL.md
└── media/              # 组 "media"
    ├── video-publish/SKILL.md
    └── screenshot/SKILL.md
```
