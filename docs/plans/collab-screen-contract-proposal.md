# 协同大屏契约补齐方案（前端提给后端）

> 2026-11-25 · v1.0
> 提出方：前端执行窗口
> 依据：[frontend-requirements.md](../design/frontend-requirements.md) §6.1（协同大屏与孪生展示，已冻结）
> 现状代码：[screen.py](../python/mailbus/api/schemas/contract/screen.py)、[screens.py](../python/mailbus/application/collab/screens.py)、前端 [ConsoleCollabPage.tsx](../../web/src/pages/console/ConsoleCollabPage.tsx)
> 性质：契约补齐提案，不涉及前端已确认需求的变更。三项取舍已与需求方确认，见文末「已确认决策」。

## 背景：前端被卡住的三件事

1. 管理端没有读取单块屏幕草稿配置的接口，编辑器只能用已发布配置回填，未发布的草稿改动有被覆盖的风险。
2. `ScreenDraftIn` 只有 `config` 和 `play_state`，需求要求的「重命名」无法保存；前端编辑框里的名称目前保存后不生效。
3. `ScreenConfigIn.grid` / `custom` 是 `dict[str, Any]`，字段未定义，三种布局无法按同一结构实现。

## 变更 A：新增屏幕详情读取

`GET /api/collab/screens/{screen_id}`，权限 `console_admin`。

| 场景 | 响应 |
|---|---|
| 正常 | 200 `ScreenDetailOut` |
| 屏幕不存在 | 404 |
| 无权限 | 403 |

新 schema `ScreenDetailOut`（不改 `ScreenOut`，列表保持轻量）：

| 字段 | 类型 | 说明 |
|---|---|---|
| screen_id | string | |
| name | string | |
| source | string | `auto / manual` |
| online | bool | |
| last_seen_at | datetime \| null | UTC ISO 8601 |
| play_state | string | 与 `ScreenOut` 保持一致 |
| config_version | int | 发布乐观锁使用 |
| published_config_version | int \| null | |
| config | ScreenConfigIn \| null | **草稿**；从未配置为 null |
| published_config | ScreenConfigIn \| null | 已发布；从未发布为 null |

示例：

```json
{
  "screen_id": "scr_01",
  "name": "一层前台大屏",
  "source": "manual",
  "online": true,
  "last_seen_at": "2026-11-25T14:00:00Z",
  "play_state": "playing",
  "config_version": 7,
  "published_config_version": 5,
  "config": { "layout_type": "office", "theme": "auto", "resolution": "1920x1080", "team_id": null, "grid": null, "custom": null },
  "published_config": { "layout_type": "office", "theme": "dark", "resolution": "1920x1080", "team_id": null, "grid": null, "custom": null }
}
```

## 变更 B：`ScreenDraftIn` 支持重命名

在现有模型上加一个可选字段，不新增端点：

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string \| null | 新增。提供时重命名 |
| config | ScreenConfigIn \| null | 现状：缺省表示草稿不变 |
| play_state | "playing" \| "paused" \| null | 现状 |

语义约定：

- `name` 去首尾空白；结果为空或长度超过 50 返回 **422**。
- **只改名字时不推进 `config_version`，也不产生未发布草稿**，否则重命名会迫使重新发布。
- `config` / `play_state` 缺省语义不变。
- 三个字段全部缺省返回 **422**。
- 重命名视为接管：`source` 置 `manual`，审计记 `screen.renamed`。
- 允许重名，`screen_id` 是唯一身份；列表同时展示名称与 ID。

## 变更 C：定义 grid 与 custom 结构

原则：**存储结构**与**读取结构**分离。配置里只存管理员真正设置的内容，需要实时数据的部分由服务端在读取时生成，不持久化。

### C.1 grid：只存参数

存储（草稿与发布配置内）：

| 字段 | 类型 | 约束 |
|---|---|---|
| max_rows | int | 1–20 |
| max_cols | int | 1–20 |
| sort_by | "name" \| "position" \| "seat" | 姓名 / 岗位 / 工位 |

```json
"grid": { "max_rows": 6, "max_cols": 8, "sort_by": "name" }
```

读取时（变更 A 的详情接口、公开配置 `PublicScreenConfigOut` 都一样）注入 `cells`：

```json
"grid": {
  "max_rows": 6, "max_cols": 8, "sort_by": "name",
  "cells": [
    {
      "seat_id": "1F-A-03",
      "row": 0,
      "col": 2,
      "agent": {
        "display_name": "…", "position": "…", "agent_name": "…",
        "status": "busy", "task": "…", "task_state": "running",
        "current_node": "…", "node_state": "…",
        "progress_done": 2, "progress_total": 5
      }
    }
  ]
}
```

- `cells` 由服务端按绑定团队成员生成并排序，**不落库**；管理端预览与大屏因此天然一致。
- `agent` 复用公开布局已有的工位投影，白名单不变：不含 `employee_id / agent_id / team_id / team / endpoint / token / created_by`。
- 未绑定团队时保存返回 **422**；公开端此时 `team_bound=false` 且 `grid=null`，前端显示「请先绑定团队」。
- 前端不自行生成网格，也不新增公开团队成员接口。

### C.2 custom：与现有 layout.json 同构

```json
"custom": {
  "floors": [
    {
      "floor_id": "f-1",
      "name": "一层",
      "level": 1,
      "rooms": [
        {
          "room_id": "r-lobby",
          "name": "大厅",
          "kind": "reception",
          "x": 0, "y": 0, "w": 700, "h": 450,
          "seats": [ { "seat_id": "1F-A-03", "x": 120, "y": 80, "rotation": 0 } ]
        }
      ]
    }
  ]
}
```

- 坐标系沿用现有楼层网格 1400 × 900，字段与前端 `Floor / Room / Seat` 对齐，渲染复用同一舞台组件。
- `custom` **只存工位坐标，不存员工**；工位与员工的绑定仍走现有 `/api/seats/{id}/assign`，避免两处真相。
- **只能移动现有工位**，`seat_id` 必须已存在；不支持在 custom 里新建或删除工位。
- `floor_id` / `room_id` 由前端生成，同一配置内唯一；`kind` 沿用现有 `reception / bullpen / focus / meeting / lounge`。

校验（不满足返回 422）：

| 规则 | 说明 |
|---|---|
| level 为整数且同配置内不重复 | |
| floor_id / room_id 同配置内唯一 | |
| 坐标与宽高非负 | x / y / w / h / rotation |
| 同一 seat_id 不得出现在两个房间 | |
| seat_id 必须存在于座位表 | 未知工位 422 |
| 空布局发布 | 后端已有，保持 |

## 已确认决策

| 问题 | 结论 |
|---|---|
| grid 工位数据由谁生成 | 服务端生成，读取时注入 `cells`，不持久化 |
| custom 能否增删工位 | 只能移动现有工位；楼层与房间可增删 |
| 屏幕名称能否重复 | 允许重名，用 `screen_id` 区分 |

## 不在本次范围

- 屏幕自动登记、心跳、`X-Screen-Secret`、离线删除 409、登记限流 429 / 503：沿用现有契约与需求 §6.1.1，本提案不改动。
- `/twin` 展示逻辑、布局编辑器交互：前端内部实现，不需要后端配合。

## 释放条件

1. 上述三项进入 `contract-matrix.md` 并标注冻结，OpenAPI 重新导出。
2. 前端重新生成 `contracts.ts` 后按本提案重做 `/console/collab` 与 `/twin`。
3. 联调时重点验证：草稿读取与已发布配置的差异展示、只重命名不推进版本、grid 未绑团队 422、custom 未知工位 422、预览与大屏同源。
