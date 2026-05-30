# Paperclip Alignment — Phase 1 完整设计方案

> 设计人：灵昭 | 2026-05-28 | 更新：2026-05-29 v2.1
> 状态：方案稿 — 灵犀 review 通过 ✅ → 已采纳 4 条改进 + Phase 2 合入
> 更新说明：
> - 新增 `validate --fix` 自动修复模式
> - 缓存改为文件 mtime 驱动
> - mailbus-send --project 与 v2 registry 同时上线（不留窗口期）
> - 合入 Phase 2（TaskTracker 串接 pusher/scanner）

---

## 一、背景

灵犀调研 Paperclip 后提出了 mailbus 的四步进化方案。经讨论确认第一步：
**registry.json schema + Message.project 字段 + --domain 路由** 优先实施。

## 二、现状评估（代码已实现部分）

先做快速代码审计，发现 Phase 1 的**大部分基础代码已经存在**：

### ✅ 已完成

| 需求 | 当前状态 | 文件证据 |
|------|---------|---------|
| `registry.json` schema v1 | ✅ 已有 `/mnt/e/ai_tools/mail/store/registry.json` | 7 个 agent 已注册 domain |
| `load_registry()` / `resolve_domain_to_agents()` | ✅ 代码已写 | `lib/utils.py:309-352` |
| `Message.project` 字段 | ✅ 已定义 `Optional[str]` | `lib/models.py:149` |
| `to_dict()` project 兼容 | ✅ 空值不输出 | `lib/models.py:198-199` |
| `from_dict()` project 兼容 | ✅ 加入 known 字段集合 | `lib/models.py:208` |
| `build_message()` project 参数 | ✅ 已有 `project: Optional[str] = None` | `lib/utils.py:243` |
| `bus.py send` + `--domain` | ✅ 路由逻辑已实现 | `bus.py:89-96`, `lib/commands.py:444-511` |
| `bus.py broadcast` + `--domain` | ✅ 过滤逻辑已实现 | `lib/commands.py:525-572` |
| `bus.py send` + `--project` | ✅ CLI 参数 + 写入逻辑 | `bus.py:96`, `commands.py:458,503,508-509` |
| 测试用例 | ✅ 8 个测试全部通过 | `tests/test_registry.py` |

### ❌ 未完成 / 待优化

| 需求 | 状态 | 原因 |
|------|------|------|
| registry.json schema v2（丰富字段） | ❌ 需扩展 | 当前只有 `domains/role/skills` |
| registry 写操作（`bus.py registry add/remove/update`） | ❌ 缺 CLI | 目前只能手动编辑 JSON |
| registry 冗余校验（agent 名与 config.json 一致性） | ❌ 缺验证 | `cmd_send` 会二次过滤，但无显式告警 |
| `mailbus-send` CLI（独立脚本）支持 `--project` | ❌ 未同步 | 独立脚本未更新 |
| API (`/api/registry`) 暴露 | ❌ 缺端点 | dashboard 看不到 registry 数据 |
| Domain 自动补全提示（bus.py send 帮助信息） | ❌ 缺实现 | 输入错误 domain 只报错不提示可用值 |
| registry 内存缓存过期策略 | ⚠️ 粗糙 | 手动 `clear_registry_cache()`，无 TTL 自动刷新 |

## 三、registry.json Schema v2 设计

### 3.1 整体结构

```json
{
  "version": "2",
  "description": "Agent 注册表 — 管理 domain 路由、技能索引、角色映射",
  "updated_at": "2026-05-28T00:00:00+0800",
  "domains": {
    "engineering": { "display_name": "工程研发", "description": "架构设计、编码实现、代码审查" },
    "security": { "display_name": "安全", "description": "安全审计、漏洞扫描、权限管理" },
    "research": { "display_name": "技术研究", "description": "前沿技术跟踪、技术雷达、对比报告" },
    "operations": { "display_name": "运营", "description": "内容运营、社交媒体、日常执行" },
    "system": { "display_name": "系统", "description": "总线、监控、基础设施" }
  },
  "agents": {
    "lingzhao": {
      "display_name": "灵昭",
      "domains": ["engineering"],
      "role": "方案设计/架构师",
      "email": "lingzhao@ziyan.ai",
      "type": "hermes",
      "status": "active"
    },
    "lingxi": {
      "display_name": "灵犀",
      "domains": ["engineering", "research"],
      "role": "技术雷达/研究员",
      "email": "lingxi@ziyan.ai",
      "type": "hermes_profile",
      "status": "active"
    }
  }
}
```

### 3.2 字段说明

| 字段 | 层级 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `version` | 顶层 | string | ✅ | JSON Schema 版本号，递增更新 |
| `description` | 顶层 | string | - | 注册表用途说明，只读元数据 |
| `updated_at` | 顶层 | string | - | 最后修改时间 ISO8601 |
| `domains` | 顶层 | object | - | domain 字典，key 为 domain 名称 |
| `domains.<name>.display_name` | domains | string | ✅ | 中文/可读名称 |
| `domains.<name>.description` | domains | string | - | 领域说明 |
| `agents` | 顶层 | object | ✅ | agent 字典，key 为 agent key |
| `agents.<key>.display_name` | agents | string | ✅ | 可读名称 |
| `agents.<key>.domains` | agents | array | ✅ | 所属 domain 列表（至少一项）|
| `agents.<key>.role` | agents | string | - | 角色描述 |
| `agents.<key>.email` | agents | string | - | 邮箱（Dashboard 邮箱按钮用）|
| `agents.<key>.type` | agents | string | - | agent 类型，与 config.json 对应 |
| `agents.<key>.status` | agents | enum | ✅ | `active` / `inactive` / `suspend` |

### 3.3 设计原则

1. **不重复 config.json 信息** — `display_name`、`email`、`type` 只是元数据可以冗余，但启动配置(launch、profile_paths 等)不放在 registry 里
2. **domain 字典自说明** — `domains` 节让 CLI 能提示可用 domain 和含义
3. **状态管理** — `status` 让不删除 agent 情况下临时"停派"
4. **前向兼容** — v2 解析器兼容 v1 格式（v1 没有 `domains` 字典时自动降级）

## 四、新增模块设计

### 4.1 `bus.py registry` 子命令族

在 bus.py 中新增 `registry` 子命令族：

```bash
bus.py registry list                      # 列出所有注册 agent（含 domain 摘要）
bus.py registry list --domain engineering # 列出某 domain 下的 agent
bus.py registry domains                   # 列出所有可用 domain（含描述）
bus.py registry add <agent> --domain engineering,security --role "xxx"
bus.py registry remove <agent>            # 从 registry 移除（不删 config）
bus.py registry update <agent> --domain research  # 更新字段
```

### 4.2 API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/registry` | GET | 返回完整 registry |
| `/api/registry/domains` | GET | 返回可用 domain 列表 |
| `/api/registry/agents` | GET | 返回 agent ↔ domain 映射表 |
| `/api/registry/validate` | GET | 校验 registry ↔ config 一致性 |

### 4.3 mailbox-daemon 兼容

mailbox-daemon 现在的 `cmd_scan` 和 `_push_queue` 里调用 `build_message()` 时不会传 project。
需要在 mailbox-daemon 的消息处理管线中把 `--project` 传下去。

当前的推送路径是：
1. scanner 发现 pending 消息
2. pusher 调用 CLI 推送（Hermes 类型直接 auto-ack）
3. 推送时消息内容里没有传递 project 信息

这不需要改动 pusher，因为 project 已经在 inbox JSON 的消息 payload 里了。Agent 自己读 inbox 时能看到 project 字段。

## 五、代码变更清单

### 修改文件

| 文件 | 改动 | 工作量 |
|------|------|--------|
| `store/registry.json` | 从 v1 升级到 v2 schema | 小 |
| `lib/utils.py` | `load_registry()` 加 domains 字典缓存；新增 `list_available_domains()` | 小 |
| `bus.py` | 新增 `registry` 子命令 parser | 中 |
| `lib/commands.py` | 新增 `cmd_registry()` 和子函数；增强 `cmd_send` 的 domain 错误提示 | 中 |
| `lib/api/handlers_system.py` | 新增 `handle_registry()` 端点 | 小 |
| `lib/api/base.py` | 注册 `/api/registry` 路由 | 小 |
| `mailbus-send` | 同步支持 `--project` 参数 | 小 |

### 新增文件

| 文件 | 用途 |
|------|------|
| （无新增文件） | 全在现有文件上修改 |

### 测试文件

| 文件 | 改动 |
|------|------|
| `tests/test_registry.py` | 追加 v2 schema 测试、registry CLI 测试、API 端点测试 |

## 六、实施计划

### 6.1 分工建议

| 阶段 | 工作 | 执行人 | 预估 |
|------|------|--------|------|
| P1 | registry.json v1→v2 升级 + 验证测试 | 大力 | 30min |
| P1 | `bus.py registry` CLI 子命令（含 `validate --fix` 自动修复模式） | 大力 | 1h |
| P1 | API `/api/registry` 端点 | 大力 | 30min |
| P1 | `mailbus-send` 加 `--project`（与 v2 registry 同时上线） | 大力 | 15min |
| P1 | 缓存改为文件 mtime 驱动 | 大力 | 15min |
| P2 | domain 错误提示增强（显示可用 domain） | 大力 | 15min |
| P2 | registry v1 兼容性降级测试 | 大力 | 15min |
| **P2** | **TaskTracker 串入 pusher/scanner（代码已写，串起来）** | **大力** | **45min** |
| 全部 | 代码审查 + config_schema 校验 registry | 灵霄 | 30min |
| 全部 | 最终过一眼代码 | 灵犀 | 15min |

> 注：Phase 2（TaskTracker 串接）按灵犀 review 建议合入本轮实施。Tracker 代码（`lib/tracker.py` 148 行）已写，只需在 pusher 和 scanner 中调用。

### 6.2 依赖关系

```
方案 review（灵犀 ✅）→ 大力写代码（registry CLI + API + TaskTracker 串接 + 缓存 mtime）
                              ↓
                         灵霄 code review
                              ↓
                         灵犀 final look
                              ↓
                         合并 + 全量测试通过 + 部署
```

## 七、风险与注意事项

1. **registry ↔ config 一致性**：registry 和 config.json 是两份独立的 agent 列表。`bus.py send` 在 domain 展开后再过滤 config 已注册的（`commands.py:470`），这个行为没问题，但 registry 可能有已删除的 agent 导致静默跳过。加 `bus.py registry validate` 检查。
2. **缓存问题**：`load_registry()` 用全局变量缓存，dashboard 改 registry 后 bus 侧不会感知。改成**文件 mtime 驱动**缓存，每次调用时检查 `os.path.getmtime(registry_path)` 是否大于缓存时间戳，过时则重新加载。相比固定 TTL，registry 文件几乎不变，mtime 驱动更合理。参见灵犀 review 建议③。
3. **mailbus-send 同步**：小七和一哥有时用 `mailbus-send` 发消息，如果不同步加 `--project`，project 字段会丢失。建议在 v2 registry 上线时一起更新。

## 八、后续展望（Phase 3+）

> Phase 2（TaskTracker 串接）已合入本轮（v2.1 更新）。以下为 Phase 3 及之后：

Phase 1+2 完成（registry v2 + CLI + API + TaskTracker 串接 + 缓存 mtime）后可以为后续做好底层设施：

- **Phase 3**: mailbus 消息 → registry.author 归属统计（Dashboard 项目视图）
- **Phase 4**: 角色路由 `--role`（查 registry.agents[].role 匹配，更灵活）
- **Phase 5**: Agent 自检 heartbeat 规范化（registry 的 heartbeat 配置字段）
