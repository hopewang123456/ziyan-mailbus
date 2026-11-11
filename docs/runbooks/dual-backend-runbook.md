# 双后端并跑 Runbook（D14）

## 端口规约
| 后端 | 端口 | 说明 |
|------|------|------|
| python serve | 9814 | 稳定实现，指标/发令/助手全能力 |
| java serve | 9815 | M1 预览；本地 mvn 跑法请用**绝对路径** `--mailbus.data-dir`（相对探测在多模块 cwd 下不稳，docker 不受影响） |
| 前端 | 随 serve 静态托管 | 同一 `web/dist` 产物，双后端各自托管 |

## Docker 并跑（推荐）
```bash
cd web && npm run build && cd ..
docker compose -f docker-compose.dual.yml up --build -d
# python: http://localhost:9814  ·  java: http://localhost:9815
```

## Java AI 助手激活（可选）
```bash
export SPRING_AI_OPENAI_BASE_URL=http://host.docker.internal:11434/v1   # ollama
export SPRING_AI_OPENAI_API_KEY=sk-any
docker compose -f docker-compose.dual.yml up -d mailbus-java
# 应用配置 mailbus.ai.enabled=true（application.yml 或 -D 参数）
```

## 已知差异（双栈）
- 指标：python 自研 query 端点 + 时序；java Micrometer `/actuator/metrics/mailbus.*`（同一 manifest 口径）
- AI 助手：两栈各自可用（同一 docs/ 知识库）
- 任务 FSM/发令后端：python 完整；java 随 M2

## 消息存储 SoT（D16，2026-11-11）

**唯一事实源**：python `inbox/<agent>/inbox.json`。java 侧全部改为适配层：

| 面 | 位置 | 说明 |
|----|------|------|
| 读 | java `PythonInboxStore` | 直读 inbox.json → MsgRecord 投影（mtime+size 缓存失效）；`/api/inbox`、`/api/replies`、`/api/agents/{id}/unread`、`/api/status`、`/api/stats` |
| 写 | java `PythonInboxWriter` | send/ack/mark-read/archive 落 inbox.json，python 状态机与格式（msg-YYYYMMDD-NNNNN、+0800、state/status 双轨） |
| 索引 | SQLite `msg_index` | **投影缓存**（files lead），可随时丢弃重建 |
| 事件 | SQLite `msg_events` | java append-only 派生增强，不参与 SoT；`/api/trace`、`/api/events` 已转正 |

### 锁
- 锁根：`<data_dir>/.locks`（`MAILBUS_LOCK_DIR` 最高优先）
- 锁文件名 = `mailbus-<sha256(data_dir 内相对路径)[:16]>.lock`，双栈容器即便挂载路径不同也命中同一锁文件
- 实现：python `lockf/flock` region[0,1) ↔ java `FileChannel.lock`，锁文件常驻不删除
- 跨语言对打验收：`python tools/d16_lock_interop.py`（期望 `final=350` 且锁目录仅一个 `mailbus-*.lock`）

### 运维命令
```bash
# 旧 java <msg-id>.json 单文件回迁进 inbox.json（幂等；源文件移到 inbox/<agent>/legacy-shards/）
mailbus migrate-shards

# msg_index 投影全量重建（python SoT → SQLite）
mailbus msg-index rebuild

# 双栈 API 面对拍（--py offline 可不起 python serve）
python tools/api_surface_diff.py --py offline --java http://127.0.0.1:9815
```

### 归档
- java `ArchiveService` 追加 `archive/<agent>/backlog-<stamp>.json`
  `{agent, archived_at, messages:[...]}`（python `store_cleanup` 同格式）
- 旧 `archive/<agent>/<date>/` 目录树不再产生

### 排障顺序（消息面）
1. `/api/agents/<agent>/unread` 与 python 直读不一致 → 检查 java 进程 `mailbus.data-dir` 是否指向同一 store
2. `/api/trace/<id>` 404 → 消息可能在 `archive/*/backlog-*.json`（已归档，或从未写入本 store）
3. reconcile 出现 java-only id → 投影滞后，跑 `mailbus msg-index rebuild` 后重试（不是伪造）
4. 写入后 python 侧长时间看不到 → 确认两侧 `.locks` 落在同一 data_dir（容器挂载路径差异必须靠 `MAILBUS_DATA` 对齐）

