# lib/adapters — 分包规则与 Port 镜像（R3 成文，2026-10-26）

## 规则（新增子包/文件必须遵守）

1. **对位 `lib/interfaces/` 的 Port 域**：实现某 Port 的 adapter 归入对应域子包
   （见下表）。一个子包可承载多个相邻 Port 的实现，但不得跨域混装。
2. **域服务型子包**：无 Port 的「适配器域服务」（对接外部系统/本机环境的纯适配逻辑）
   按外部域命名子包（如 `llm_routing`、`frameworks`、`internal_llm`、`container`），
   **对外一律经 `lib/composition` 门面**暴露，api/core/application 不直连。
3. **高内聚闭环优先**：互相成闭环的模块聚合同一子包（先例：`llm_routing`
   = model_router + complexity_router + ollama_routing）。
4. **搬移留 shim**：渐进重构中移动的模块在旧位留 `sys.modules` 替换 shim
   （分层守卫测试已豁免该模式），调用方分批切换后 shim 才可删。
5. 新增子包须更新本表。

## 子包 ↔ Port 镜像表

| 子包 | 承载 Port（interfaces/） | 说明 |
|------|--------------------------|------|
| `config` | `ConfigRepository`（config_repo） | 配置仓/注册表/settings/compose 等配置域 |
| `discovery` | `DiscoverySource` | agent 发现源（dir/docker/env） |
| `fakes` | 多 Port 测试替身 | Wave4 dry-run，全 Port 的内存假件 |
| `frameworks` | `BridgedAgentPort` 的实现基础 | 12+ agent 框架平级适配（BaseAdapter+ADAPTERS 注册表，SPEC.md 规范） |
| `integrations` | `IntegrationsPort` | n8n/comfyui/memory_bridge 等外集成（model_router/ollama_routing 已析出至 llm_routing） |
| `internal_llm` | （无 Port，域服务） | 内置 LLM client/index/probe，经 composition 门面 |
| `llm_routing` | （无 Port，域服务闭环） | R3 聚合：复杂度→档位→本地推理就绪；P2 指标中心智能层的路由底座 |
| `metrics` | （无 Port，域服务） | P2 指标引擎（B1-B3）：manifest 双栈 SoT 读取 + collector 现算 + store 时序环形窗口 + query 统一协议 |
| `locale` | `LocalePort` | 中文错误码/角色标签 |
| `ops` | `OpsPort` + 域服务 | doctor/clinic/heartbeat/alerts/scheduler/search/catalog |
| `orchestration` | `TaskFsmPort`/`HumanGatePort`/`AuditPort`/`NotifierPort`/`BudgetMeterPort` | 纯 Port 实现层（R1 后：task_fsm/phantom_detect 已归 application，complexity_router 已归 llm_routing） |
| `plane` | `HostPlanePort`/`ContainerPlanePort` | 宿主/容器平面 |
| `results` | `ResultStorePort` | ack/回执/结果落盘 |
| `runtime` | `AgentRuntimePort` | 凭据交付等运行时支持 |
| `transport` | `MessageTransportPort`/`A2ATransportPort` | 消息总线/A2A HTTP/file-bus |
| `container` | （无 Port，域服务） | docker compose 管理服务 |

## 已知待办

- `orchestration/automation.py`、`human_queue.py`：规则+持久化混合体，无独立 Port；
  待后续触达时评估是否提 Port 或并入域服务。

## L3 装配登记现状（P0c，2026-10-28 更新）

已登记 slot（`lib.interfaces.assembler.register`；`composition.<slot>` 声明优先，
harness 例外——选择键保持 `harness.mode`）：

| slot | 实现 | 消费点 |
|---|---|---|
| `audit` | noop / file | composition.build_orchestration |
| `notifier` | file | composition.build_orchestration |
| `result_store` | file / fake | composition.build_result_store |
| `locale` | dict | composition.build_locale_port（lang 经 ctx） |
| `transport` | selecting / fake | composition.build_transport |
| `a2a_transport` | http / fake | composition.build_a2a_transport |
| `bridged_agent` | cli / fake | composition.build_bridged_agent |
| `harness` | stub / replay / record / production | composition.get_harness 门面（未知 mode fail-fast） |

**成文例外**：`adapters/transport/file_bus.py` 的 `_harness_for()` 惰性经
composition 门面查 harness（adapters→composition）——per-store 语义要求按
消息 headers 的 data_dir 逐次解析，无法装配期注入单一实例；禁止扩大此模式。
（原债 `frameworks/registry.py` 反向 import `lib.infra.agent_demo` 已于
2026-10-28 删除——零消费者的死 re-export。）
