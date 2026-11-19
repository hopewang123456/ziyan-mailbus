# mailbus

Agent 消息总线：分层 FastAPI + SQLite 后端，共用 React 驾驶舱（`web/`）。

Python 侧是分层 FastAPI 应用，持久化用 SQLite：领域规则在 `mailbus/core`，
用例在 `mailbus/application`，适配器在 `mailbus/adapters`，HTTP 映射在
`mailbus/api`，装配与路径在 `mailbus/bootstrap`。运行数据默认在 `data/`，
可用 `MAILBUS_DATA_DIR` 覆盖。

## 快速开始

```bash
cd python
pip install -e ".[dev]"
uvicorn mailbus.bootstrap.main:app --port 9814
```

- 健康检查：`GET http://127.0.0.1:9814/api/health`
- OpenAPI：`GET http://127.0.0.1:9814/api/openapi.json`
- 测试：`python -m pytest -q`
- 契约导出：`python tools/export_openapi.py`

首次启动通过 `POST /api/identity/bootstrap/super-admin` 创建超级管理员。

## Java 后端

`java/` 提供与 Python 版同构的 Spring Boot 3.3 / JDK 17 实现，HTTP 契约对齐
`shared/contracts/generated/openapi.json`（67 路径 / 82 操作），并与 Python 共用同一
SQLite schema 与 `data/` 目录。不熟悉 Python 的团队可直接基于它二次开发：

```bash
cd java
mvn spring-boot:run
```

详见 [java/README.md](java/README.md)。

## 目录

| 目录 | 内容 |
|---|---|
| `python/` | Python 服务（`mailbus` 包、测试、契约导出） |
| `java/` | Java 服务（Spring Boot 3.3，与 Python 同契约） |
| `web/` | React 驾驶舱 |
| `shared/` | 语言中立资产与生成的契约 |
| `config/` | 静态种子数据（办公布局） |
| `data/` | 运行状态：SQLite、file_bus / MCP 队列 |
| `docs/` | 产品与设计文档 |

## 分层

```
core → application → adapters → api → bootstrap
```

- `core` 纯领域逻辑，仅标准库。
- `application` 一个用例一个事务，负责 outbox。
- `adapters` 实现持久化、传输、时钟与 id。
- `api` 只做 HTTP 转换与调用者解析。
- `bootstrap` 是唯一知道文件路径的层。

权限统一走 `core.identity.policy.ensure_allowed`；写路由必须声明 capability，
由守卫 G8 校验。

旧 Python 栈（`python/lib`、`python/bus`、旧 `python/tools/`）已于 B7 清理移除。
