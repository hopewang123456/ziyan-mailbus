# mailbus 优化方案讨论纪要

> 2026-06-03 · 灵昭整理
> 
> 全部方案讨论完毕后一起派工

---

## 🔴 1. Agent 收不到消息或响应太慢

### 已完成的部分
- **P0** API Key 继承机制 → 已派灵霄
- **P1** 精简推送 system context → 已派灵霄
- **P2** 串行消息队列 → 已派灵霄
- **P4** 状态细化 + inbox 默认只显示待处理 → 已派灵霄/小七

### ④ 持久会话（待定）
**问题：** 每次推送启动新的 chat -q 进程，加载慢。
**结论：** 不强求持久会话。通过精简推送 + 规则文档外置来优化。

### ⑤ 规则文档外置（方案已定，等派工）
**核心思路：**
- 把 mailbus 工作纪律从推送消息中剥离到独立文件
- `store/rules/` 下按角色分：`common.md`、`reviewer.md`、`tester.md`、`developer.md`、`dispatcher.md`
- 推送消息只带规则文件路径，不提 token 全文
- 规则变更时通过 mailbus 发广播通知 affected agent

**推送消息新格式：**
```
📬 你有一条新消息
来自: lingzhao | 消息ID: msg-xxx
任务内容：...

【规则文档（请先阅读）】
通用规则: /mnt/e/ai_tools/mail/store/rules/common.md
你的岗位规则: /mnt/e/ai_tools/mail/store/rules/tester.md
```

**变更同步机制：**
- 规则文件被修改后，mailbus watchdog 检测到变更
- 发广播消息给使用该规则的所有 agent：`📢 规则更新：tester.md，请重新阅读`

**实现：**
- `lib/pusher.py` system context 从 300 行精简到 15 行
- `store/rules/` 目录结构
- watchdog 或 git hook 检测规则变更

### ⑥ Agent 离线检测
**现状：** heartbeat 模块有离线检测，离线超过 3 次 ping 会发通知给灵昭。
**待优化：** 离线时 inbox 消息应该继续保持 pending，等上线后再推送（目前好像已经是这样？需要确认）。

---

## 🟡 2. 消息搜索和查看历史

**现状：** 
- 要查历史只能读 `store/inbox/<agent>/inbox.json` 的原始 JSON
- 没有按时间/关键词/发送人搜索的 API
- dashboard 上没有全局搜索入口

**方案（待讨论）：**

---

## 🟡 3. 消息撤回/编辑功能

**现状：** 发错了消息没法撤回，agent 回复了错误内容也没法编辑。

**方案（待讨论）：**

---

## 🟡 4. 消息模板/快捷回复

**现状：** 每次发任务都要手敲完整内容。常见任务类型没有模板。

**方案（待讨论）：**

---

## 🟢 5. 归档机制启用

**现状：** `lib/archiver.py` 已存在但没被触发。
**方案：** 自动归档超过 N 天的 done 消息，融入 P4 的状态细化方案。

---

## 🟢 6. Dashboard 移动端适配

**现状：** mailbus dashboard 在手机上基本不可用。

**方案（待讨论）：**

---

## 🟢 7. 消息统计/报表

**现状：** 看不到消息量、agent 活跃度、响应时间等数据。

**方案（待讨论）：**
