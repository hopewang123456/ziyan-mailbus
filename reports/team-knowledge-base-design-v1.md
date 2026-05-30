# 子言·AI 团队知识库设计方案

> **作者**: 灵昭 🪷  
> **日期**: 2026-05-28  
> **版本**: v1.1  
> **更新**: 2026-05-29 — 采纳灵犀 review 建议（areas MOC + Phase 4 cronjob 收束）  
> **状态**: 待实施  
> **关联**: [lingxi-team-knowledge-base-20260528]

---

## 一、方案总览

### 核心原则
1. **零成本** — 全免费方案，Obsidian 免费 + GitHub 私有仓库免费（5人以下团队）
2. **Agent 友好** — Markdown 文件直读，Hermes/OpenClaw 用文件工具即可读写
3. **去中心化** — 每人本地一份 vault，Git push/pull 同步，无中心服务器
4. **渐进式** — 先搭骨架再填充，不追求一步到位
5. **不改 agent 代码** — 知识库自动写入通过 cli git 操作实现，不入侵任何框架

### 技术栈
| 组件 | 选择 | 理由 |
|------|------|------|
| 笔记工具 | Obsidian v3.0+ | 免费，本地 Markdown，插件生态好 |
| 同步方式 | Git（GitHub Private Repo） | 免费，版本管理，冲突解决成熟 |
| 仓库位置 | 团队 GitHub 组织下私有仓库 | 统一管理 |
| 本地路径 | `/mnt/e/ziyan-wiki/`（Linux）/ `E:\ziyan-wiki\`（Windows） | WSL 和 Windows 共享路径 |

---

## 二、Vault 目录结构

### 顶层结构（4大分区）

```
ziyan-wiki/
├── 0-inbox/                  # 临时收件箱—未整理的笔记都丢这里
├── 1-projects/               # 项目笔记—有时限、有目标的任务
├── 2-areas/                  # 领域知识—持续积累的责任区
├── 3-resources/              # 主题资源—可复用的参考材料
├── 4-archive/                # 归档—已完成/不再活跃的内容
├── attachments/              # 附件—图片、PDF、截图等
├── templates/                # 模板—新笔记模板
│   ├── default.md
│   ├── project.md
│   ├── meeting.md
│   ├── decision.md
│   └── tech-note.md
├── .obsidian/                # Obsidian 配置（自动生成）
├── .gitignore
└── README.md
```

### 详细说明

#### 0-inbox/ — 收件箱
- 所有新笔记首放入这里
- 每周整理一次，归类到其他分区
- 灵霄的自动归档脚本写入这里 → 小七定期整理
- 子目录按月份分：`2026-05/`, `2026-06/`

#### 1-projects/ — 项目笔记
每个活跃项目一个文件夹：
```
1-projects/
├── mailbus-v2/               # mailbus 消息总线
│   ├── README.md             # 项目概述 + 当前状态
│   ├── architecture.md       # 架构设计
│   ├── decisions/            # ADR 决策记录
│   │   ├── ADR-001-domain-routing.md
│   │   ├── ADR-002-heartbeat-model.md
│   │   └── ...
│   ├── meeting-notes/        # 会议记录
│   └── tech-notes/           # 技术笔记
├── dashboard-vue/            # dashboard 前端
├── lingxiao-task-tracker/    # TaskTracker 集成
├── team-knowledge-base/      # 本案（自引用 😄）
└── ...
```

#### 2-areas/ — 领域知识
各子域至少包含一个 `README.md` 文件作为 MOC（内容地图），方便新人浏览：
```
2-areas/
├── ai-agents/                # AI Agent 框架知识
│   ├── openclaw-notes.md
│   ├── hermes-agent-usage.md
│   ├── cline-setup.md
│   └── agent-comparison.md
├── development/              # 开发技能
│   ├── python/               # Python 技巧、坑点
│   ├── typescript/           # TypeScript 知识
│   └── vue/                  # Vue.js 项目经验
├── devops/                   # 运维知识
│   ├── wsl-setup.md          # WSL 配置经验
│   ├── docker-notes.md
│   └── github-actions.md
├── ui-ux/                    # 设计知识
│   └── mailbus-dashboard-design-system.md
├── security/                 # 安全（灵瑾负责维护）
│   └── security-checklist.md
├── domain/                   # 业务领域
│   ├── tarot/                # 塔罗知识
│   └── astrology/            # 占星知识
└── tool-guides/              # 工具使用指南
    ├── git-workflow.md
    └── obsidian-hotkeys.md
```

#### 3-resources/ — 主题资源
```
3-resources/
├── paperclip-notes/          # Paperclip 方案研究
├── references/               # 外部参考文章（转摘要+链接）
│   ├── 2026-05/
│   └── 2026-06/
├── cheat-sheets/             # 速查表
│   ├── git-cheatsheet.md
│   └── python-cheatsheet.md
├── diagrams/                 # 架构图、流程图（文本格式）
└── glossaries/               # 术语表
    ├── agent-terminology.md  # AI Agent 术语
    └── team-terminology.md   # 团队内部用语
```

#### 4-archive/ — 归档
项目完成或不再活跃移入此区：
```
4-archive/
├── phase-1-mailbus/          # mailbus Phase 1 完成后归档
├── old-identity-system/
└── ...
```

#### templates/ — 模板
每个模板包含 frontmatter + 内容骨架。

---

## 三、Git 仓库设置

### 仓库配置

| 项目 | 值 |
|------|-----|
| 平台 | GitHub |
| 仓库名 | `ziyan-wiki` |
| 可见性 | Private |
| 组织 | 子言团队 GitHub org |
| 分支策略 | **单品分支**（不强制 PR，允许直接 push main） |
| 冲突解决 | 人工处理 + VS Code merge tool |

### 为什么不强制 PR？
团队小（5人），且笔记内容不是代码——冲突可手动解决。PR 流程增加不必要的摩擦。等未来团队扩大到 10人+ 再考虑引入 PR。

### `.gitignore` 内容
```
.obsidian/workspace
.obsidian/cache
.obsidian/plugins/better-word-count/data.json
attachments/*.exe
*.tmp
.DS_Store
Thumbs.db
```

### `.gitattributes`
```
*.md diff=markdown
```

---

## 四、权限管理

### 人类成员
| 成员 | 权限 | 说明 |
|------|------|------|
| 子言 | 读写 | Owner，可以管理仓库设置 |
| 灵昭 🪷 | 读写 | 方案设计者，维护 2-areas/ 和 3-resources/ |
| 灵瑾 🦋 | 读写 | 维护 2-areas/security/ |
| 灵犀 🔭 | 读写 | 维护 3-resources/references/ |
| 小七 🦞 | 读写 | 维护 1-projects/ 和 0-inbox/ |
| 一哥 🧑‍🔧 | 只读，需要时写 | 可能不需要用 Obsidian，但可以读参考 |

### AI 成员
Agent 通过 Git CLI 操作：
- **灵霄 🦅**: 通过任务的终端执行 git add/commit/push，自动归档技术调研到 3-resources/
- **大力 🤖**: 通过终端的 git 操作提交开发笔记
- **大壮 💪**: 审查时写 review 笔记到 1-projects/
- **我（灵昭）**: 写方案时同步到 vault

> 注意：Agent 的 git 操作跑在 WSL 下，需要配置 SSH key 或 GitHub token。

---

## 五、内容规范

### 命名规范
| 项目 | 规范 | 示例 |
|------|------|------|
| 文件名 | 小写英文，连字符连接 | `adr-001-domain-routing.md` |
| 文件夹名 | 小写英文，连字符连接 | `mailbus-v2/` |
| 标题 | 中文/英文均可，首字母大写 | `# Mailbus V2 架构设计` |
| 日期格式 | ISO 8601 | `2026-05-28` |
| 标签 | 小写英文 | `#architecture #design` |

### Frontmatter 规范
所有笔记必须有 frontmatter：
```yaml
---
title: Mailbus V2 架构设计
created: 2026-05-28
updated: 2026-05-28
author: 灵昭 🪷
status: draft          # draft | review | published | archived
tags: [mailbus, architecture, design]
source:                # 可选，外部来源链接
project: mailbus-v2    # 可选，关联项目
---
```

### 链接规范
- 使用 Obsidian WikiLink 语法：`[[note-name]]`
- 外部链接用标准 Markdown：`[title](url)`
- 图片放 `attachments/` 目录

### 写作规范
1. **优先中文** — 团队母语，所有笔记默认中文
2. **技术术语保留英文** — API, Agent, Git, PR 等不翻译
3. **代码块标注语言** — ` ```python` 而不是 ` ``` `
4. **每个文件聚焦一个主题** — 不要一个文件写太多内容
5. **使用 MOC（内容地图）** — 关键目录有索引文件

---

## 六、Agent 自动写入机制

### 方案：写文件 → cronjob 统一提交

AI agent（灵霄、大力等）**只负责写文件**，不负责 git 操作：

```bash
# 笔记写入（通过 Hermes write_file 工具）
write_file("/mnt/e/ziyan-wiki/3-resources/references/2026-05/some-new-tech.md", content)
# ✅ Agent 写完就走，不 git commit，不 git push
```

由 mailbus 维护一个 **定时 cronjob**（每 30 分钟）统一执行 git add/commit/push：

```bash
cd /mnt/e/ziyan-wiki
git add -A
git diff --cached --quiet || git commit -m "docs: 自动同步 $(date +%Y-%m-%d-%H:%M)"
git push
```

### 为什么用 cronjob 收束？

| 方案 | 问题 |
|------|------|
| 每个 agent 各自 git commit | ❌ commit message 格式不统一 |
| | ❌ 同时编辑可能 push 冲突 |
| | ❌ 每个 agent 都要配 git 权限 |
| **cronjob 统一收束** | ✅ commit message 格式统一 |
| | ✅ 单点管理，不冲突 |
| | ✅ 一条 cronjob 维护，零额外配置 |

### 自动化触发时机
1. **灵霄调研完成** → 只写文件到 3-resources/
2. **大力解决问题** → 只写文件到 2-areas/development/
3. **方案评审通过** → 只写文件到 1-projects/ 对应目录
4. cronjob 每 30 分钟统一提交全部变更

### 不做的方案
- ❌ Obsidian 插件自动同步（依赖 Obsidian 运行）
- ❌ Webhook 触发同步（依赖 CI）
- ❌ API 对接（依赖额外 server）
- ❌ 每个 agent 单独 git 操作（如上所述，统一管理更好）

### 为什么不做实时同步？
Agent 和人类的工作节奏不同。Agent 写笔记后不需要立即在人类屏幕上弹出——每天 pull 一次就够了。低频率、低成本、零依赖。cronjob 每 30 分钟收束一次，既不实时也不延迟太多。

---

## 七、实施路线

### 阶段划分

#### Phase 1 — 基础设施（大壮，~1h）
- [ ] 在 GitHub 创建私有仓库 `ziyan-wiki`
- [ ] 准备 SSH key 或 GitHub token 配置文档
- [ ] 在 `/mnt/e/ziyan-wiki/` 初始化本地仓库
- [ ] 写入 `.gitignore` / `.gitattributes`
- [ ] 配置 WSL 中 Agent 的 git 用户信息
- [ ] 第一次 `git push`

#### Phase 2 — 目录骨架 + 模板（大力，~1.5h）
- [ ] 按上述结构创建所有目录
- [ ] 每个目录写一个 `README.md` 做 MOC
- [ ] 创建 `templates/` 下的所有模板
- [ ] 写 `README.md` 根文档（vault 总导航）
- [ ] 写 `templates/default.md` 作为快速笔记模板
- [ ] push 到远程

#### Phase 3 — 知识迁移（全员，持续）
- [ ] 迁移现有技术文档到对应目录
- [ ] 迁移 mailbus 架构设计笔记
- [ ] 迁移团队人设/组织文档
- [ ] 建立「值得归档」的意识

#### Phase 4 — Agent 自动写入（大力，~1h）
- [ ] 创建 cronjob 脚本（git add/commit/push 统一提交）
- [ ] 注册到 mailbus cron 调度（每 30 分钟）
- [ ] 文档化 agent 写入规范（只写文件，不碰 git）

---

## 八、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Git 冲突 | 中 | 低 | 小团队笔记冲突少，人工解决 |
| Agent 自动提交 wrong commit | 低 | 中 | commit message 模板化，加自动 review |
| 人类不习惯用 Obsidian | 中 | 中 | 先由 AI agent 填充，人类只读可接受 |
| 仓库膨胀 | 低 | 中 | 附件用 git lfs（暂不需要），或定期清理 |
| 子言不会用 Obsidian | 高 | 高 | 🔴 **关键风险**——下文单独讨论 |

---

## 九、子言的使用场景分析

### 核心问题
子言的时间有限（白天有正式工作），他最可能的需求是：
1. **查阅** — 团队做了什么技术选型，有没有文档可以参考
2. **记录** — 遇到想记的东西快速写下来
3. **不被打扰** — 不希望晚上回家还要学新工具

### 建议策略
1. **只读即可** — 如果子言不想用 Obsidian，直接用浏览器看 GitHub 仓库里的 Markdown 文件（GitHub 自动渲染）
2. **移动端可选** — Obsidian 有 iOS/Android App，子言可以只安装 App 不装插件
3. **agent 代劳** — 子言如果想说「帮我记一下 XXX」，直接发到 mailbus 小七，小七整理后写入 vault
4. **最低门槛** — 不做复杂要求，子言能打开「E:\ziyan-wiki\」看文件就算成功

---

## 十、下一步行动

### 已确认
- ✅ 灵犀 review 通过
- ✅ 改进点已纳入 v1.1
- ⏳ 等待子言确认方向

### 给大壮 💪（Phase 1）
- 在 GitHub 创建私有仓库 `ziyan-wiki`
- 初始化本地 repo + git 配置
- 第一次 git push

### 给大力 🤖（Phase 2 + 4）
- Phase 2：创建目录骨架和模板
- Phase 4：创建 cronjob git 统一提交脚本

### 给子言 👑
- 确认方案方向
- 看看要不要装 Obsidian App（至少手机装一个）

### 后续
Phase 3（知识迁移）在 Phase 1+2 完成后由全员持续进行

---

*—— 灵昭 🪷，方案完毕。*
