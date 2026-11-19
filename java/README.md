# mailbus Java 后端

与 `python/` 版同构的 Java 后端实现，用于不熟悉 Python 的团队直接做二次开发。
HTTP 契约与 `shared/contracts/generated/openapi.json` 对齐：81 条路径 / 99 个操作；
运行时通过 `GET /api/openapi.json` 提供同一份契约。

## 技术栈

| 项 | 选择 |
|----|------|
| JDK | 17 |
| 构建 | Maven 3.9+ |
| 框架 | Spring Boot 3.3（Web / JDBC / Validation） |
| 数据库 | SQLite（与 Python 版共用同一份 schema 与迁移脚本） |
| 测试 | JUnit 5 + MockMvc |

单模块 Maven 工程，根包 `io.github.hopewang123456.mailbus`。

## 目录结构

```
java/
├── pom.xml
└── src/main/java/io/github/hopewang123456/mailbus/
    ├── MailbusApplication.java   # 启动类（含 @EnableScheduling）
    ├── config/                   # AppProperties：所有路径与运行参数
    ├── db/                       # 数据源 + 迁移执行器
    ├── common/                   # 统一错误体、异常处理、ID/Token 工具
    ├── auth/                     # Bearer 解析、Actor、能力校验
    ├── identity/                 # 引导、员工、邀请、会话、心跳
    ├── org/                      # 团队、岗位、工位
    ├── agents/                   # Agent 目录
    ├── workflow/                 # 工作流、任务、审批
    ├── messaging/                # 消息、投递尝试、A2A/MCP 入口
    ├── skills/                   # 技能包与绑定
    ├── layout/                   # 办公布局（内部 + 公开脱敏）
    ├── observability/            # 总览、操作日志
    ├── metrics/                  # 指标查询、告警规则、大盘布局
    ├── audit/                    # 审核统计、最近告警
    ├── integrations/             # 集成清单、插件、env
    ├── dispatch/                 # outbox 派发、file_bus 入站
    ├── scheduler/                # 心跳/审批/派发后台巡检
    └── settings/                 # data/settings.json 读写
```

依赖方向保持单向：`controller → service → jdbc/组件`。Controller 只做协议翻译并取 Actor，
权限判断统一放在 Service（`Authz`）。

## 运行

要求 JDK 17 与 Maven。

```bash
cd java
mvn spring-boot:run
```

默认监听 `http://localhost:8080`，数据库为 `../data/mailbus.db`（与 Python 版共用。
**不要同时用两个进程写同一个库**）。

打包后运行：

```bash
mvn -DskipTests package
java -jar target/mailbus-java-0.2.0.jar
```

### 配置项

均可用环境变量覆盖（`application.yml` 中已声明默认值）：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MAILBUS_PORT` | `8080` | HTTP 端口 |
| `MAILBUS_DATA_DIR` | `../data` | 运行数据目录（SQLite / settings.json / file_bus / mcp） |
| `MAILBUS_SESSION_DAYS` | `7` | 会话有效天数 |
| `MAILBUS_HEARTBEAT_TIMEOUT_SEC` | `180` | 心跳超时秒数 |
| `MAILBUS_HEARTBEAT_SWEEP_SEC` | `30` | 心跳巡检间隔 |
| `MAILBUS_DISPATCH_INTERVAL_SEC` | `5` | outbox 派发 + file_bus 入站间隔 |
| `MAILBUS_DISPATCH_BATCH` | `50` | 单次派发数量 |
| `MAILBUS_DISPATCH_MAX_ATTEMPTS` | `3` | 最大投递次数，超过后进死信 |
| `MAILBUS_LAYOUT_PATH` | `../config/office-layout.json` | 办公布局种子 |
| `MAILBUS_METRICS_MANIFEST` | `../shared/config/mailbus/metrics-manifest.json` | 指标口径真源 |

> 相对路径基于启动时的工作目录。推荐在 `java/` 下启动；从仓库根启动时请显式设置
> `MAILBUS_DATA_DIR`、`MAILBUS_LAYOUT_PATH`、`MAILBUS_METRICS_MANIFEST`。

### 首次启动

1. `POST /api/identity/bootstrap/super-admin` 创建超级管理员，响应里的 `token` 作为后续 `Authorization: Bearer`。
2. `POST /api/identity/bootstrap/model-config` 配置模型（可跳过）。
3. `POST /api/identity/bootstrap/team` 或 `POST /api/identity/bootstrap/{step}/skip` 完成引导。

健康探测：`GET /api/health`（公开）。

## 测试

```bash
cd java
mvn test
```

`BackendSmokeTest` 会启动完整 Spring 上下文，使用 `target/test-data/mailbus.db`，
覆盖健康/鉴权、引导、身份、组织、Agent、布局、指标、审计、集成、工作流、任务、审批链路、
技能、消息，并校验越界参数返回 422。

## 二次开发指引

### 新增一个接口

1. 在对应领域包内新增/扩展 `*Dtos.java`，字段名用 camelCase，Jackson 全局转 snake_case。
2. 在 `*Service.java` 写用例：先取 `Actor`、用 `Authz` 判权限，再读写数据库；
   需要事件时通过 `Outbox.enqueue(kind, payload)`，与业务写入同事务。
3. 在 `*Controller.java` 映射路由，从 `@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE)` 取 Actor。
   写接口按契约补 `@ResponseStatus(HttpStatus.CREATED)` 或返回 `204`。
4. 需要新表时在 `src/main/resources/db/migration/` 增加 `0NN_xxx.sql`，
   文件名前缀即版本号；启动时 `MigrationRunner` 会与 Python 版共享 `ops_schema_version` 自动执行。
5. 补 `MockMvc` 测试，并更新 `shared/contracts/generated/openapi.json`（Python 侧导出脚本是契约真源）。

### 关键约定

- **错误体**：`{"error": "...", "error_code": "...", "message_zh": "..."}`；
  401/403/404/409/422 分别由 `ApiException` 工厂方法产生，参数校验失败统一 422 `validation_error`。
- **权限**：能力常量见 `auth/Authz.java`；写用例必须显式判权，Agent 的发送/派发/回执还要求端点审核通过。
- **时间**：数据库存 epoch 秒（`REAL`），对外序列化为 ISO-8601。
- **事件**：所有跨域副作用先写 `ops_outbox`，由 `OutboxDispatcher` 异步投递；
  支持 `file_bus`、`mcp`、`a2a` 三个通道，失败按 `2^attempts` 退避，超过上限进死信。
- **单实例**：派发器不做跨进程抢占；多实例部署前需要先给 `ops_outbox` 增加租约列。
- **路径集中**：文件系统路径只出现在 `AppProperties`，业务代码不要硬编码。

### 与 Python 版的关系

- 数据库 schema、迁移版本、能力枚举、路由与 JSON 字段保持一致，两个实现可读取同一份数据目录
  （迁移由先启动的一方执行）。
- 指标口径以 `shared/config/mailbus/metrics-manifest.json` 为唯一真源，Java 只负责读取与计算。
- 错误码、HTTP 状态码、422 错误体与 Python 版一致；唯一差异是 Java 的瞬时时间序列化为
  `Z` 结尾（Python 为 `+00:00`），对接前端时按 ISO-8601 解析即可。
