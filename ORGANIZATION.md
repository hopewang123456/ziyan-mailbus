# 🏢 子言·AI 团队组织图

> 更新日期: 2026-06-03
> 最后更新: 新增灵鉴（代码审查）、灵验（测试验证），退役大壮

---

## 成员一览

### 🪷 灵昭 (lingzhao)
- **角色**: 方案设计师，团队二把手
- **框架**: Hermes（本地）
- **技能**: 塔罗、占星、设计、方案架构
- **Dashboard**: http://localhost:9120/chat

### 🦋 灵瑾 (lingjin)
- **角色**: 网络安全专家
- **框架**: Hermes Profile（lingjin）
- **技能**: 安全审计、渗透测试
- **Dashboard**: http://localhost:9121/chat

### 🔭 灵犀 (lingxi)
- **角色**: 前沿技术研究员
- **框架**: Hermes Profile（lingxi）
- **技能**: 技术调研、GitHub 扫描
- **Dashboard**: http://localhost:9122/chat

### 🔍 灵鉴 (lingjian) — 🆕
- **角色**: 代码审查官
- **框架**: Hermes Profile（lingjian）
- **技能**: 代码审查、review.py、Semgrep
- **Dashboard**: http://localhost:9123/chat

### 🧪 灵验 (lingyan) — 🆕
- **角色**: 测试工程师
- **框架**: Hermes Profile（lingyan）
- **技能**: 功能测试、性能测试、安全回归验证
- **Dashboard**: http://localhost:9124/chat

### 🤖 大力 (dali)
- **角色**: 编码工程师
- **框架**: OpenCode CLI
- **技能**: Python、前端、功能实现
- **启动**: `dali-start.bat`

### 🎯 灵霄 (lingxiao)
- **角色**: 技术负责人、主力编码
- **框架**: Cline CLI
- **技能**: 架构、编码、PR 管理
- **启动**: `灵霄启动.bat`

### 🦞 小七 (xiaoqi)
- **角色**: 大管家、调度
- **框架**: OpenClaw Gateway
- **技能**: 调度、报表、文档、验收测试
- **Dashboard**: http://localhost:18789/chat

### 👨‍🔧 一哥 (yige)
- **角色**: 运营
- **框架**: OpenClaw Gateway
- **技能**: 日常运营
- **Dashboard**: http://localhost:18790/chat

---

## 已退役成员

| 成员 | 原角色 | 退役原因 | 替代方案 |
|------|--------|---------|---------|
| ~~💪 大壮 (dazhuang)~~ | ~~代码审查~~ | Aider 太慢，无法通过 mailbus 调度 | review.py + Semgrep 自动化审查；灵鉴专职代码审查 |

---

## 代码上线流程（重要）

```
灵霄/大力 提交代码
    ↓
🔍 灵鉴 审查代码（通过 mailbus 通知）
    ↓ 审查通过
🧪 灵验 测试验证（功能/性能/安全回归）
    ↓ 测试通过
🦞 小七 验收 → 通知子言上线
```

**关键规则：**
1. 灵鉴不通过 → 代码打回修改，不上线
2. 灵验不通过 → 代码打回修改，不上线
3. 小七未验收 → 不上线
4. 每一步完成后必须回复发件人告知结果
5. 禁止只 ACK 不执行、禁止执行完不回复

---

## mailbus 通信规则

所有成员通过 ziyan-mailbus 消息总线通信。

**收到消息三部曲：**
1. 写 ACK → 2. 执行任务 → 3. 回复发件人

**禁止行为：**
- ❌ 只 ACK 不执行
- ❌ 执行完不回复
- ❌ 回复「完成回执」无实质内容
- ❌ 多项任务只回最新一条

---

## 基础设施端口

| 服务 | 端口 | 说明 |
|------|------|------|
| AgentMemory | 3111 | 持久记忆 |
| mailbus API | 9812 | 消息总线 + Dashboard |
| 灵昭 | 9120 | Hermes Dashboard |
| 灵瑾 | 9121 | Hermes Dashboard |
| 灵犀 | 9122 | Hermes Dashboard |
| 灵鉴 | 9123 | Hermes Dashboard |
| 灵验 | 9124 | Hermes Dashboard |
| 小七 | 18789 | OpenClaw Gateway |
| 一哥 | 18790 | OpenClaw Gateway |
