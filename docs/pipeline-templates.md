# 流水线模板 & 工单报告格式 v2

> 每个步骤产出一份结构化报告，报告中的 `next` 字段决定下一步派发给谁。
> mailbus 根据 `next` 解析下一步的 assignee，不需要预定义流程。

---

## 核心机制

### 一次完整的流转

```
灵昭发任务给大力
  ↓
大力做完 → 写 dev-report → 报告里写 next: "lingjian"
  ↓ mailbus 解析 next → 自动推给灵鉴
灵鉴审查 → 写 review-report → 报告里写 next: "lingyan"（通过）或 "dali"（不通过）
  ↓ mailbus 解析 next → 推给对应的人
灵验测试 → 写 test-report → 报告里写 next: "xiaoqi"
  ↓
小七验收 → 写 approve-report → 报告里写 next: ""（没有下一步 = 完成）
```

### 每个报告的通用字段

```json
{
  "template": "review-report",
  "conclusion": "pass",
  "next": "lingyan",
  "summary": "代码审查通过",
  "details": {}
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `template` | ✅ | 工单模板名称，如 review-report |
| `conclusion` | ✅ | 结论：`pass` / `fail` / `done` / `blocked` / `approve` / `reject` |
| `next` | ✅ | **下一步的 assignee**，空字符串表示没有下一步（任务完成） |
| `summary` | ✅ | 摘要，展示在 Dashboard 节点上 |
| `details` | ❌ | 具体内容，各模板不同 |

---

## 各岗位的报告模板

### 1. 方案设计师 — scheme-report（灵昭）

```json
{
  "template": "scheme-report",
  "conclusion": "approved",
  "next": "xiaoqi",
  "summary": "Dashboard重设计方案已完成，请调度开发",
  "details": {
    "design_doc": "plans/dashboard-redesign.md",
    "key_decisions": ["冷色调", "左侧导航", "毛玻璃卡片"],
    "risks": ["大力没做过CSS动效，可能需要指导"]
  }
}
```

| 字段 | 说明 |
|------|------|
| next 典型值 | `xiaoqi`（方案通过后交给小七调度）|

### 2. 技术调研 — research-report（灵犀）

```json
{
  "template": "research-report",
  "conclusion": "done",
  "next": "lingzhao",
  "summary": "调研完成，推荐使用方案B",
  "details": {
    "topic": "前端动画方案调研",
    "candidates": [
      {"name": "方案A: CSS Animation", "pros": "轻量", "cons": "复杂动效吃力"},
      {"name": "方案B: GSAP", "pros": "功能强大", "cons": "需要引入库"}
    ],
    "recommendation": "方案B",
    "references": ["https://gsap.com"]
  }
}
```

| 字段 | 说明 |
|------|------|
| next 典型值 | `lingzhao`（调研结果给灵昭做决策）|

### 3. 开发完成 — dev-report（灵霄/大力）

```json
{
  "template": "dev-report",
  "conclusion": "done",
  "next": "lingjian",
  "summary": "完成了Dashboard配色系统和导航栏改造，pytest通过",
  "details": {
    "changes": [
      {"file": "docs/index.html", "summary": "新增CSS变量系统+左侧导航"},
      {"file": "docs/index.html", "summary": "新增星系粒子背景"}
    ],
    "self_test": "pass",
    "test_output": "pytest tests/ -q → 149 passed"
  }
}
```

| 字段 | 说明 |
|------|------|
| conclusion | `done` / `blocked` |
| next 典型值 | `lingjian`（开发完成→审查）、`lingzhao`（遇到阻塞→找灵昭） |

### 4. 代码审查 — review-report（灵鉴）

```json
{
  "template": "review-report",
  "conclusion": "pass",
  "next": "lingyan",
  "summary": "代码审查通过，2条建议级意见",
  "details": {
    "issues": [
      {"severity": "minor", "file": "lib/pusher.py", "line": 45, "desc": "变量名建议改为snake_case"}
    ],
    "review_tool": "review.py + Semgrep",
    "passed_checks": ["安全扫描", "代码规范", "逻辑正确性"]
  }
}
```

| 字段 | 说明 |
|------|------|
| conclusion | `pass` / `fail` / `warn` |
| next（pass时） | `lingyan`（通过→测试）或 `xiaoqi`（小改动→小七验收兼测） |
| next（fail时） | `dali` 或 `lingxiao`（不通过→退回开发重修） |

### 5. 测试 — test-report（灵验）

```json
{
  "template": "test-report",
  "conclusion": "pass",
  "next": "xiaoqi",
  "summary": "回归测试3/3全部通过",
  "details": {
    "results": [
      {"name": "页面访问 200", "status": "pass"},
      {"name": "搜索API返回结果", "status": "pass"},
      {"name": "统计API数据完整", "status": "pass"}
    ],
    "total": 3,
    "passed": 3,
    "failed": 0,
    "environment": "WSL Python 3.11"
  }
}
```

| 字段 | 说明 |
|------|------|
| conclusion | `pass` / `fail` |
| next（pass时） | `xiaoqi`（通过→验收） |
| next（fail时） | `dali` 或 `lingxiao`（不通过→退回开发） |

### 6. 验收 — approve-report（小七）

```json
{
  "template": "approve-report",
  "conclusion": "approve",
  "next": "",
  "summary": "审查通过、测试通过、功能符合需求，可以上线",
  "details": {
    "checks": [
      {"name": "审查已通过", "status": "yes"},
      {"name": "测试已通过", "status": "yes"},
      {"name": "功能符合需求", "status": "yes"}
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| conclusion | `approve` / `reject` |
| next（approve时） | `""`（验收通过=任务完成，没有下一步） |
| next（reject时） | 退回对应的开发人员 |

### 7. 上线 — deploy-report（一哥/小七）

```json
{
  "template": "deploy-report",
  "conclusion": "deployed",
  "next": "",
  "summary": "Dashboard重设计已部署上线",
  "details": {
    "deploy_time": "2026-06-04T14:00:00+0800",
    "version": "v2.2.0",
    "changes": "冷色调配色、左侧导航、星系粒子背景",
    "status": "running",
    "url": "http://localhost:9812"
  }
}
```

| 字段 | 说明 |
|------|------|
| conclusion | `deployed` / `failed` |
| next | `""`（部署完成=整条任务结束）或 `lingzhao`（部署失败） |

### 8. 巡检 — patrol-report（灵巡）

```json
{
  "template": "patrol-report",
  "conclusion": "done",
  "next": "",
  "summary": "巡检完成，10/10 Agent在线，1条待处理",
  "details": {
    "online_agents": 10,
    "pending_tasks": 1,
    "findings": [
      {"severity": "warning", "agent": "lingjian", "desc": "审查任务待处理（已超15分钟）"}
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| next | `""`（巡检报告存档）|

---

## 流转逻辑

### mailbus scan 检测

```python
def process_pipeline_step(task_id, step_report):
    """根据工单的 next 字段自动流转"""
    next_assignee = step_report.get("next", "")
    
    if not next_assignee:
        # 没有下一步 → 任务完成
        mark_task_done(task_id)
        return
    
    # 有下一步 → 发消息给 next_assignee
    # 消息内容包含上一步的工单摘要 + 本步骤的任务描述
    send_message(
        to=next_assignee,
        content=f"你有一个新任务，上一步 ({step_report['template']}) 已完成。\n摘要: {step_report['summary']}\n请继续处理。"
    )
```

### 判定完成 vs 不通过

| conclusion 值 | 含义 | 流转行为 |
|---------------|------|----------|
| `done` / `pass` / `approve` / `deployed` / `confirmed` | 成功 | 读取 next，推送下一步 |
| `fail` / `reject` / `blocked` | 失败 | 读取 next（通常是退回开发），推送+通知灵昭 |
| `warn` | 有建议但通过 | 同 pass，但记录建议 |

---

## 跟之前设计的关联

| 概念 | 关联 |
|------|------|
| 规则文档 `store/rules/*.md` | 告诉 agent 每个步骤应该怎么做、报告格式是什么 |
| 工单模板 `store/templates/*.json` | 每个报告的 JSON schema 定义 |
| 推送消息 | 每次推送时告诉 agent：你的任务 + 必须回复的报告格式 |
| Dashboard 节点展示 | 每个步骤的工单内容可点击查看 |

---

## Agent 需要知道的事情

推送消息里需要告诉 agent：
1. **你要做什么**（任务描述）
2. **你要按什么格式回复**（附 JSON 模板）
3. **你写报告时要把下一步派给谁**（根据你的结论决定）

例如给灵鉴的审查消息：
```
📬 审查任务
请审查以下代码改动：xxx

审查完成后，请按以下格式回复：

--- 审查报告 ---
{
  "template": "review-report",
  "conclusion": "pass",         // 通过 或 fail 或 warn
  "next": "lingyan",            // 通过→给灵验测试；不通过→退回给大力
  "summary": "...",
  "details": { ... }
}
---
```
