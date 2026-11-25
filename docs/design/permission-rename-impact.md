# permission 重命名影响评估

> 2026-11-24 · 范围：权限概念 `capability` → `permission` 全量重命名
> 对象：线上 6 个 hermes Agent（lingzhao / lingjin / lingxi / lingxun / lingtuo / lingzhang）
> 配套：[agent-unification-design.md](./agent-unification-design.md) 第 6 章、9.1 迁移清单
>
> **状态说明（2026-11-25）**：本文是重命名决策的历史评估，文中 `/api/identity/employees`、`/api/identity/staff/{id}/heartbeat` 等路径已被新契约取代（现为 `/api/employees` 等）。保留用于追溯决策，不作为接口契约依据。

---

## 1. 结论

**6 个 Agent 不受行为影响，不需要改配置、不需要重启容器、token 不失效。**

理由是权限数据完全在 mailbus 服务端：Agent 只持有会话 token，token 解析只查 `identity_sessions.token_hash`，权限在每次请求时从 grants 表重新加载。重命名只改表名/列名与 HTTP 字段名，不改权限值（`message_read` / `message_send` / `result_submit` 原样保留）。

破坏面集中在 mailbus 内部与对外 HTTP 契约：
- **破坏性**：`GET/POST /api/identity/employees`、`/api/identity/invites` 的 `capabilities` 字段；OpenAPI 的 `Capability` 枚举；Java 侧 135 处 `Authz.*` 引用。
- **非破坏性**：DB 表/列改名（配合停服）、Python 内部枚举、前端 `Access` 字段、MCP 内部鉴权。
- **配置侧**：`data/hermes-agent-tokens.json` 里的 `capabilities` 键仅作文档用途，heartbeat 只读 `employee_id` 与 `token`，改名可选。

---

## 2. 实测基线（只读查询 `data/mailbus.db`）

| 项 | 实测值 |
|---|---|
| schema 版本 | 14（设计中的 015–030 尚未应用） |
| 6 个 Agent 员工 | `account_type=agent`、`status=active`、`seat_id=f2-bullpen-s1..6`、`position_id=NULL` |
| Agent ↔ 外壳 | 6 条 `identity_employees.agent_id` 均非空；`agents.endpoint=NULL`（A2A 地址来自 `store/config.json`） |
| 权限 grants | 18 行 = 6 人 × 3 项（`message_read` / `message_send` / `result_submit`） |
| 会话 | 6 条；`expires_at=NULL`、`revoked_at=NULL`；`sha256(token)` 与 `data/hermes-agent-tokens.json` 6 个 token **逐一匹配** |
| 邀请 | 0 行（邀请表改名无数据风险） |
| 岗位 | 0 行（`org_positions.capabilities` 为空，按设计保留不读写） |
| 视图/触发器 | 无，`ALTER TABLE RENAME` 可直接执行 |

---

## 3. 影响矩阵

| 层面 | 具体变更 | 性质 | 需要动作 |
|---|---|---|---|
| DB | `identity_capability_grants` → `identity_permission_grants`；列 `capability` → `permission` | 破坏性（旧代码查询会 500） | 停服迁移，数据原样保留 |
| DB | `identity_invites.capabilities` → `permissions` | 破坏性（契约字段） | 随迁移执行；表为空 |
| DB | `org_positions.capabilities` | 保留不动（设计中已废弃） | 无 |
| 会话/鉴权 | token 表、哈希算法、grants 值 | 不变 | 无 |
| Python 核心 | `Capability` 枚举、`policy.py` 判定与错误文案 | 内部 | 改名 + 文案「缺少权限」 |
| Python 持久化 | `identity_repo.py` 5 处 SQL（读/写/按权限查人） | 内部 | 跟随列名 |
| Python API | `EmployeeOut.capabilities`、`InviteIn/Out.capabilities`、OpenAPI `Capability` | **对外破坏性** | 改字段并重生成契约；前端同步 |
| Java | `Authz.java`、`TokenResolver`、`EmployeeRepository`、`OrgService`、`IdentityDtos`、测试 | **对外破坏性** | 按 E14 与 Python 同步交付 |
| 前端 | `ConsoleApp` 的 `access.capabilities` / `can()`；41 处调用（权限值不变） | 低 | 只改字段名与类型 |
| MCP | 4 工具 schema 不含权限名，仅内部 `Authz` 校验 | 无 | 无 |
| 6 个 Agent | 只调 heartbeat（SELF）、A2a 入站（`message_send`）、文件通道 | **无影响** | 无 |
| 配置 | `data/hermes-agent-tokens.json` 的 `capabilities` 键 | 无（sidecar 忽略） | 建议改名保持一致 |
| 测试 | 断言 `capabilities` 字段的用例、OpenAPI 快照 | 低 | 随字段更新 |

---

## 4. 6 个 Agent 逐项

| Agent | employee_id | 接入方式 | 是否读取权限名 | 重命名影响 |
|---|---|---|---|---|
| lingzhao | `emp_7d45…1307` | hermes A2A + file_bus | 否 | 无 |
| lingjin | `emp_2eb5…fe31` | 同上 | 否 | 无 |
| lingxi | `emp_3539…dc38` | 同上 | 否 | 无 |
| lingxun | `emp_de0c…eed7` | 同上 | 否 | 无 |
| lingtuo | `emp_9b6a…c7f4` | 同上 | 否 | 无 |
| lingzhang | `emp_e5ed…00fc` | 同上 | 否 | 无 |

补充说明：
- 心跳响应体虽然是 `EmployeeOut`（含权限字段），但 `shared/docker-agents/heartbeat/heartbeat.py` 只读状态码、不解析 body。
- 6 个 Agent 的 skill / 提示词中没有 `/api/identity/employees` 或 `capabilities` 字段引用。
- 它们的 A2A 地址 `agents.endpoint` 为空，实际由 `store/config.json` 提供，与本次重命名无关。

---

## 5. 迁移步骤（建议维护窗口内执行）

前置：备份 `data/mailbus.db`；确认无正在执行的人工操作。

1. 停止 mailbus API 与 Java 进程（**不可热迁移**，旧代码会查旧表）。
2. 执行新迁移（示例编号 016，实际按批次排定，勿改历史迁移 `002_identity.sql`）：

```sql
ALTER TABLE identity_capability_grants RENAME TO identity_permission_grants;
ALTER TABLE identity_permission_grants RENAME COLUMN capability TO permission;
ALTER TABLE identity_invites RENAME COLUMN capabilities TO permissions;
```

3. 同步部署 Python 与 Java（同迁移版本、同契约文件）。
4. 验证：
   - `select count(*) from identity_permission_grants` = 18，值仍为 3 类
   - 6 个旧 token 调 `POST /api/identity/staff/{id}/heartbeat` 均返回 200
   - 任选一个 Agent 走一次 A2a 推送 → ack → result，节点正常推进
   - 控制台登录后能看到 6 人权限；Java 同路径返回一致
5. Agent 容器无需重启；mailbus 恢复后心跳自动回在线。

**Agent 侧动作：无。** 若希望配置语义统一，可把 `data/hermes-agent-tokens.json` 的 `capabilities` 键改为 `permissions`，heartbeat 不受影响。

回滚：反向执行三条 RENAME，回退双端版本即可；token 仍有效。

---

## 6. 风险与注意事项

1. **停服是硬要求**：迁移窗口内旧进程查询旧表会全部 500，必须停服后执行。
2. **在跑 run 的 90s 宽限**：迁移耗时若超过「离线判定 + 90s 宽限」，在跑 run 会判失败并按 `max_retries` 重派；建议在空闲窗口迁移，或迁移前暂停调度器。
3. **契约破坏**：`EmployeeOut / InviteIn / OpenAPI enum` 改名会影响控制台以外任何消费方；发布前更新 `shared/contracts/generated/openapi.json` 并升契约版本。
4. **Java 锁定同步**：135 处 `Authz.*` 与 3 个仓储类必须与 Python 同版本上线，E14 已明确禁止语义分叉。
5. **不要顺手改 `org_positions.capabilities`**：它是被废弃的业务列，当前为空，保留可避免无意义迁移。
6. **历史迁移不可编辑**：`002_identity.sql` 等已应用脚本只追加新迁移，避免校验和不一致。
7. **文档口径修正**：设计文档原写「迁移后需重启 6 个 Agent 容器并复验 token」，与实测不符，已改为「仅需重启 mailbus，token 不变」。

---

## 7. 验收清单

- [ ] 迁移后 grants 18 行、值不变
- [ ] 6 个旧 token 全部仍可鉴权，无需重新登记
- [ ] 心跳、A2a 推送、ack、result 全链路正常
- [ ] 控制台 6 人权限展示正确，无空白
- [ ] Java 与 Python 同契约、同迁移版本
- [ ] OpenAPI 中不再出现 `Capability` 枚举与 `capabilities` 字段
- [ ] `rg "identity_capability_grants"` 仅命中历史迁移
- [ ] 回滚脚本演练通过
