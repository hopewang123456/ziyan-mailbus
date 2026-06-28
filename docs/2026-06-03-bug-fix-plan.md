# 2026-06-03 Bug 修复计划 (P0-P4)

## P0 — API Key 继承机制

**问题：** Hermes profile 的 auth.json 中 credential_pool 为空数组，且 profile 目录没有 .env 文件。
profile 启动时读不到 API Key，chat -q 模式报 401。

**修复方案：**
在 `mailbus-boot.sh` 的 `launch_all()` 中，对每个 `hermes_profile` 类型的 agent，
启动前检测 profile 目录下是否有 `.env` 链接或文件。如果没有，创建到主 `.env` 的符号链接：

```bash
if [ ! -f "$PROFILE_DIR/.env" ]; then
  ln -sf /mnt/e/hermes-data/.hermes/.env "$PROFILE_DIR/.env"
fi
```

或者让 Hermes 启动时自动检测主配置的 credential_pool 并继承（需要改 Hermes 代码）。

**优先级：** P0
**执行者：** 灵霄

---

## P1 — 推送消息 system context 过长

**问题：** mailbus 推送消息时附带了大段 system context（300+ 行的 mailbus 工作纪律说明），
模型需要读完这些才能处理实际任务，导致 chat -q 模式耗时 > 2 分钟。

**方案 A（推荐）：** 精简 system context 到 30 行以内，只保留核心字段（ack 路径、回复格式）。
详细内容放到首次推送时发一次，后续只发增量。
改 `lib/pusher.py` 中的 `system_context` 变量。

**方案 B：** 让 Hermes 也跑持久会话（类似 Cline hub-daemon），每次推送走 stdin 不是重新启动。

**优先级：** P1
**执行者：** 灵霄

---

## P2 — 串行消息队列

**问题：** 同一个 agent 同时收到多条消息时一次性全部推送，同时 ACK，后面的任务被忽略。

**方案：** 详见 `plans/task-audit-redesign.md` 第五节。核心：
- 一个 agent 最多同时只有 1 条 `pushed` 消息
- `pending → pushed → acknowledged → done` 走完才推下一条
- 加急可插队

**改动文件：** `lib/scanner.py` — `build_queues()` 加单 agent 串行约束

**优先级：** P2
**执行者：** 灵霄

---

## P3 — 灵鉴灵验启动脚本技能名错误

**问题：** `lingjian-start.bat` 指定了不存在的 skill：`code-review-tooling, matt-pocock-skills, mailbus-code-map`
导致启动报错 `Error: Unknown skill(s)`

**修复：** 去掉不存在的 skill，或者查看 Hermes 技能列表替换为实际存在的技能名。
灵鉴应该加载的技能：`requesting-code-review, github-code-review, systematic-debugging, codebase-inspection`

**文件：** `/mnt/c/Users/Administrator/Desktop/批处理/lingjian-start.bat` 第 21 行

**优先级：** P3
**执行者：** 灵霄

---

## P4 — 前端死代码 + 状态细化

**问题：**
1. `renderTasks()` 函数在 HTML 中已无对应的 tab，但 JS 里还保留着
2. 灵验 inbox 历史消息（33 条 done 状态的旧报告）淹没新任务
3. 没有 `processing` 中间态区分"已读未处理"和"已读已处理"

**修复：**
1. 删除 `renderTasks()` 函数
2. 灵霄实现状态细化：inbox API 加 `?status_filter=pending` 参数，默认只返回待处理消息
3. 消息状态机增加 `processing` 态：`pending → pushed → acknowledged → processing → done`

**优先级：** P4
**执行者：** 小七（清理死代码）+ 灵霄（状态细化）
