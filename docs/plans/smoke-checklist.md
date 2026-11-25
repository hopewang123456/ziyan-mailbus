# 后端联调 Smoke 测试清单

> 2026-11-25 · v1.0
> 范围：Mailbus 前端 `web/` ↔ 后端全量联调
> 前置：后端 B1.5+ 全部就绪、`VITE_API_MODE=real`、关闭 mock
> 关联：[frontend-execution-plan.md](./frontend-execution-plan.md) / [contract-matrix.md](./contract-matrix.md)

---

## 0. 联调前置条件

| # | 检查项 | 通过标准 |
|---|---|---|
| 0.1 | 后端 B1.5 起的所有域已启动 | `/api/health` 返回 200，`schema_version` 与前端期待一致 |
| 0.2 | `VITE_API_MODE=real`（关闭 mock） | 前端 build 时不再启用 `src/mocks/` |
| 0.3 | 四个测试身份已就绪 | super / supervisor / staff / readonly 各一份 token |
| 0.4 | 浏览器硬刷新 + 清 localStorage | 避免上次 mock 残留的 `mailbus.screen`、`mailbus.token` |
| 0.5 | 后端日志窗口打开 | 任意 5xx 现场可见 |

---

## 1. 身份与权限（console-access / permissions）

| # | 操作 | 期望 |
|---|---|---|
| 1.1 | 无 token 访问 `/console/*` | 重定向 `/login`，不发任何业务请求 |
| 1.2 | 错误 token 访问 | `/api/identity/me` 返回 401 → 清 token + 跳登录 |
| 1.3 | super 登录 | 五组导航全部可见 |
| 1.4 | supervisor 登录 | 仅见本数据范围内的页（无 system_config、无 log_read 菜单项） |
| 1.5 | staff 登录 | 只见概览/任务/工作流；组织、Agent、审计隐藏 |
| 1.6 | readonly 登录 | 页面可见但所有写按钮 disabled |
| 1.7 | 直接输入无权限 URL（如 staff 访问 `/console/audit`） | 显示 `RequirePermission` 403 占位 |
| 1.8 | token 在另一标签页登出 | 当前标签页收到 `auth-required` 事件 → 跳登录 |

---

## 2. 组织（F1）

| # | 操作 | 期望 |
|---|---|---|
| 2.1 | 员工 Tab 列表加载 | 返回 `{items,total,limit,offset}`，四条计时字段是 ISO 字符串 |
| 2.2 | 员工搜索 + 状态筛选 + 团队筛选 | 查询参数被正确序列化，结果数变化 |
| 2.3 | 员工抽屉打开 → 四 Tab 切换 | 档案/角色技能/权限/工位联系人；第四 Tab 显示"待后端"占位 |
| 2.4 | 邀请员工（默认 staff，data_scope=self） | 明文 invite code 仅显示一次，复制按钮可用 |
| 2.5 | 撤销邀请 | 410 错误码被 `lib/api.ts` 正确归类 |
| 2.6 | 岗位 Tab 列表 + 新建 + 编辑 | 名称/说明写入 `PositionIn`，保存后列表刷新 |
| 2.7 | 角色 Tab + 21 权限编辑器 | 仅展示当前用户可授权子集；勾选用 `templatePermissions` |
| 2.8 | 角色绑定员工 | POST binding 返回 200，绑定列表刷新 |
| 2.9 | 团队 Tab + 工位分配 | 冲突工位返回 409 + 后端 reason 字段透传 |
| 2.10 | 删除仍被引用的岗位/团队 | 409，文案透传后端 message |

---

## 3. Agent（F1）

| # | 操作 | 期望 |
|---|---|---|
| 3.1 | Agent 列表加载 + 在线状态列 | `online` 按心跳判定，不等于 `enabled` |
| 3.2 | Agent 详情抽屉 | token 仅显示指纹；endpoint 待审批状态可见 |
| 3.3 | endpoint 审批通过 / 拒绝 | 状态机变化；拒绝时 reason 必填 |
| 3.4 | token 轮转 | 完整 token 仅回显一次，再次进入只显示指纹 |
| 3.5 | token 吊销 | 仅 `console_admin` 可见此按钮；其他角色 403 |
| 3.6 | 软注销 Agent（带活跃 run） | 409，错误文案透传 |
| 3.7 | 邀请码列表（三页签：未用 / 已用 / 已撤销） | 状态切换；过期项置灰 |
| 3.8 | 创建邀请码 + 复制 | 一次性明文展示 |

---

## 4. 工作流（F2）

| # | 操作 | 期望 |
|---|---|---|
| 4.1 | 工作流列表加载 | 卡片显示最新版本 + 已发布版本 |
| 4.2 | 新建工作流 | 自动落到 `v1` 草稿，跳编辑器 |
| 4.3 | 编辑器加载 Graph | nodes/edges 渲染，节点坐标正确 |
| 4.4 | 添加六类节点（agent/human/approval/condition/join/final_approval） | 节点图标 + 类型 label 正确 |
| 4.5 | 拖拽连线 + 删除连线 | edges 数组同步更新 |
| 4.6 | 节点属性面板编辑 | name/seq/max_loops/max_retries 等写回 graph |
| 4.7 | 保存 Graph（首次） | PUT `/graph` 返回 200，revision +1 |
| 4.8 | 并发场景：A/B 两标签页各改一次后保存 | 第二个保存返回 409，前端弹出"服务端 revision=N" + 强制覆盖按钮 |
| 4.9 | 强制覆盖 | revision 用服务端返回值重新 PUT，成功 |
| 4.10 | 校验（`POST /validate`） | 错误列表按节点定位展示 |
| 4.11 | 发布（`POST /publish`） | 已发布版本号更新；运行中任务版本不变 |
| 4.12 | clone 已发布版本 | 创建新草稿版本 |

---

## 5. 任务中心（F3）

| # | 操作 | 期望 |
|---|---|---|
| 5.1 | 三 Tab 切换（全部 / 我的工作 / 审批） | URL `?tab=` 同步；角标来自 summary |
| 5.2 | 筛选 state / owner / workflow | 参数序列化正确 |
| 5.3 | 认领任务 | 成功返回 200；并发认领返回 409 → 列表刷新 |
| 5.4 | 任务详情四 Tab | 概览节点 Run 列表完整；trace 时间线按 `at` 升序 |
| 5.5 | 提交结果（带 attempt_no） | 成功 → run 状态推进；stale attempt_no 返回 409 |
| 5.6 | rerun-join | body 含 `fanout_group` 与缺失 slot 范围；409 表示不允许 |
| 5.7 | 取消任务 | 弹 ConfirmDialog → reason=manual；活跃 run 返回 409 |
| 5.8 | 变量 / 产物 Tab | 当前显示占位（待后端扩 DTO），不应崩溃 |
| 5.9 | 四类终止原因展示 | manual / timeout / failed / cancelled 各有独立标签 |

---

## 6. 消息（F4）

| # | 操作 | 期望 |
|---|---|---|
| 6.1 | 消息列表 + 筛选（inbox/room/type） | 参数透传 |
| 6.2 | 发送消息对话框 | body=`MessageIn`；成功后插入列表顶部 |
| 6.3 | 详情抽屉 + trace | trace 列表按时间排序 |
| 6.4 | SSE 实时插入 | 后端推 `mailbus:message` 事件 → 列表自动新增 |
| 6.5 | 删除消息 | 仅 message_send 权限；只读角色按钮 disabled |

---

## 7. 审计 / 概览 / 指标（F4）

| # | 操作 | 期望 |
|---|---|---|
| 7.1 | 审计列表 + 筛选 | actor/action/target 参数透传 |
| 7.2 | 审计详情抽屉 | detail JSON 完整 |
| 7.3 | 概览页快照 | 全部数字与 `/api/overview` 一致 |
| 7.4 | 指标 7d/30d/自定义切换 | trend 返回 buckets 数量正确 |
| 7.5 | SVG 趋势图渲染 | 折线连续、x/y 轴标签正确 |
| 7.6 | breakdown 排行 | 进度条按最大值归一化 |
| 7.7 | CSV 导出 | 文件下载，`downloadFile` 410 时自动重签一次 |
| 7.8 | 告警规则启停 | PATCH rules 写回 |

---

## 8. 协同大屏（F5 管理端）

| # | 操作 | 期望 |
|---|---|---|
| 8.1 | 屏幕列表加载 | 来源/在线/最后心跳字段完整 |
| 8.2 | 新建屏幕 | 当前 fallback 走 `/api/public/collab/screens`；后端补直连后切换 |
| 8.3 | 编辑布局 + 分配 seat | PUT `/api/seats/{id}/assign` 成功 |
| 8.4 | 发布屏幕 | `expected_config_version` 匹配则成功，否则 409 |
| 8.5 | 聚焦屏幕 | 大屏立即聚焦到该屏幕 |
| 8.6 | 删除屏幕 | 仅 `console_admin`；正在使用的屏幕 409 |
| 8.7 | 结对管理：结束 pair | POST `/pairs/{id}/end` 成功 |
| 8.8 | 协同消息按 screen 筛选 + 发送 | body=`CollabMessageIn` |

---

## 9. 孪生 `/twin`（F5 公开端）

| # | 操作 | 期望 |
|---|---|---|
| 9.1 | 匿名 kiosk 进入 | 不弹登录；只读视图 |
| 9.2 | 登录后进入交互模式 | 加载 screen config + seat tasks |
| 9.3 | 5 分钟无操作 | 自动退回 kiosk |
| 9.4 | `?preview=1` | 不调用 `registerScreen`，无 secret 写入 localStorage |
| 9.5 | 公开投影字段白名单 | DOM 中无 `team`、`endpoint`、`token`、`creator` 字段 |
| 9.6 | reduced-motion 系统开启 | 结对人偶动画禁用 |
| 9.7 | 心跳 | 每 30s 一次，请求头带 `X-Screen-Secret`（mock 阶段跳过验证，后端 B6 后启用） |
| 9.8 | 离开页面 | `leaveScreen` keepalive 调用 |
| 9.9 | 刷新页面 | localStorage `mailbus.screen` 复用同一 screen_id，不重复注册 |

---

## 10. 横切关注点

| # | 检查 | 通过标准 |
|---|---|---|
| 10.1 | 所有列表接口 | 返回 `{items,total,limit,offset}`；空数组 + total=0 |
| 10.2 | 所有时间字段 | UTC ISO 8601 字符串，前端 `formatTime` 本地化显示 |
| 10.3 | 错误码映射 | 0/400/401/403/404/409/410/422/429/5xx 分别进入 `lib/api.ts` 对应 kind |
| 10.4 | 401 自动处理 | GET/HEAD 请求 401 → 清 token + auth-required 事件 + 重试一次 |
| 10.5 | 写失败 toast | 任意写操作失败 → `ConsoleToastHub` 收到 `mailbus:write-failed` |
| 10.6 | AbortController | 快速切换路由 / 筛选，旧请求被 abort，无 late-setState 警告 |
| 10.7 | 竞态丢弃 | 快速连续触发 useQuery，仅最后一次生效 |
| 10.8 | 大屏公开端无敏感字段 | DOM 检查无 token/secret/creator/team_id |

---

## 11. 验收门禁

| 命令 | 通过 |
|---|---|
| `npm run typecheck` | 0 错误 |
| `npm test` | 全通过 |
| `npm run build` | 成功，无 warning |
| `npm run gen:types` + `git diff --exit-code` | 无漂移 |
| 1280×800 / 1024×768 真实浏览器逐页验收 | 无横向滚动，无截断 |
| 关闭 mock 跑通 1.x ~ 9.x 所有用例 | 全部通过，无 fallback 路径被意外触发 |

---

## 使用建议

- **联调节奏**：建议按域推进（§1 → §2 → §3 → …），每域通过后在前端代码里把对应域的 mock fallback 关掉，再进入下一域。
- **失败定位**：任意用例失败先看后端日志，再看前端 DevTools Network 面板的请求/响应；错误码映射异常时优先怀疑后端返回结构偏离 `ApiError`。
- **fallback 提醒**：清单中标了"fallback"的项（如 §8.2）表示前端临时走了兜底路径，后端补直连后须验证直连路径并删除 fallback。
- **重跑机制**：每完成一轮修复，回到 §11 验收门禁重跑一遍，确认无回归。
