# Phase 1: Domain Routing + Project Field — 详细设计

## 概述

实现灵昭拍板的两个改造：
1. **registry.json** — 独立于 config.json 的 agent 注册表，支持 domains 路由
2. **Models** — Message 顶层加 `project: str` 可选字段
3. **bus.py** — `--domain` 参数支持，查 registry 展开收件人列表
4. **scanner.py** — routing 展开兼容
5. **测试**

## 一、registry.json schema

**路径**: `store/registry.json`

```json
{
  "version": "1",
  "agents": {
    "灵犀": {
      "domains": ["engineering", "security", "research"],
      "role": "前沿技术研究员",
      "skills": ["web-reach", "arxiv", "ziyan-mailbus", "..."]
    },
    "灵昭": {
      "domains": ["engineering"],
      "role": "技术负责人/架构师",
      "skills": ["writing-plans", "test-driven-development", "..."]
    },
    "小七": {
      "domains": ["operations"],
      "role": "调度员",
      "skills": []
    }
  }
}
```

### 设计原则
- 一个 agent 可以 belong to 多个 domain
- domains 字段可以为空（不影响现有总线功能）
- role 和 skills 是元数据，供后续"发信给角色"模式使用，Phase 1 不启用
- registry.json 不存在时，`--domain` 退化为无效果，不影响现有功能

## 二、Message.project 字段

### 改动点: `lib/models.py`

在 Message dataclass 的 `forward_chain` 之后、`state` 之前插入一行：

```python
project: Optional[str] = None  # 所属项目（如 "mailbus", "paperclip"）
```

### 序列化兼容
- `to_dict()`: 如果 project 为空，不输出（保持现有 JSON 干净）
- `from_dict()`: 将 `project` 加入 known 字段集合

### 影响
- `build_message()` 在 `lib/utils.py` 加一个 `project: str = ""` 参数
- 所有调用 `build_message()` 的地方（send/broadcast）不需要立即改，默认传空

## 三、bus.py — `--domain` 参数

### send 子命令新增

```
bus.py send <agent> --msg <内容> [--domain <domain>] [--project <project>]
bus.py send --domain engineering --msg "关于数据库迁移"  # 发给所有 engineering domain 的 agent
```

### 路由逻辑

```
if --domain 指定:
  1. 读取 store/registry.json
  2. 查找所有 agents 中 domains 包含该 domain 的
  3. 展开为 to 列表（去重）
  4. 逐个写入 inbox → 实际上就是批量 send 的语法糖
```

### 广播新增

```
bus.py broadcast --domain engineering --msg "...
```

只发给该 domain 下的 agent，而非全员。不接触 broadcast（广播板是全局的）。

## 四、scanner.py 兼容

scanner.py 扫 inbox 时只关心 `status == PENDING` 的消息，不 care 消息怎么来的。所以 routing 展开写入的 inbox，scanner 看到的就是普通 pending 消息。**不需要改 scanner 逻辑**。

但有一处要考虑：ack 处理。当一个消息从 `--domain` 展开到 N 个收件人时，每个收件人各自发各自的 ack。scanner 已经能处理多 agent 独立 ack，无需改动。

## 五、代码清单

### 修改文件

| 文件 | 改动 |
|------|------|
| `lib/models.py` | Message 加 `project` 字段；to_dict/from_dict 兼容 |
| `lib/utils.py` | build_message 加 `project` 参数；新增 `load_registry()`, `resolve_domain_to_agents()` |
| `bus.py` | `send` 子命令加 `--domain` `--project` 参数；`broadcast` 加 `--domain` 过滤 |
| `lib/commands.py` | `cmd_send`, `cmd_broadcast` 实现 domain 路由逻辑 |

### 新增文件

| 文件 | 用途 |
|------|------|
| `store/registry.json` | demo 注册表数据（团队全员） |

### 测试文件

| 文件 | 用途 |
|------|------|
| `tests/test_registry.py` | 测试 registry 加载、domain 解析、project 字段序列化 |

## 六、registry.json demo 数据

```json
{
  "version": "1",
  "agents": {
    "灵犀": { "domains": ["engineering", "research"], "role": "前沿技术研究员", "skills": [] },
    "灵昭": { "domains": ["engineering"], "role": "技术负责人/架构师", "skills": [] },
    "灵霄": { "domains": ["engineering"], "role": "架构师", "skills": [] },
    "灵曦": { "domains": ["engineering", "security"], "role": "安全工程师", "skills": [] },
    "小七": { "domains": ["operations"], "role": "调度员", "skills": [] },
    "大力": { "domains": ["engineering"], "role": "编码工程师", "skills": [] },
    "大壮": { "domains": ["engineering"], "role": "审查工程师", "skills": [] },
    "一哥": { "domains": ["operations"], "role": "运营家", "skills": [] },
    "mailbus": { "domains": ["system"], "role": "消息总线", "skills": [] }
  }
}
```
