# 后端执行计划（Python + Java 同构）

> 2026-11-25 · v1.1（按 4 项结构决策重写）
> 主规格：[agent-unification-design.md](../design/agent-unification-design.md) v4.1
> 迁移基线：[migration-review.md](../design/migration-review.md)
> 前端侧：[frontend-execution-plan.md](./frontend-execution-plan.md)
> 范围：`python/`、`java/`、`shared/contracts/generated/`、`config/`；**不改 `web/`**。

---

## 0. 单一驱动链（本轮新增，最高优先级）

采用 **DDL → OpenAPI → TS 类型**，禁止各层自行定义字段。

| 层 | 唯一事实源 | 规则 |
|---|---|---|
| 持久化 | 034/035/036 迁移 DDL | 双端同编号、同内容、同哈希；字段只在此定义 |
| 用例/DTO | 冻结后的字段归属表 | DTO 只能引用归属表已有字段，不得新增同义字段 |
| 传输 | `python tools/export_openapi.py` 输出 | `shared/contracts/generated/openapi.json` 是唯一 wire 契约 |
| 前端类型 | 从 OpenAPI 生成 | 前端不手写 DTO；生成脚本与 CI 校验由前端计划落地 |
| Java | 按同一 OpenAPI | Java DTO 手写，但必须通过双端 parity 测试 |

**CI 必须拦住三类变更**：

1. 改了路由/字段但没重新导出 OpenAPI；
2. DDL 有列、字段归属表没有登记；
3. Java 响应结构与 Python 不一致。

---

## 1. 防乱五件套（编码前必须先填）

### 1.1 契约矩阵（按域填）

> 完整列定义、填写示例、各域骨架、覆盖清单与 CI 判定见 [contract-matrix.md](./contract-matrix.md)。本节只保留摘要。

| 页面/按钮 | 接口 | 请求 DTO | 响应 DTO | 权威表.列 | 权限 |
|---|---|---|---|---|---|
| 组织·员工列表 | `GET /api/employees` | query | `EmployeeOut` | `identity_employees` | `org_manage` |
| … | … | … | … | … | … |

> 矩阵外的接口与字段不允许实现；矩阵由后端维护，前端只消费。

### 1.2 状态机（唯一口径）

| 实体 | 合法状态 | 迁移约束 |
|---|---|---|
| task | `pending / running / blocked / done / cancelled / failed` | 只由引擎与 result 推进；取消写 `termination_reason` |
| run | `pending / running / done / failed / cancelled` | stale attempt 返回 409 |
| node | `pending / running / blocked / done / failed` | 扇出按 `fanout_group + fanout_slot` 独立 |
| screen | `online / offline` + `playing / paused` | `paused` 仅停新配置 |
| approval | `pending / approved / rejected / expired` | 仅 `final_approval` |

### 1.3 字段归属表（防止同一字段两处存）

| 字段 | 唯一来源 | 禁止出现的位置 |
|---|---|---|
| 屏幕团队 | `config_json.team_id` | 单独列、公开响应 |
| 屏幕布局参数 | `config_json.layout_type/theme/resolution` | 重复列 |
| 播放状态 | `config_json.play_state` | 单独列 |
| 屏幕密钥 | `collab_screens.secret_hash` | 列表、公开响应、日志 |
| 任务进度 | 由 run 聚合计算 | 任务表冗余列 |
| Graph | `wf_nodes + wf_node_transitions` | `wf_versions.nodes` 仅只读历史 |

### 1.4 DTO 分层（禁止平行复制）

- `Base`：共享字段唯一来源（如 `SeatAgentBase`）。
- `Admin`：`Base` + 管理字段（如 `agent_id/team`）。
- `Public`：`Base` 的白名单子集，**不得复制字段后再删**，用组合/投影函数。
- `Detail`：引用列表 DTO，不展开重复字段。

### 1.5 单一实现清单（同一能力只允许一处）

| 能力 | 唯一落点 |
|---|---|
| 屏幕登记/心跳/密钥校验 | `application/collab/screens.py` |
| 屏幕配置读取/发布 | 同一 `ScreenService`，管理端与公开端共用 |
| 公开投影 | `api/mappers/layout.py` 的 public 投影函数 |
| 权限判断 | `core/identity/policy.py` |
| Token 加解密 | `adapters/security/token_cipher.py`（新建） |
| 任务推进 | `application/task/engine.py`（唯一入口） |
| 限速/SSE 容量 | `adapters/ratelimit/` 端口 + 内存适配器（预留 Redis） |

---

## 2. 迁移规范（停机破坏式）

1. **维护窗口**：停服 → 备份 → 迁移 → 校验 → 启动；不做在线双写。034/035/036 只在**发布窗口**对生产库执行一次；开发/测试库可提前迁移，生产库不在域开发中途迁移。
2. **034 重建**：`task_node_runs` 在单事务内建新表、迁数据、删旧表、改名、重建索引；保留 run_id/result/artifacts 引用。
3. **036 不可逆**：`secret` 改名 `secret_hash` 并清空旧明文；设备需重新登记。发布前必须公告。
4. **双端一致**：Python 与 Java 文件逐字节一致；CI 比对哈希。
5. **校验**：每步后 `PRAGMA integrity_check`、`foreign_key_check`、`schema_version` 一致。
6. **禁止**：Spring/Flyway 改写迁移内容；禁止用 SQL 伪造加密/哈希。
7. **时间戳**：新表一律 `TEXT` ISO 8601 UTC；旧 REAL 表由适配层转换，DTO 输出保持 ISO。

---

## 3. 域切片模板（每个域都按此 7 步）

1. 在契约矩阵登记该域接口与字段；
2. 确认 DDL 已包含所需列，缺列先补迁移（不夹带业务改动）；
3. Python：core 模型 → application 用例 → 端口 → adapters → api 路由；
4. 运行 `python tools/export_openapi.py`，检查 diff；
5. **立即**做同域 Java 同构 + parity 测试；
6. 前端按生成的 TS 类型接入（不等待全部后端完成）；
7. 删除该域旧路由/旧 DTO/旧表引用，grep 验证无残留。

> 不允许“先把 Python 全部写完、最后集中改 Java”。

### 3.1 并行隔离（Java / 多窗口）

- 允许按域并行：每个线程/窗口只改自己域的文件，互不阻塞。
- 迁移 SQL、OpenAPI 导出、路由汇总注册属于共享文件，只由整合线程最后合并；并行线程不得直接改。
- 每个并行线程使用独立分支或工作树，禁止跨域改文件、禁止同时编辑同一文件。
- 容器、缓存、限速器、SSE 闸门等共享状态必须线程安全；禁止跨线程复用请求作用域对象。
- 每域合并前单独跑该域 parity 与测试，全部合并后再跑全量。

---

## 4. 阶段与任务

### B0：基线、备份与驱动链

- [x] 备份生产库，`integrity_check` 通过；记录迁移前 schema、权限行数、Agent / 员工 / 大屏规模。
- [x] 核对 001–036 双端哈希一致（B9 执行时扩展核对到 036，全部一致）。
- [x] 落地 OpenAPI 导出与 diff 校验脚本；约定字段归属表、契约矩阵、状态机位置。
- [x] 确认 `MAILBUS_TOKEN_ENCRYPTION_KEY` 注入方式；缺失 fail fast（`container.start()` 调用 `token_cipher.require()`）。
- [x] 建立双端 parity 测试骨架。

**门禁**：驱动链可执行；矩阵/状态机/归属表模板已建；备份可打开。

### B1：DDL 冻结（034 / 035 / 036，先落开发/测试库）

- [x] `034_final_contract_alignment.sql`：扇出唯一键与 `fanout_slot`、`wf_versions.revision`、软删除、endpoint 审批、token 密文与 lookup 索引、邀请字段。
- [x] `035_collab_screen_layout.sql`：`source/config_json/published_config_json/config_version/updated_at` + 索引 + 旧屏回填 `manual`。
- [x] `036_collab_screen_secret_hash.sql`：`secret` → `secret_hash`，清空旧明文。
- [x] 双端同编号、同内容；测试库副本迁移到 schema 36。
- [x] 生产库保持未迁移，直到 B8 发布窗口统一切换；开发期用测试库副本验证。

**门禁**：旧 run 全部 `fanout_slot=0`；库内无明文 token/secret；`integrity_check` 通过。生产库未被提前迁移。

### B1.5：契约桩（解除前端阻塞，先于 B2）

目标：**不写业务逻辑、不动库**，只把 30+ 个冻结端点与 DTO 形状落到 Python 路由与 OpenAPI，供前端生成类型。

- [x] 按 [contract-matrix.md](./contract-matrix.md) 补齐组织、工作流、任务、Agent、大屏管理、审计告警的路径与 Pydantic schema。
- [x] 统一列表包装、错误结构、`X-Screen-Secret` 头、`{graph,revision}`、`Screen*` DTO 与公开投影白名单。
- [x] 未实现逻辑统一返回 501 `{error_code:"NOT_IMPLEMENTED"}`，不返回假数据、不接数据库。
- [x] 旧路由保留但标 deprecated；新路径是唯一契约，前端只调新路径。
- [x] 执行 `python tools/export_openapi.py` 并提交 `shared/contracts/generated/openapi.json`；契约矩阵对应行从 `待填` 改 `冻结`。
- 本阶段不做 Java 同构、不做迁移；Java 在各域 B2–B7 跟进。

**门禁**：
- 前端可 `gen:types` 生成 `contracts.ts`，30+ 路径与 DTO 无缺失；
- OpenAPI 的 path+method 与矩阵 100% 一致；
- 新导航只引用新路径，旧路径不出现在契约中。

### B2：组织域（Python → Java）

- 21 权限枚举；`/api/employees|positions|teams`；`/api/options/*`；分页/UTC/错误结构。
- 软删除过滤与活跃 run 409；邀请上界三处复核；410 规则。
- DTO 去重：`TeamOut` 只保留一处，`EmployeeOut` 作为唯一员工投影。

- [x] Python：21 权限枚举、35 个组织域端点、分页/UTC/错误结构、`EmployeeOut.permissions` 唯一投影。
- [x] 软删除过滤、活跃 run 409、工位占用 409、Agent 无岗位 422、邀请上界三处复核、邀请撤销/过期/已用 410。
- [x] Java 同构：仓储对齐 schema 36（`identity_permission_grants` / `employee_capabilities` / `deleted_at`）、`Authz` 21 权限、`OrgAdminController` 35 端点、`EmployeeView.permissions`。
- [x] 旧 `/api/identity/*`、`/api/org/*` 暂保留，新路径为唯一契约，旧路径统一在 B8 删除。
- [x] 门禁：Python guards + B2 e2e 30 passed；Java `mvn test` 通过（含组织域契约用例）；OpenAPI 与契约矩阵 148 一致。

**门禁**：四类身份可用；越权 403；双端响应一致；契约矩阵该域全绿。

### B3：工作流域（Python → Java）

- 六类节点；Graph `{graph,revision}`；发布校验（显式 join、终验零/一回边）；`wf_versions.nodes` 只读。
- 编辑器所需选项接口、diff、clone、软删除。

- [x] Python：六类节点枚举、Graph 读写（`wf_nodes`+`wf_node_transitions`）、`{graph,revision}` 乐观锁、force 覆盖 +1 并写 `ops_audit_log`、validate 不落库、clone、版本分页、软删除与审计。
- [x] 发布强制校验（旧线性版本按 `nodes` 非空且 `revision==1` 跳过）、失败 422 带 `errors`、已发布版本 409、重复发布幂等。
- [x] Java 同构：`WorkflowGraphRepository`、`WorkflowGraphValidator`、`WorkflowService`/`WorkflowController`、`ApiException`/`ApiError` 输出 `errors`/`revision`。
- [x] 门禁：Python guards + `tests/e2e/test_workflow_graph.py` 6 passed；OpenAPI `--check` 与契约矩阵 148 一致；Java `mvn test` 通过（含 `workflowGraphContractParity`）。

**门禁**：交互稿第 16 节后端项通过；force 覆盖 +1 且写审计；双端一致。

### B4：任务域（Python → Java）

- 自由任务、claim CAS、result `attempt_no`、cancel 四类原因、rerun-join、升级、产物。
- 终验通过/驳回；missing 分片不自动推进。

- [x] Python：`Flow` 唯一推进 + `Fanout` 扇出/汇聚/分片重试、自由任务即启动、claim CAS、stale attempt 409、四类取消原因、终验审批（驳回有回边回退、无回边终止）、失败重试耗尽转人工、missing 不自动推进、`rerun-join` 写 `ops_audit_log`、超时两级升级与自动终止。
- [x] Python 读侧：列表 `{items,total,limit,offset}`、汇总角标、详情 run 投影（`dispatched→running`、`waiting_human→pending`）、`task.updated` 9 字段事件、产物下载 410。
- [x] Java 同构：`TaskRepository`、`TaskGraph`、`TaskFlow`、`TaskStaff`/`TaskConditions`、`TaskService`/`TaskController`、`ApprovalService` 列表与终验委托、调度器超时清扫。
- [x] 门禁：Python `tests/e2e/test_task_domain.py` 9 passed；`tests/guards` 13 passed；OpenAPI 155 path 与契约矩阵 148 一致；Java `mvn test` 12 passed（含 `taskDomainEngineParity`：认领/终验通过/驳回意见必填/失败转人工/扇出缺片 rerun-join 审计/取消原因）。

**门禁**：设计第 10 节 1–10、29–33、38 条；双端一致。

### B5：Agent 与 A2A 域（Python → Java）

- `/api/a2a/messages` 单入口；幂等 `run_id + attempt_no`。
- Token 密文 + lookup digest + 轮转/吊销；endpoint 待审批 + SSRF。
- Agent 注册记录长期保留，不因离线或长时间无心跳自动删除；运行态仍按心跳判在线/离线，离线宽限、run 失败与重派照旧；仅协同端删除才移除记录。
- 6 个 Agent 回归准备（切换前单独确认）。

- [x] Python：`/api/a2a/messages` 单入口（heartbeat/result/message/ack），`run_id + attempt_no` 幂等（重复结果 201 `duplicate`、过期/冲突 409 `stale_run`）。
- [x] Python：AES-GCM token 密文 + HMAC lookup digest（`enc:<base64url>`）；轮转 24h 宽限、吊销立即 401；endpoint 待审批 + SSRF 防护（拒绝 metadata/link-local/userinfo）；注册记录长期保留、仅软删除；心跳 180s 判在线。
- [x] Python：`pick_candidates` 对待审批/被拒/离线/软删除 Agent 不派单；`/api/a2a/messages` 与 `/api/agents/register` 免登录入口，A2A 由 Agent token 自校验。
- [x] Java 同构：`Agent`/`AgentRepository`/`TokenCipher`/`EndpointGuard`/`AgentService`/`AgentRegistrationService`/`AgentA2AService`/`AgentController`/`A2AController`/`AgentInviteController`；`TaskStaff` 增加 Agent 派单门禁；`AuthFilter` 放行两个公开入口。
- [x] 门禁：Python `tests/e2e/test_agent_a2a.py` 3 passed、`tests/e2e/test_task_domain.py` 9 passed、`tests/guards` 13 passed；OpenAPI 148 path 与契约矩阵一致；Java `mvn test` 13 passed（含 `agentA2ADomainParity`：注册/密文非明文/SSRF 422/待审批不派单/审批+心跳派单/幂等/409 `stale_run`/轮转/吊销）。
- [x] 既有 Agent 回归准备（切换前单独确认）：B8 用生产库副本演练，Agent 心跳全部 201。

**门禁**：日志/库/界面无明文；待审批不派单；双端一致。

### B6：大屏域（Python → Java）

- 公开登记/心跳/离线/配置/布局/SSE；Header `X-Screen-Secret`；哈希校验；限速 10/min、上限 64。
- 限速与 SSE 容量走端口抽象（`RateLimiterPort` / `StreamGatePort`），本期内存实现；为后续 Redis 适配保留接口，不引入 Redis 依赖。
- 管理端接管、保存草稿、发布 `config_version+1`、聚焦、删除。
- 公开投影删除 `team`；`admin` 与 `public` 共用 `ScreenService`。

- [x] Python：`ScreenService` 统一承接公开与管理工作流；密钥仅存 SHA-256 摘要，登记响应只回显一次；`X-Screen-Secret` 校验，心跳/离线幂等。
- [x] Python：`RateLimiterPort`/`StreamGatePort`/`SecretHasherPort` 端口化，本期内存实现；登记按 IP 10/min、在线屏幕上限 64（503）。
- [x] Python：草稿 last-write-wins + 审计；发布 `expected_config_version` CAS（409 `version_conflict`），空布局 422；`play_state` 即时生效不进版本；聚焦离线 409、删除在线 409。
- [x] Python：公开配置/布局只读已发布快照，剔除 `team_id` 与 `team`；未知 `screen_id` 404；公开 SSE 白名单移除 `screen.registered`。
- [x] Python：自动登记屏仅在未被接管且离线 30 天后由维护任务清理；删除旧明文回填工具。
- [x] Python 门禁：`test_collab_screens.py`、`test_screen_limits.py`、`test_public_stream_scrub.py`、`test_sse_limits.py`、`tests/guards` 共 26 passed；OpenAPI 148 path 与契约矩阵一致。
- [x] Java 同构：`ScreenDtos`/`ScreenRepository`/`ScreenSecretHasher`/`ScreenRateLimiter`/`ScreenService`/`CollabController`；`LayoutService.getPublic(teamId)` 与 `PublicSeatAgentOut` 去 `team`；公开布局按 `screen_id` 已发布团队过滤；`StreamGate` 共享 SSE 容量、公开流白名单剔除 `screen.registered`。门禁：`mvn test` 16 passed（含 `collabScreenLifecycle` B6 parity）。

**门禁**：6.1.5 全部异常码；公开白名单测试；`paused` 语义；前端 F5 可联调。

### B7：指标、审计、告警、技能、集成（Python → Java）

- [x] Python：指标 overview/trend/breakdown/CSV 与 `data_scope` 同口径；审计列表/详情 diff/CSV；告警状态流转、规则 CRUD/test、`silence_seconds` 冷却与通知重试；邀请码校验顺序；集成路由。
- [x] Java 同构：报表 scoped SQLite 聚合与 CSV；ops 审计/告警/通知（含 SMTP）；集成/env/reload 与邀请码；技能包沿用既有双端实现。
- [x] 门禁：Python B7 定向 e2e + guards 31 passed，OpenAPI/矩阵 148 个 path+method 一致；Java `mvn -q -o clean test` 18 passed（BackendSmokeTest 15 + AuthzOfflineTest 3）。

**门禁**：前端 F1/F4/F5 所需字段全部在契约中；`MetricPointOut` 只保留一处。

### B8：全量回归与清理

- [x] 重新导出 OpenAPI；校验与上一版差异均已在矩阵登记。
  - `python tools/export_openapi.py --check` → 契约一致；`python tools/check_contract_matrix.py` → 149 个 path+method 一致。
  - 本轮重新导出补登了 B4 已实现但未导出的 `ArtifactOut` 与 `TaskDetailOut.artifacts`（字段归属已登记）；其余删除项均为 `include_in_schema=False` 旧别名，不产生 path 变化。
- [x] 删除旧 `/api/identity/*`、`/api/org/*`、`/advance`、`/dispatch`、旧 DTO、旧表引用。
  - Python：删除 `api/routers/org.py`（`/api/org/*` 全部）；`identity.py` 删除 `POST /staff`、`GET /staff/{id}`、`/review`、`/activate`、`/deregister`、`PATCH /staff/{id}/seat|agent|endpoint|manager`、`POST /invites`；`tasks.py` 删除 `POST /{task_id}/dispatch`、`/{task_id}/advance`。
  - Java：删除 `org/OrgController.java`；`IdentityController` 删除同组旧端点；`TaskController` 删除 dispatch/advance，`TaskService` 删除对应死代码，`TaskDtos.TaskAdvanceIn` 删除；`AuthFilter` 移除已不存在路由的公开白名单。
  - 例外（web 仍在调用，按用户决策保留）：`GET /api/identity/staff`、`POST /api/identity/staff/{employee_id}/heartbeat`。
  - 旧 DTO/死代码：Python 与 Java 的旧 staff 申请、审核、激活、注销、工位/Agent/endpoint/manager DTO 与 service 方法已删除；旧 `InviteService`、申请/邀请 DTO、`TaskAdvanceIn`、`AdvanceCommand`、旧任务 dispatch/advance 实现均已清除。保留的 bootstrap/me/heartbeat 与新 OrgAdmin 邀请不受影响。
  - 旧表引用：本轮未删除任何表；034/035/036 的旧列/旧表在迁移中已处理，无运行时代码继续读取。
- [x] 全量 guards/e2e/integration + Java test + 双端 parity。
  - Python：`python -m pytest tests/e2e tests/guards tests/integration -q` → 152 passed。
  - Java：`mvn -q -o test` → 20 passed（BackendSmokeTest 15 + AuthzOfflineTest 3 + ContractStubsTest 2）。
  - 迁移测试覆盖：真人邀请/接受、员工软删除、团队/岗位/工位新契约、Agent 注册/审批、任务创建即启动。
- [x] 生产库副本演练：迁移、完整性、既有 Agent 心跳与 A2A。
  - 源库为发布前一致性副本（schema 14，含既有 Agent）；用 SQLite backup API 复制到临时目录后启动应用。
  - 结果：`schema_version=36`、`integrity_check=ok`、`foreign_key_check=[]`、Agent token 全部 `enc:` 密文、`collab_screens` 无 `secret` 旧列。
  - 既有 Agent 经 `/api/a2a/messages` 心跳全部 201。
- [x] 输出发布清单：迁移顺序、环境变量、回滚点。
  - 迁移顺序：`034_final_contract_alignment.sql` → `035_collab_screen_layout.sql` → `036_collab_screen_secret_hash.sql`；Python/Java 同编号同内容，先备份后迁移，停机窗口内执行一次。
  - 环境变量：`MAILBUS_TOKEN_ENCRYPTION_KEY` 必须提供（32 字节 base64/文本），缺失 fail fast；登录入口与 Agent 注册使用的域名/端口按部署环境配置。
  - 回滚点：迁移前完整备份（含 WAL）；034/035 可通过恢复备份回滚；036 不可逆（`secret` → `secret_hash` 明文清空），发布前需公告设备重新登记。
  - 发布后校验：`/api/health` schema_version=36、`PRAGMA integrity_check`、Agent 心跳、公开大屏登记/心跳。
- [x] B8 遗留清零：实现 C-014 Agent 解绑与 C-100 任务追迹的 Python/Java 同构；路由层无 501 桩；旧身份集成测试已迁移到 Agent 注册/审批/禁用链路，旧 DTO 与 service 死代码无残留。

### B9：生产发布与验收（已执行，待用户验收）

目标：在明确维护窗口内完成唯一一次生产切换，使生产库到 schema 36，双端运行同一 OpenAPI 契约，并完成核心链路验收。

- [x] 发布前确认：用户授权执行；本次运行栈为 Python；回滚由用户确认。
- [x] 发布前确认：`MAILBUS_TOKEN_ENCRYPTION_KEY` 已生成并按约定方式注入运行进程，不落盘、不进命令行；缺失 fail fast。
- [x] 补齐 B0 基线：发布前完成一致性备份；001–036 双端迁移哈希一致。
- [x] 发布候选冻结：Python 152 项与 Java 20 项全绿；`export_openapi.py --check` 与契约矩阵 149 个 path+method 一致。
- [x] 停服并做发布前完整备份；副本试迁移通过后对生产库执行 015–036（034/035/036 已包含），`schema_version=36`、`integrity_check=ok`、`foreign_key_check=[]`。
- [x] 启动发布候选并完成服务端 smoke：`/api/health` 200（schema 36）、bootstrap completed、OpenAPI 117 paths、`/api/public/layout` 200、未登录 `/api/collab/screens` 401、公开大屏 register/heartbeat/config/SSE/leave 全通过。
- [x] 验证既有 Agent：全部签发 token，库内均为 `enc:` 密文且有 lookup digest、明文 0；Agent A2A 心跳全部 201。
- [x] 验证 web 只读：登录页正常渲染；大屏页面正常渲染、无错误覆盖层；前端代理返回 schema 36。
- [x] 记录回滚点与结果：036 已执行；回滚需恢复发布前备份并回滚旧包，同时公告设备重新登记。
- [ ] 用户验收：登录后关键写链路验收待完成。

**职责边界（按 2026-11-26 澄清）**

- Mailbus 只负责在自身运行环境内监听并就绪，不承诺多平台部署适配。
- 其它 Agent/平台运行在 Windows、Linux、WSL、Docker 或任意外部环境，如何打通到 Mailbus 由其自行负责：端口映射、防火墙、反向代理、VPN 等均属调用方部署范畴。
- `MAILBUS_TOKEN_ENCRYPTION_KEY` 只要求以环境变量注入；自启动、密钥托管（systemd、env file、secret manager）由部署方按自身环境选择，不作为 Mailbus 缺陷。

**执行后遗留（不阻塞本次切换，但需跟进）**

1. 验收环境中宿主网络转发失效属部署方配置范畴；服务本身在运行环境内正常监听。
2. 前端 `/twin` 在无 Bearer token 时不发起屏幕登记（`shouldRegister` 依赖 `hasToken`），匿名页面会停留在“实时待连接”；后端公开登记/心跳/SSE 已独立验证通过。该项属于前端计划，与跨环境通信无关。

**门禁**：生产 schema 36、完整性与外键检查通过、Agent 心跳通过、服务端与公开大屏 smoke 通过、回滚点可用；用户验收待完成。

---

## 5. 已知重复的治理项（必须完成）

| 项 | 处理 |
|---|---|
| `TeamOut` 两处 | 合并为单一 DTO，另一处改为引用 |
| `MetricPointOut` 两处 | 合并到 metrics 域单一 DTO |
| `SeatAgentOut` / `PublicSeatAgentOut` | 抽 `SeatAgentBase`，公开端只做投影 |
| `Layout*Out` / `PublicLayout*Out` 四层复制 | 同上，公开端组合而非复制 |
| `ScreenView.secret` | 删除该字段，登记响应单独 DTO 返回一次性明文 |
| 屏幕登记逻辑 | 后端只保留 `ScreenService` 一处 |
| `wf_versions.nodes` 与 `wf_nodes` | 前者只读历史，Graph 只走后者 |

---

## 6. 交付物

- [ ] 双端 034/035/036
- [ ] 契约矩阵、状态机、字段归属表（按域填满）
- [ ] 重新导出的 `shared/contracts/generated/openapi.json`
- [ ] Python + Java 同域实现与 parity 测试
- [ ] 旧路径与重复 DTO 删除记录
- [ ] 迁移演练与回滚点
