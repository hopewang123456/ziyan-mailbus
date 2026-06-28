# Hermes Agent 记忆能力基线 v1.0

> 撰写：灵犀（前沿技术研究员）  
> 日期：2026-05-25  
> 版本：v1.0  
> 用途：为灵昭后续的「自建记忆层」决策提供技术基线

---

## 一、工具概览

Hermes Agent 的原生记忆能力由两个独立工具共同组成，定位完全不同：

| 维度 | `memory` 工具 | `session_search` 工具 |
|------|-------------|---------------------|
| **定位** | 持久化**精选记忆**（curated memory） | 跨会话**全文检索**（conversation recall） |
| **数据源** | 用户/Agent 主动写入的要点 | 所有历史会话的 SQLite 全文索引 |
| **容量** | 小（2,200 + 1,375 字符） | 无硬上限（取决于 state.db 大小） |
| **注入方式** | 注入到 system prompt 前缀缓存 | 按需检索 + LLM 摘要 |
| **延迟** | 零（已缓存在 prompt 中） | 中（FTS5 → 摘要 LLM 调用，~5-30s） |
| **存什么** | 用户偏好/环境事实/教训 | 任何历史对话记录 |

**核心设计哲学**：`memory` 是「告诉 Agent 你是谁」，`session_search` 是「帮 Agent 回忆你做过什么」。一个守、一个搜。

---

## 二、memory 工具能力清单

### 2.1 支持的 Action

源码位置：`/mnt/e/hermes-data/.hermes/hermes-agent/tools/memory_tool.py`

| Action | 功能 | 参数 |
|--------|------|------|
| `add` | 追加一条新条目 | `target` + `content` |
| `replace` | 替换包含 `old_text` 子串的条目 | `target` + `old_text` + `content` |
| `remove` | 删除包含 `old_text` 子串的条目 | `target` + `old_text` |
| `read` | 读取（通过返回的 `entries` 字段获得） | 无需额外参数 |

**不支持的 Action**：没有 `list` / `search` / `batch_add` / `batch_remove` / `rename`。当前状态通过每次操作返回的 `entries` 字段暴露。

### 2.2 支持的 Target

| Target | 含义 | 写入文件 | 默认字符限制 |
|--------|------|---------|------------|
| `memory` | Agent 的个人笔记 | `~/.hermes/memories/MEMORY.md` | 2,200 字符 |
| `user` | 用户画像 | `~/.hermes/memories/USER.md` | 1,375 字符 |

> 注意：Profile 隔离机制下，实际路径为 `$HERMES_HOME/memories/`，例如灵犀的路径为 `/mnt/e/hermes-data/.hermes/profiles/lingxi/memories/MEMORY.md`

### 2.3 存储位置与持久化机制

```
存储位置：
  - ~/.hermes/memories/MEMORY.md  (全局 agent 记忆)
  - ~/.hermes/memories/USER.md    (全局用户画像)
  - $HERMES_HOME/memories/MEMORY.md (profile 级记忆)
  - $HERMES_HOME/memories/USER.md   (profile 级画像)

持久化策略：
  - 每次 add/replace/remove 操作后立即写盘（「原子替换」模式）
  - 先用 tempfile 写临时文件，再 os.replace() 原子覆盖
  - 文件锁（fcntl/msvcrt）防止并发写竞争
  - 写盘后不修改 system prompt —— 保持前缀缓存稳定
  - 下次会话启动时才会刷新 system prompt 中的记忆

文件格式：
  - 纯文本，每行以 `§`（U+00A7）分隔条目
  - `§` 本身可以作为条目内部字符（用 `ENTRY_DELIMITER = "\\n§\\n"` 区分）
```

### 2.4 字符容量

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `memory_char_limit` | 2,200 字符 | MEMORY.md 总字符上限（约 800 tokens） |
| `user_char_limit` | 1,375 字符 | USER.md 总字符上限（约 500 tokens） |

容量可以在 `config.yaml` 中调整：
```yaml
memory:
  memory_char_limit: 2200    # ~800 tokens
  user_char_limit: 1375      # ~500 tokens
```

**容量验证**：当前灵犀 Profile 的 MEMORY.md 包含 17 个条目（约 2,000 字符），USER.md 包含 5 个条目（约 700 字符），均在限制范围内。

### 2.5 安全机制

写盘前做安全扫描，拦截以下模式：
- 提示注入（`ignore all instructions`、`system prompt override` 等）
- 角色劫持（`you are now`）
- 凭证外泄（`curl` + 环境变量、`cat .env`）
- SSH 后门（`authorized_keys`）
- Unicode 不可见字符注入（零宽字符等）

### 2.6 匹配逻辑

`replace` 和 `remove` 依赖**子串匹配**，不是 ID 或精确匹配：
- 查找所有条目中包含 `old_text` 的
- 如果找到唯一匹配 → 执行操作
- 如果找到多个**不同**条目 → 返回错误 + 预览，要求更精确
- 如果找到多个**相同**条目 → 操作第一个（去重机制保证重复条目不常出现）

### 2.7 重复检测

写入时自动去重：
- `add` 时检查新内容是否已存在 → 跳过（返回信息但不报错）
- `load_from_disk()` 时用 `dict.fromkeys()` 去重

---

## 三、session_search 工具能力清单

### 3.1 架构概览

```
session_search 的完整流程：

1. 用户/Agent 发起查询
   ↓
2. 查询传入 hermes_state.SessionDB.search_messages()
   ↓
3. DB 用 FTS5 全文索引快速定位匹配消息（最多查 50 条）
   ↓
4. 按 parent_session_id 解析到根会话，去重
   ↓
5. 排除当前会话分支（不再需要 Agent 已有上下文）
   ↓
6. 限制到最多 limit 个独立会话（默认 3，上限 5）
   ↓
7. 取每个匹配会话的完整对话，截取约 100K 字符的匹配窗口
   ↓
8. 并行调用辅助 LLM 生成摘要（max_concurrency=3，上限 5）
   ↓
9. 返回 JSON 结果：{ session_id, when, source, model, summary }
```

### 3.2 搜索语法

底层使用 **SQLite FTS5** 引擎（`unicode61` tokenizer + `trigram` tokenizer for CJK）。

支持的查询语法：

| 语法 | 示例 | 说明 |
|------|------|------|
| 简单关键词 | `docker deployment` | FTS5 默认 AND 语义，所有词必须出现 |
| OR 布尔 | `docker OR kubernetes` | 任意词出现即匹配 |
| AND 布尔 | `python AND java` | 所有词必须出现（默认即 AND） |
| NOT 布尔 | `python NOT java` | 排除含 java 的结果 |
| 精确短语 | `"docker networking"` | 双引号包裹，词序必须一致 |
| 前缀通配 | `deploy*` | 匹配 deploy/deployment/deployed |
| 连字符/点号 | `chat-send` / `my-app.config` | 自动用双引号包裹防 tokenizer 拆分 |

**重要**：工具 Schema 的 description 明确提示「Use OR between keywords for best results — FTS5 defaults to AND which misses sessions that only mention some terms」。

### 3.3 CJK 搜索特殊处理

CJK（中日韩）字符搜索使用独立的 trigram FTS5 表：

```
查询流程：
  含 CJK 字符？
  ├── 是，且 ≥3 个 CJK 字符 + 每个 token ≥3 CJK → 使用 trigram FTS5 表
  ├── 是，但 <3 CJK 或单 token <3 CJK → 用 LIKE %keyword% 回退
  └── 否（纯英文） → 使用默认 unicode61 FTS5 表
```

这一设计保证中文短语（如「大别山项目」）不会拆成单个字的 AND 查询。

### 3.4 参数支持

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `query` | string | 空 | 任意长度 | 省略=最近会话模式 |
| `limit` | integer | 3 | [1, 5] | 返回的最大会话数 |
| `role_filter` | string | 无 | 如 `"user,assistant"` | 逗号分隔的角色筛选 |

**不含的参数**：没有 `source_filter`、`date_range`、`session_id` 过滤、`offset` 分页（这些是 `SessionDB.search_messages()` 底层的参数，但 session_search 工具本身不暴露）。

### 3.5 结果格式

```json
{
  "success": true,
  "query": "memory tool",
  "results": [
    {
      "session_id": "20260525_014900_abc123",
      "when": "May 25, 2026 at 01:49 AM",
      "source": "cli",
      "model": "deepseek-chat",
      "summary": "(LLM 生成的摘要文本...)"
    }
  ],
  "count": 2,
  "sessions_searched": 3
}
```

异常时：
```json
{
  "success": false,
  "error": "Session summarization timed out. Try a more specific query or reduce the limit."
}
```

### 3.6 两种模式

| 模式 | 触发条件 | 行为 | LLM 调用 |
|------|----------|------|----------|
| 最近会话浏览 | `query` 为空/空白 | 返回最近会话的标题+预览+时间戳 | ❌ 零 |
| 关键词搜索 | `query` 不为空 | FTS5 匹配 → LLM 摘要 | ✅ 每个匹配会话调用一次 |

### 3.7 性能限制

| 限制项 | 值 | 说明 |
|--------|-----|------|
| FTS5 单次匹配上限 | 50 条 | 传给 `search_messages(limit=50)` 的硬编码值 |
| 摘要并发数 | `max_concurrency=3` | 可配置 `auxiliary.session_search.max_concurrency`，上限 5 |
| 每会话传输字符上限 | 100,000 | `MAX_SESSION_CHARS`，截取匹配窗口 |
| 摘要模型超时 | 30s | 可在 `auxiliary.session_search.timeout` 调整 |
| 总超时 | 60s | 并发摘要超时，超过返回错误 |
| 会话排除 | 当前会话 + 子代理会话 | 避免重复上下文 |
| 隐藏源过滤 | `source="tool"` 排除 | 第三方集成（Paperclip 等）的会话排除 |

### 3.8 存储数据库

```
路径：$HERMES_HOME/state.db
类型：SQLite + WAL 模式
索引：两个 FTS5 虚拟表（messages_fts + messages_fts_trigram）
触发器：INSERT/DELETE/UPDATE 自动维护 FTS 索引
模式版本：Schema v11
```

---

## 四、能力边界总结

### 4.1 能做什么 ✅

| 能力 | 工具 | 说明 |
|------|------|------|
| 记住用户偏好 | memory → user | 存入 `USER.md`，每次会话自动注入 |
| 记住环境事实 | memory → memory | 存入 `MEMORY.md`，每次会话自动注入 |
| 修改/删除记忆 | memory → replace/remove | 子串匹配，即时生效 |
| 搜索历史对话 | session_search | FTS5 全文检索 + LLM 摘要 |
| 搜索中文内容 | session_search | trigram FTS5 处理 CJK 文本 |
| 最近会话浏览 | session_search（空 query） | 零 LLM 成本，即时返回 |
| 排除当前会话 | session_search | 自动解析父子会话链排除 |
| 外挂记忆插件 | memory.provider 配置 | Honcho、Mem0、Holographic 等 |

### 4.2 不能做什么 ❌

| 能力缺失 | 影响 | 严重程度 |
|----------|------|----------|
| ❌ **无向量语义搜索** | 无法按含义相似度检索，只能精确关键词匹配 | 🔴 高 |
| ❌ **无渐进式记忆分层** | 记忆不分短期/中期/长期，不自动提炼/合并/遗忘 | 🔴 高 |
| ❌ **无自动记忆提取** | Agent 不会从对话中自动提取要点写入记忆；工具 Schema 建议人工做 | 🟡 中 |
| ❌ **无跨会话场景提炼** | 不能自动从多轮会话中提取「场景记忆」（类似 TencentDB 的 L2 层） | 🔴 高 |
| ❌ **无记忆图/知识图谱** | 记忆条目之间无关联，无法形成知识网络 | 🟡 中 |
| ❌ **无时效性/权重** | 无法给记忆打分、设置过期时间、根据使用频率衰减 | 🟡 中 |
| ❌ **无分段存储** | `memory` 只有 2,200+1,375 字符的固定小容量 | 🟡 中 |
| ❌ **无汇聚/冲突解决** | 不同 session 写入的同一话题记忆可能重复或矛盾 | 🟢 低 |
| ❌ **无离线/私有部署的记忆层** | 外挂 Honcho/Mem0 依赖云服务 | 🟢 低 |
| ❌ **无自定义 source/date 过滤** | session_search 参数中没有 source_filter、date_range | 🟢 低 |

---

## 五、与 TencentDB Agent Memory 的能力差距

| 能力维度 | Hermes 原生 | TencentDB Agent Memory | 差距分析 |
|----------|------------|----------------------|---------|
| **L0 原始日志** | ✅ SQLite state.db 全量会话 | ✅ 日志系统 | 持平 |
| **L1 精确检索** | ✅ FTS5 关键词 + 短语 + 布尔 | ✅ 同样支持 | 基本持平 |
| **L2 场景记忆** | ❌ 无 | ✅ LLM 提取 → Markdown 打包 → 重用 | 🔴 **核心差距** |
| **L3 向量语义搜索** | ❌ 需外挂 Mem0 等插件 | ✅ BGE-M3 embedding 原生支持 | 🔴 **核心差距** |
| **记忆分层** | ❌ 扁平 store | ✅ 三层分层（L0-L1-L2） | 🔴 **核心差距** |
| **自动提取** | ❌ 仅人工写入 | ✅ 对话中自动提取事实 | 🟡 中 |
| **记忆冲突解决** | ❌ 无 | ✅ 规则去重 + 时间线排序 | 🟢 低 |
| **跨 Agent 共享** | ❌ 仅 profile 内隔离 | ✅ 单 TT 表多 Agent 关联 | 🟡 中 |
| **时效性管理** | ❌ 无 | ✅ 遗忘曲线 / 过期策略 | 🟡 中 |
| **离线/私有部署** | ✅ 纯本地 | ✅ PostgreSQL + embedding 可私有 | 持平 |
| **显存/算力要求** | ✅ 零 | ❌ 4060 8GB 跑不动 BGE-M3 | Hermes 胜出 |

### 5.1 关键差距详解

**差距 1：无自动场景记忆提取**
- TencentDB 的 L2 场景记忆工作流：对话进行 → LLM 自动提取「场景描述+关键信息」→ 写入 Markdown 文档 → 下次类似场景自动注入
- Hermes 目前完全依赖 Agent 人工判断何时调用 `memory add`。工具 Schema 虽然鼓励这么做（"do this proactively, don't wait to be asked"），但无强制机制

**差距 2：无向量语义搜索**
- FTS5 只能匹配**精确的关键词**。如果查询词和记忆内容用词不同（同义词、上位词），FTS5 会错过
- TencentDB 用 BGE-M3 embedding 做语义匹配，支持跨语言和同义词搜索
- Hermes 虽然有 Honcho/Mem0 等外挂插件支持 embedding，但需要配置云服务（Honcho）或 API Key（Mem0）

**差距 3：无记忆分层**
- Hermes 的 `memory` 是扁平的：全部 2,200 字符一股脑注入 system prompt，无优先级区分
- 理想的分层应该是：高频短记忆（注入 prompt）← 中频记忆（按需检索）← 长期记忆（惰性召回）

---

## 六、未来自建记忆层需要补什么

如果团队要自建记忆层（而不是用 TencentDB 或 Honcho/Mem0），以下是补全建议：

### 6.1 优先级 P0（缺失即不可用）

| 需求 | 建议方案 | 依赖 |
|------|---------|------|
| **向量 embeddings** | 本地 `sentence-transformers` (all-MiniLM-L6-v2 仅需 ~400MB RAM) 或 在线 API（OpenAI text-embedding-3-small） | pip install sentence-transformers |
| **向量数据库** | SQLite 自带 FTS5 已有，embedding 可另存为 BLOB+余弦相似度计算；或用轻量 ChromaDB | ChromaDB pip 安装即可 |
| **自动记忆提取** | 每轮对话后用辅助 LLM 提取关键事实，自动 `memory add` + 向量化写入 | 已有 session_search 的辅助 LLM 可用 |

### 6.2 优先级 P1（区别出专业与玩具）

| 需求 | 建议方案 |
|------|---------|
| **记忆分层** | L0=全量原始日志（state.db 已有）、L1=高频要点（现有 memory 文件）、L2=场景记忆（Markdown 打包 + 条件注入） |
| **记忆冲突解决** | 同一关键词/实体下多条记忆 → 时间线排序 + LLM 合并 + 冗余去重 |
| **时效性/权重** | 每条记忆附加 `score` 和 `last_accessed`，基于遗忘曲线衰减，定期压缩 |

### 6.3 优先级 P2（锦上添花）

| 需求 | 建议方案 |
|------|---------|
| **跨 Agent 共享记忆** | 统一数据库（如 shared-memory 目录已有）+ Profile 间读写隔离 |
| **session_search 增强** | 暴露 source_filter、date_range 参数；支持分页 offset |
| **记忆可视化** | Dashboard 上显示记忆容量使用率、最近写入 | 

### 6.4 不需要自己做的

Honcho 和 Mem0 已经封装好了完整的内存层能力（语义搜索 + 自动提取 + 分层记忆），需要时可以直接启用（`memory.provider: "mem0"` 或 `"honcho"`），不需要从头造轮子。

---

## 七、附录

### 7.1 相关源码位置

| 文件 | 功能 |
|------|------|
| `tools/memory_tool.py` | memory 工具实现（586 行） |
| `tools/session_search_tool.py` | session_search 工具实现（612 行） |
| `hermes_state.py` | SessionDB + FTS5 实现（2,966 行） |
| `agent/memory_manager.py` | MemoryManager 调度器 + MemoryProvider 注册 |
| `agent/memory_provider.py` | MemoryProvider 抽象基类 |
| `plugins/memory/__init__.py` | 外挂插件发现与加载 |
| `plugins/memory/holographic/` | Holographic 记忆插件（FTS5 + HRR 向量） |
| `plugins/memory/mem0/` | Mem0 平台集成插件 |
| `plugins/memory/honcho/` | Honcho AI 记忆集成插件 |
| `plugins/memory/supermemory/` | Supermemory 语义记忆插件 |
| `run_agent.py`（L1920-1950） | memory store 与 provider 的初始化 |
| `hermes_cli/config.py` | 默认配置定义 |
| `hermes_cli/memory_setup.py` | `hermes memory setup\|status` CLI |

### 7.2 配置要点

```yaml
# ~/.hermes/config.yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200      # MEMORY.md 字符限制（默认）
  user_char_limit: 1375        # USER.md 字符限制（默认）
  provider: ""                 # 外挂插件名：honcho / mem0 / holographic / openviking / etc.

auxiliary:
  session_search:
    provider: "auto"           # 辅助 LLM 提供商
    model: ""                  # 留空使用主模型
    timeout: 30                # 摘要超时（秒）
    max_concurrency: 3         # 并行摘要数（上限 5）
```

### 7.3 实际使用数据

当前灵犀 profile 的记忆使用情况：
- **MEMORY.md**: ~2,000 字符 / 2,200 限制（91%）
- **USER.md**: ~700 字符 / 1,375 限制（51%）
- **state.db**: 未计入（灵犀 profile 单独存储）
