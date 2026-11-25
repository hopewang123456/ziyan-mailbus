# 迁移脚本评审（015–030）

> 2026-11-24 · 评审对象：设计文档 9.1 规划的 015–030
> 方法：只读检查现有迁移、两份运行时（Python / Java）、生产库 `data/mailbus.db` 实况
> 配套：[agent-unification-design.md](./agent-unification-design.md) 第 9 章
> 最终补充：034（最终跨端契约）与 035（大屏配置）已在第 7 节列入实施清单，但**尚未创建或验证**；013–033 的既有 parity 结论不覆盖它们

---

## 1. 结论

评审已完成并落地：015–030 按结论产出，双端文件一致，生产库副本与全新库均验证到 schema 30；剩余工作是 Phase 2 代码层同步。

- **原硬阻塞已解**：Java 013/014 已补齐。
- **已落实到脚本**：017 RENAME（含 invites）、019/020 自动补 start、021 完整回填、027 环境变量、新表 REAL 时间戳、029 token 唯一索引、018/023/024 调度与查询索引、030 历史 cancelled 回填。
- **遗留（非阻塞）**：`task_node_runs / task_variables / task_escalations` 未加外键，按设计依赖应用层清理（Java 侧未开 `PRAGMA foreign_keys`）；后续可统一补。

**落地状态（2026-11-24）**：Java 013/014 已补齐；013–033 双端共 21 个文件哈希一致；已在「生产库副本」与「全新库」验证到 schema 33（grants 18 行、旧版本生成 `start → 收集资料 → 执行分析`、坐标 0/240/480；新增 `short_fanout`、`msg_messages.task_id`、`agent_registration_invites`、`ops_alerts` / `ops_alert_rules`）。当前 Python/Java 业务代码仍引用旧表名，**迁移不可单独部署**，须与 Phase 2 代码改名同批上线。

现状基线（只读实测）：

| 项 | 实测 |
|---|---|
| Python 迁移 | 001–014（14 个） |
| Java 迁移 | 001–**012**（缺 `013_indexes.sql`、`014_collab_screen_secret.sql`） |
| 生产 schema 版本 | 14 |
| 工作流 | 1 个已发布版本，**2 个节点**（收集资料、执行分析），JSON 线性结构 |
| 任务 | 0 个 task、0 个 task_node、0 个审批 |
| 员工/Agent | 6 个 agent 员工、14 个 agents 外壳（6 个 hermes_profile 已绑定） |
| 权限 grants | 18 行；邀请 0 行；岗位 0 行；团队 0 行 |
| JSON1 | Python SQLite 3.50.4 可用；Java sqlite-jdbc 3.46.1.3 内置 JSON1 |
| 时间戳 | 现有表全部 `REAL`（epoch 秒）；新 DDL 全部 `TEXT`（ISO） |

---

## 2. 逐文件评审

| 序号 | 结论 | 主要问题与建议 |
|---|---|---|
| 015 | 需修改 | `agent_type` / `channel_type` 用默认值覆盖全部 14 行，其中 8 个未绑定外壳会被标成 `service/a2a`。建议：默认值保留，但对 `framework='hermes_profile'` 显式置 `a2a`，其余按实际接入方式 UPDATE；`last_seen_at` 已统一为 `REAL`。 |
| 016 | 通过 | `pending_task_count INTEGER NOT NULL DEFAULT 0` 可直接加；现有 6 行自动为 0。 |
| 017 | 已定方案 | 设计 3.2 与 9.1 口径已统一为 `RENAME TABLE` + `RENAME COLUMN`（SQLite ≥3.25，双端满足），保留 18 行与 `granted_at`；并补 `identity_invites.capabilities → permissions`。 |
| 018 | 需修改 | 6 张表可建。缺调度必需索引：`employee_capabilities(capability)`、`employee_role_bindings(role_id)`、`position_role_bindings(role_id)`、`position_employee_assignments(position_id)`。`employee_capabilities.capability` 是**业务技能**，不要跟着 017 改名，建议在列注释里写明。 |
| 019 | 已定方案 | 旧版本只有 `{node_id,name,order}`，没有 start。已确认：插入合成 `start`（`seq=0`，`position_id NULL`），旧节点 `seq=order+1`、`node_type='agent'`、`position_id=NULL`；坐标 `x=(order+1)*240, y=120`。JSON1 双端可用。 |
| 020 | 需修改 | 线性边规则需覆盖合成 start：`start → 首节点 → 次节点`。建议补索引 `(workflow_id, version, to_node_id)` 供入度/回边校验。条件为空。 |
| 021 | 已定方案 | 设计已补「旧任务回填」。已确认完整回填：每个 `task_nodes` 生成 `attempt_no=1` 的 run，`pending→pending / running→running / done→done`，活跃节点 `assigned_employee_id = task_tasks.owner_id`，再写 `current_run_id`。 |
| 022 | 通过 | PK `(task_id,var_key)` 合理；建议 `source` 加 `CHECK (source IN ('input','system'))`。 |
| 023 | 需修改 | 补索引：`task_node_artifacts(task_id)`、`(run_id)`；`task_node_artifact_edits(artifact_id)` 已有 FK，但需显式索引（SQLite 不自动建）。 |
| 024 | 需修改 | `org_teams.leader_employee_id` 可加（当前 0 行）；补索引 `task_escalations(task_id, resolved_at)`。`reason` 注释补 `no_matching_branch` 之外的新值需与 4.6/5.6 对齐（当前 4.6 走终止，不进 escalation，注释可不改）。 |
| 025 | 通过 | `skills_packages` 已存在，`provides_capabilities TEXT NOT NULL DEFAULT '[]'` 即可。 |
| 026 | 通过 | 默认 `'{}'`，0 任务无回填。 |
| 027 | 已定方案 | 「归档配置」原无落点。已确认：只加 `archived_at REAL`，保留天数读 `MAILBUS_TASK_ARCHIVE_DAYS`（默认 30），Java 读同一环境变量，不新建配置表。 |
| 028 | 通过 | `level INTEGER NOT NULL DEFAULT 1`；0 行无回填。 |
| 029 | 需修改 | 两个 nullable 列即可；补 **唯一索引** `agents(endpoint_token)` 与 `agents(endpoint_token_prev)`（token 反查是热路径，且必须唯一）。 |
| 030 | 需修改 | 可空列；建议回填 `state='cancelled'` 的旧任务 `termination_reason='manual'`（当前 0 行，兼容其他部署）。 |

---

## 3. 跨切面问题

### 3.1 Java 迁移落后两个版本（必须先修）

Java 只有 001–012，Python 已到 014。若只补 015–030，Java 部署会缺索引与大屏 secret 列。执行顺序：**先补 013/014 到 Java resources，再同步 015–030**，两份文件保持语义一致（建议直接复制，不做方言改写）。

### 3.2 时间戳类型不一致（已确认统一）

现有库全部 `REAL` epoch（含 `task_tasks.created_at`、`identity_sessions.issued_at`），原设计新 DDL 用 `TEXT` ISO。混用会导致同一任务上 `task_tasks.updated_at`（REAL）与 `task_node_runs.completed_at`（TEXT）无法直接比较/排序。

**已确认**：015–030 新表统一 `REAL` epoch，与双端现有仓储一致；设计文档 DDL 已同步改完。

### 3.3 外键与清理

`task_nodes` 有 `ON DELETE CASCADE`，但新表 `task_node_runs / task_node_artifacts / task_escalations / task_variables` 均无外键。若后台维护任务物理清理会留孤儿数据，建议统一加 `REFERENCES task_tasks(task_id) ON DELETE CASCADE`，并确认双端连接已开 `PRAGMA foreign_keys=ON`。该建议仅用于内部维护；最终产品契约中任务前台只有取消，不提供物理删除。

### 3.4 执行器差异

- Python：整文件包在 `BEGIN IMMEDIATE … COMMIT`，失败回滚；脚本内**不要**再写 `BEGIN/COMMIT`。
- Java：Spring `ScriptUtils` 按 `;` 分句执行，整个文件一个事务。019 回填含 JSON 字符串，当前 2 个节点名无分号，但需约定**迁移数据里不出现分号**，否则 Java 会截断。
- 双端都不支持 down migration：只提供备份/恢复与 017 的反向 SQL。

### 3.5 回填测试数据不足

生产库只有 1 个 2 节点版本、0 任务，无法验证 019–021 的回填分支。实施前需准备一份**合成测试库**：含 3 节点线性版本、运行中/已完成任务、task_nodes、18 条 grants、1 条未消费邀请。

---

## 4. 已确认决策（2026-11-24）

1. **旧版本 start 节点**：迁移时自动补合成 `start` 节点，旧节点 `seq=order+1` 并铺坐标。
2. **归档配置落点**：环境变量 `MAILBUS_TASK_ARCHIVE_DAYS`（默认 30），只加 `archived_at REAL`，不新建配置表。
3. **021 旧任务回填**：完整回填（`attempt_no=1`，状态映射 pending/running/done，活跃节点用 `owner_id`）。
4. **时间戳类型**：新表统一 `REAL` epoch，设计文档 DDL 已同步修改。

---

## 5. 建议的执行顺序

```
0. 补 Java 013 / 014
1. 015 agents 字段（含 hermes 显式 a2a）
2. 016 pending_task_count
3. 017 权限重命名（RENAME，含 invites）
4. 018 角色/技能/绑定表 + 调度索引
5. 019 wf_nodes + 合成 start + 坐标
6. 020 wf_node_transitions + 线性边 + to_node 索引
7. 021 task_node_runs + current_run_id + 旧任务回填
8. 022 task_variables
9. 023 artifacts + 索引
10. 024 escalations + leader
11. 025 skills provides_capabilities
12. 026 loop_counters
13. 027 archived_at（配置走环境变量）
14. 028 escalation level
15. 029 token 轮转字段 + 唯一索引
16. 030 termination_reason + 历史回填
```

每步之后在**测试库副本**上跑：迁移 → 双端启动 → `GET /api/health` schema_version 一致 → 种子链路回归。

---

## 6. 验收清单

- [ ] Python 与 Java 迁移文件编号、内容一一对应，schema_version 相同
- [ ] 017 后 grants 18 行、权限值不变，邀请列已改名
- [ ] 019 后每个旧版本恰有 1 个 start，节点坐标不重叠
- [ ] 020 后旧线性版本边为 start→n1→n2，无孤立节点
- [ ] 021 回填后每个旧 task_node 有且仅有一个 current_run
- [ ] 029 两个 token 列均有唯一索引
- [ ] 新表时间戳类型与现有库一致
- [ ] 后台维护清理任务时 runs/artifacts/escalations 无孤儿；前台无任务物理删除入口
- [ ] 合成测试库全链路通过，生产库副本迁移后 6 个 Agent 心跳/A2a 正常

---

## 7. 最终新增迁移 034（已确认，未实施）

`034_final_contract_alignment.sql` 是最终需求澄清后的新增结构基线，Python/Java 必须使用相同文件编号与语义；不能把它误认为已包含在 013–033 的哈希一致结论中。

### 7.1 DDL 与数据回填清单

1. **扇出 run**：重建 `task_node_runs`，新增 `fanout_slot INTEGER NOT NULL DEFAULT 0`，旧数据全部回填 0；唯一键改为 `(task_id,node_id,fanout_slot,attempt_no)`，补 `fanout_group` 活跃分片查询索引。重建期间保留 run_id、result、attempt、artifacts 引用。
2. **Graph 乐观锁**：`wf_versions.revision INTEGER NOT NULL DEFAULT 1`；旧版本从 1 开始，JSON `updated_at` 不再充当锁。
3. **软删除**：`identity_employees`、`agents`、`wf_defs` 增加 `deleted_at/deleted_by`；默认列表过滤删除标记，历史 run 与审批记录不删除。
4. **endpoint 审批**：`agents` 增加 `pending_endpoint`、`endpoint_review_status`、`endpoint_approved_by/at`；已有可用 endpoint 的迁移状态必须显式记录，切换前 6 个 Agent 仍需逐一审批新 A2A endpoint。
5. **Token 加密与反查**：现有 `endpoint_token/endpoint_token_prev` 改存密文，新增当前/旧 `lookup_hash` 并建立唯一索引；原明文唯一索引不得继续承担入站查询。密文由使用 `MAILBUS_TOKEN_ENCRYPTION_KEY` 的应用迁移步骤生成，SQL 文件本身不保存密钥或明文。
6. **邀请上界与撤销**：`agent_registration_invites` 增加 `data_scope DEFAULT 'self'`；`identity_invites` 增加 `revoked_at/revoked_by`。真人邀请默认 24h、used/revoked/expired 访问 410 由应用层保证。

### 7.2 双端验收补充

- [ ] 旧 run 全量保留且 `fanout_slot=0`；同一节点可写入同 attempt 的多个不同分片，普通节点唯一约束仍防重复
- [ ] 扇出分片独立重试不撞唯一键；按 `fanout_group + fanout_slot` 能找到各槽位最新 attempt
- [ ] Graph 正常保存与 force 保存都递增 revision，旧 `expected_updated_at` 不再被双端接受
- [ ] 员工/Agent/工作流软删除后历史详情可读，有活跃 run 时删除事务返回 409 且不写删除标记
- [ ] 数据库任何 token 字段均无明文；使用配置密钥可解密密文用于出站，lookup digest 可反查入站，日志仅显示指纹
- [ ] 密钥缺失时服务 fail fast，不自动生成或硬编码默认密钥；旧 token 24h 与吊销即时失效规则不变
- [ ] endpoint 待审批期间无新任务投递，批准/拒绝留审计；SSRF、DNS、可信网段测试通过
- [ ] Python/Java 迁移后 schema_version 相同，并共同通过自由任务、显式 join、终验驳回、邀请上界和告警冷却契约测试

### 7.3 新增迁移 035（大屏配置，未实施）

`035_collab_screen_layout.sql` 为孪生/协同大屏的屏幕配置基线，Python/Java 必须同编号、同语义。

1. `collab_screens` 增加 `source TEXT NOT NULL DEFAULT 'auto'`（`auto/manual`）、`config_json TEXT NOT NULL DEFAULT '{}'`、`published_config_json TEXT NOT NULL DEFAULT '{}'`、`config_version INTEGER NOT NULL DEFAULT 1`、`updated_at REAL`。新登记默认 `auto`；迁移时把已有屏幕统一回填为 `manual`，避免被自动清理。管理端任一接管操作（改名、绑定团队、发布）同样置 `manual`。
2. 旧屏幕回填：优先用原 `floor_id/seat_id` 生成最小 `office` 配置并作为初始聚焦；无法解析时置空布局，`config_version=1`；不删除旧列，避免历史读取断裂。
3. 补索引：`collab_screens(last_seen_at)` 供离线判定与清理；`collab_screens(source, last_seen_at)` 供自动登记清理。
4. 配置 JSON 内保存 `layout_type/theme/resolution/team_id/play_state/office/grid/custom`；团队过滤与布局选择由应用层校验，不用 SQL 约束枚举。
5. `/twin` 只读 `published_config_json`；管理端保存只写 `config_json`，发布时快照并递增 `config_version`。
6. 清理只删 `source='auto'` 且离线超过 30 天的屏幕；已接管或已发布屏幕不自动删除。
7. 密钥改哈希：另立 `036_collab_screen_secret_hash.sql`，将 `collab_screens.secret` 重命名为 `secret_hash` 并清空旧明文（现有屏幕强制重新登记），Python/Java 同编号、同语义；035 不依赖密钥语义，可与 036 分开发布。
8. 传输统一：心跳/离线一律读 `X-Screen-Secret` 头，现有 body `secret` 在 036 同批改为头，Python/Java/前端一起切换。

验收补充：

- [ ] 旧屏幕迁移后仍能按原楼层/工位展示，`config_version=1`
- [ ] 发布后 `/twin` 读取新配置，草稿不影响在线屏幕
- [ ] `?preview=1` 不登记、不发心跳、不接收聚焦；目标屏不存在 404
- [ ] 60 秒无心跳判离线；在线删除返回 409；未接管自动屏 30 天后可清理，已接管屏不清理
- [ ] `grid` 未绑定团队保存 422；公开登记超限 429；在线自动屏超 64 台 503；公开 SSE 满 503
- [ ] 登记后库内只有 `secret_hash`，接口仅登记响应返回一次明文，列表与心跳响应不回显

> 完成以上新增迁移和契约实现前，只能称 013–033 旧基线已验证，不能称最终冻结需求已落地。
