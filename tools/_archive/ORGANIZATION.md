# 🏢 子言·AI 团队组织图

> 更新日期: 2026-06-24  
> 机器可读编制表: [`store/roles/json/roster.json`](store/roles/json/roster.json)（13 人，含 gender）

---

## 性别一览

| ID | 姓名 | 性别 |
|----|------|------|
| lingzhao | 灵昭 | 男 |
| lingjin | 灵瑾 | 女 |
| lingxi | 灵犀 | 女 |
| lingtuo | 灵拓 | 男 |
| lingjian | 灵鉴 | 男 |
| lingyan | 灵验 | 女 |
| lingxun | 灵巡 | 男 |
| lingxiao | 灵霄 | 男 |
| dali | 大力 | 男 |
| lingyun | 灵云 | 女 |
| xiaoqi | 小七 | 女 |
| yige | 一哥 | 男 |
| lingzhang | 灵账 | 女 |

---

## 成员一览（13 人）

### 决策与方案

| | 灵昭 (lingzhao) |
|---|-----------------|
| **性别** | 男 |
| **角色** | 方案设计师，团队二把手 |
| **框架** | Hermes Profile |
| **Dashboard** | http://localhost:9120/chat |

### 商前（调研 · 商机 · 获客）

| | 灵犀 (lingxi) | 灵拓 (lingtuo) | 一哥 (yige) |
|---|---------------|----------------|-------------|
| **性别** | 女 | 男 | 男 |
| **角色** | 前沿技术研究员 | 市场拓展官 | 首席运营 · 内容获客 |
| **框架** | Hermes :9122 | Hermes :9126 | OpenClaw :18790 |
| **分工** | 趋势/雷达 | intake 研判、防烂单 | outbound 内容、多平台发布 |

### 交付链（开发 · 质量 · 调度）

| | 灵霄 | 大力 | 灵云 | 灵瑾 | 灵鉴 | 灵验 | 灵巡 | 小七 |
|---|------|------|------|------|------|------|------|------|
| **id** | lingxiao | dali | lingyun | lingjin | lingjian | lingyan | lingxun | xiaoqi |
| **性别** | 男 | 男 | 女 | 女 | 男 | 女 | 男 | 女 |
| **角色** | 技术负责人 | flash 编码 | pro 精细编码 | 网络安全 | 代码审查 | 测试 | 巡检 | 调度·验收 |
| **框架** | Codex | OpenCode | Claude Code | Hermes :9121 | Codex | Claude Code | Hermes :9125 | OpenClaw :18789 |

### 商后（回款）

| | 灵账 (lingzhang) |
|---|---------------------|
| **性别** | 女 |
| **角色** | 财务跟进官 — 账期、开票提醒、回款 |
| **框架** | Hermes Profile |
| **Dashboard** | http://localhost:9127/chat |

---

## 端到端流程

```
【商前】平台/线索 → 灵拓研判 → 灵昭 brief → 小七拆工单
                    ↘ 一哥内容获客（content_hint）

【交付】灵霄/大力/灵云 → 灵鉴 → 灵验 → 小七验收 → 上线
        （灵瑾安全 · 灵巡巡检 横切）

【商后】验收 approved → 灵账建账期 → 回款提醒
```

---

## 已退役成员

| 成员 | 原角色 | 替代 |
|------|--------|------|
| ~~大壮 (dazhuang)~~ | 代码审查 | 灵鉴 + review.py |

---

## 基础设施端口

| 服务 | 端口 |
|------|------|
| mailbus API | **9814**（Windows 本机 / Docker 默认；`$MAILBUS_API_PORT` 可覆盖） |
| 灵昭–灵巡 Hermes | 9120–9123, 9125–9126（灵验已迁 Claude Code，:9124 可停用） |
| 灵拓 / 灵账 | 9126 / 9127 |
| 小七 / 一哥 OpenClaw | 18789 / 18790 |

---

## Agent 框架说明

- **灵霄 / 灵鉴**：Docker `codex-agent`，config `type=codex`；看板 **Web** → codexapp（9240/9241），备用 ttyd（9250/9251）；**勿用 Codex Desktop**（DeepSeek 网关）
- **大力**：Docker `opencode-agent`，config `type=opencode`
- **灵云 / 灵验**：宿主机 Claude Code，config `type=claude_code`（`mailbus_claude`）；看板 **Web** → WSL ttyd（9260/9261）；**勿用 Claude Desktop**
- **Cline**：legacy，仅 WSL 宿主机直连场景

## mailbus 通信规则

收到消息：**ack → 执行 → 回复发件人**。禁止只 ACK 不执行。
