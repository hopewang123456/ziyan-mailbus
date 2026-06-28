# mailbus 稳定性 & 工作流完善 — Bug/优化清单

> 整理时间：2026-06-16  
> 来源：Docker 化回归测试、冷启动、e2e、工作流 smoke、代码审查  
> 目标：为明日大任务做准备，确保 Cursor ↔ mailbus ↔ 全 agent 链路可跑通

---

## 一、本次已修复（回归已通过）

| # | 问题 | 根因 | 修复 | 验证 |
|---|------|------|------|------|
| F1 | mailbus 容器反复重启 | systemd ExecStop 执行 compose down | ExecStop=/bin/true | e2e 60s 稳定性 0 restart |
| F2 | 宿主机 legacy cron 与 Docker mailbus 冲突 | 双实例抢 9812 | cleanup + Docker 独占 | smoke 8/8 |
| F3 | 容器代理指向失效 172.17.0.1:7898 | 硬编码 | setup-container-proxy 读 Windows 代理 | 代理 OFF/ON 均 OK |
| F4 | OpenClaw 小七/一哥浏览器都进小七 | 共用 OPENCLAW_STATE_DIR | 独立 .openclaw-xiaoqi / yige | 18789/18790 配置 id 分离 |
| F5 | Hermes 灵昭 CLI 失忆 | SOUL.md 覆盖 system_prompt | sync-identities.sh | CLI 回复「灵昭，方案设计师…」 |
| F6 | **scan cron 丢失，工作流卡住** | cleanup 删了 bus scan 条目 | install-mailbus-scan-cron.sh + start-team 自动安装 | crontab 已恢复 |
| F7 | memory-bridge cron 崩溃 | inbox.json list 格式 + 批量超时 | normalize_inbox + --limit 20 | cron 不再 traceback |
| F8 | watchdog chmod 污染日志 | 非 root chmod 1777 失败 | 2>/dev/null \|\| true | start-team 无 chmod 报错 |
| F9 | 冷启动 timeout 报错 | 非交互环境 timeout 不支持 | ping -n 替代 | cold-start.log PASS |
| F10 | 重复 force-recreate 耗时长 | 每次 start-team 都重建 | .proxy-state 仅变更时重建 | 日志 Proxy unchanged |
| F11 | workflow-smoke bus send 语法错误 | 用了 --to 而非 positional | 已改 bus send agent | API 创建+写入 OK |

**回归成绩：** smoke 8/8 · e2e 5/5 · cold-start PASS · monitor 9/9

---

## 二、P0 — 阻塞工作流（必须修，否则 agent 链跑不通）

### P0-1 流水线引擎未接入 scan ⚠️ 最关键

- **现象：** `lib/pipeline_trigger.py` 已实现「读 msg-results → 自动推进下一角色」，但 **全仓库无任何 import/call**
- **设计文档：** `plans/p0-design.md` 要求 `scanner.run_housekeeping` 调用 PipelineEngine
- **实际：** `run_housekeeping` 只有催办/归档/索引，**没有 pipeline trigger**
- **后果：** 灵昭/灵霄/灵鉴/灵验各自收消息，**不会自动流转**；Dashboard 任务链 status 永远 pending
- **修复建议：**
  1. 在 `run_housekeeping` 末尾调用 `pipeline_trigger.trigger(data_dir, agents, paths)`
  2. 修复 `pipeline_trigger.py` L65/L85 `task_id` 未定义 bug
  3. 补集成测试：mock msg-results → 验证 chain 推进 + inbox 写入

### P0-2 任务 chain 格式不统一

- **现象：** `POST /api/tasks/create` 接受 `chain: ["lingzhao","xiaoqi",...]` 字符串数组
- **pipeline_trigger 期望：** `[{step, to_role, to_person, status, started_at, ...}]` 对象数组
- **后果：** 即使接入 trigger，现有任务 chain[-1].get("to_person") 为空，**pipeline 跳过**
- **修复建议：**
  1. `TaskTracker.create` 增加 `init_pipeline_chain(template)` 按 role-flow-config 初始化第一步
  2. API 接受 `template: "full"` 或 `chain_template: "A"` 替代裸字符串数组
  3. Dashboard 展示统一为 pipeline 步骤对象

### P0-3 inbox 积压淹没新任务

- **现象：** lingzhao urgent 队列 450+ 条；game-lvup 测试任务 pushed_count=0
- **根因：** 串行队列 + 历史 reply/notice 未归档；单 agent 每次 scan 只推 1 条
- **修复建议：**
  1. 归档/关闭 2026-06-15 之前的 done/acknowledged 消息（或移入 archive）
  2. scan 优先推送 type=task 且带 task_id 的消息
  3. 启用 `archive_max_messages` 更积极清理（config 已有，需调参）

### P0-4 CLI send 无即时推送

- **现象：** `bus send` 只写 inbox，等 cron scan 才推送（最长 1 分钟）
- **对比：** `POST /api/send-msg` 写完后立即 `push_messages`
- **修复建议：** `cmd_send` 写入后可选 `--instant` 或默认调用与 send-msg 相同的 push 逻辑

---

## 三、P1 — 严重（影响日常与大任务）

| # | 问题 | 模块 | 建议 |
|---|------|------|------|
| P1-1 | Agent auto-ack 不执行 | 灵霄/大力/灵鉴 | 强化 pusher 指令 + mailbox-daemon task 分流；见 plans/fix-lingxiao-auto-ack.md |
| P1-2 | 推送消息过长导致 chat -q 超时 | pusher.py | system context 已精简，需验证 <15 行生效 |
| P1-3 | OpenClaw 小七 context overflow | openclaw | contextWindow 1M 已改，需长对话回归 |
| P1-4 | e2e 与 cold-start 并行会互杀 | 测试脚本 | e2e 开头检测 lock；或文档规定顺序执行 |
| P1-5 | Docker 缺 lingjian/lingyan/lingxi 容器 | docker-compose | 大任务前确认 Hermes 9121-9125 对应 agent 在线 |
| P1-6 | 任务审计/催办 false alarm | tracker | tracker-remind 系列重复投递，需 inbox_overflow 修复 |
| P1-7 | GitHub 改动未整理上传 | docker-agents | 按 GITHUB_PREP.md 脱敏后 init repo |

---

## 四、P2 — 体验与明日扩展

| # | 问题 | 说明 |
|---|------|------|
| P2-1 | Dashboard 任务链 UI 与 pipeline 步骤不同步 | 前端 renderTasks 死代码；需对接新 chain 格式 |
| P2-2 | Cursor ↔ mailbus 任务入口 | 建议：`workflow-smoke.sh` 升级为 `create-pipeline-task.sh` 标准模板 |
| P2-3 | 打怪升级小游戏 E2E | 作为 pipeline 模板 A 的验收用例，链：灵昭→小七→灵霄→灵鉴→灵验→小七 |
| P2-4 | WSL localhost 代理 NAT 警告 | 不影响功能，可忽略或 fix-wsl-localhost 文档化 |
| P2-5 | config.json unknown field max_concurrency | 校验告警噪音，schema 补字段或忽略 |

---

## 五、建议交给灵昭的任务包（待你确认后 mailbus 下发）

### 任务 ID：`mailbus-hardening-20260616`

**摘要：** mailbus 工作流 P0 修复 — 接入 pipeline + 统一 chain 格式 + inbox 减负

**流水线模板 A（完整流程）：**

```
Cursor/子言 提需求
  → 灵昭(方案设计师)  输出修复方案 + 工单拆分
  → 小七(调度员)      排期 + 指派
  → 灵霄(开发工程师)  实现 P0-1~P0-4
  → 灵鉴(审查官)      审 code diff
  → 灵验(测试工程师)  跑 e2e + workflow + cold-start
  → 小七(验收员)      确认 Dashboard 任务链显示正确
```

**灵昭 deliverable：**
1. 确认 P0 优先级排序
2. `init_pipeline_chain` 设计方案（API + tracker 改动点）
3. inbox 积压清理策略（哪些 agent、截止日）
4. 工单列表（每项含：文件路径、验收标准、负责 agent）

**验收标准（灵验执行）：**
- [ ] scan 后 pipeline_trigger 日志出现 `[pipeline] xxx 完成 -> 审查官(lingjian)`
- [ ] Dashboard /api/tasks 中 chain 为步骤对象，status 随流转更新
- [ ] 新建测试任务从 lingzhao 走到 lingyan 无人工干预（或仅 1 次 scan 周期内）
- [ ] e2e + cold-start + monitor-regression 仍 100% PASS

---

## 六、mailbus 下发命令草案（确认后执行）

```bash
# 1. 创建 pipeline 任务
curl -X POST http://127.0.0.1:9812/api/tasks/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "mailbus-hardening-20260616",
    "summary": "mailbus 工作流 P0 完善：pipeline 接入 + chain 统一 + inbox 减负",
    "assignee": "lingzhao",
    "deliverable": "plans/mailbus-hardening-plan.md",
    "chain": ["lingzhao","xiaoqi","lingxiao","lingjian","lingyan","xiaoqi"]
  }'

# 2. 即时推送给灵昭（建议改用 /api/send-msg 或修复后的 instant send）
cd /mnt/e/ai_tools/mail
python3 -m bus send lingzhao --data-dir store --from mailbus --type task \
  --msg "【mailbus-hardening-20260616】请阅读 plans/2026-06-16-mailbus-hardening-inventory.md，输出修复方案与工单拆分，结果写入 msg-results/。"
```

---

## 八、ES 日志查询看板（子言建议 — 纳入 P1）

**目标：** 7 天归档后的 JSONL/日志可在 mailbus 面板全文检索。

**推荐架构：**
```
store/archive/{agent}/*.jsonl  ──bulk──▶  Elasticsearch (单节点 Docker)
store/cron.log / logs/*.log    ──bulk──▶  index: mailbus-logs-*
                                      ▲
mailbus GET /api/logs/search?q=   ─────┘
Dashboard「日志查询」Tab
```

**优点：** ES 擅长归档日志全文检索、时间范围过滤、agent/task_id 聚合；与现有 FTS5 消息搜索互补。

**P0 先做：** 7 天归档 + cron.log 结构化（已有 archive_all）  
**P1 灵昭方案后灵霄实现：** docker-compose 加 elasticsearch:8.x + Filebeat/自写 bulk 脚本 + `/api/logs/search`

---

## 九、用户确认项（2026-06-16）

- [x] 先做 P0，保证工作流执行
- [x] 归档周期 **7 天**（非 3 天）
- [x] ES 日志查询 — 同意方向，P1 实现，灵昭出详细方案
- [x] Cursor 持续监控 + 卡顿修复

