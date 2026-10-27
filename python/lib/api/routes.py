"""声明式路由表（PY4-Option A 第一批）— 分发 + OpenAPI 元数据同源。

设计（提案 2026-10-27-python-http-1-3-1.md Option A）：
- 本表是**分发的优先层**：do_GET/do_POST 先查表，未命中回退
  base.py 既有 elif 链——渐进迁移零行为变化（D9）；
- 每条路由带 OpenAPI 3.1 形状元数据（summary/tags/params），是
  openapi.py 生成器的唯一输入，也是未来的权限点清单（D15 预留）；
- 路径以 ``{param}`` 结尾 → 前缀匹配，剩余段为路径参数；
  ``param_mode="path_suffix:X"`` 表示参数尾部携带后缀 X（如 {id}/delete）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str  # 精确路径；{param} 为路径参数（可在任意段，如 {id}/delete）
    module: str  # _get_handlers() 返回的 handler 集 key
    action: str  # handler 函数名
    summary: str = ""
    tags: tuple = ()
    param_mode: str = "none"  # none | path | path_suffix:<suffix>
    params_meta: tuple = field(default=())  # OpenAPI query 参数补述 (name, in, desc)

    def __post_init__(self) -> None:
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.path)
        object.__setattr__(self, "_regex", re.compile("^" + pattern + "$"))

    def match(self, path: str) -> Optional[str]:
        """None=不匹配；""=精确命中；非空=第一个路径参数捕获值。"""
        m = self._regex.match(path)  # type: ignore[attr-defined]
        if not m:
            return None
        groups = m.groupdict()
        if not groups:
            return ""
        return next(iter(groups.values()))


ROUTES: list[RouteSpec] = [
    # ── system / 目录（GET）───────────────────────────────────────────────
    RouteSpec("GET", "/api/health", "system", "handle_health",
              "服务健康探测", ("system",)),
    RouteSpec("GET", "/api/status", "system", "handle_status",
              "系统状态总览", ("system",)),
    RouteSpec("GET", "/api/positions", "system", "handle_positions",
              "职位目录（发令窗口起草面板：候选池+inputs schema+实时空闲态）", ("catalog",)),
    RouteSpec("GET", "/api/identities", "system", "handle_identities",
              "内置身份清单（D2/D15：id 稳定，显示名可改）", ("identity",)),
    RouteSpec("GET", "/api/command/inbox", "tasks", "handle_command_inbox",
              "子言收件箱四路聚合（manager-pending+human-queue+alerts+未读）", ("command",)),
    RouteSpec("GET", "/api/metrics/manifest", "system", "handle_metrics_manifest",
              "指标清单 SoT（B1：双栈同源 manifest）", ("metrics",)),
    RouteSpec("GET", "/api/metrics/query", "system", "handle_metrics_query",
              "指标查询（B2：point 现算/1h 时序窗口）", ("metrics",),
              params_meta=(("metric", "query", "指标 id"), ("granularity", "query", "point|1h"),
                           ("hours", "query", "回溯小时数"))),
    RouteSpec("GET", "/api/metrics/rules", "system", "handle_metrics_rules",
              "告警规则清单（B5）", ("metrics",)),
    RouteSpec("GET", "/api/metrics/layout", "system", "handle_metrics_layout",
              "驾驶舱大盘布局（B4 dashboard as config）", ("metrics",)),
    RouteSpec("GET", "/api/workflows", "workflows", "handle_workflows_list",
              "工作流模板清单（registry SoT）", ("workflows",)),
    RouteSpec("GET", "/api/workflows/{id}", "workflows", "handle_workflow_get",
              "工作流模板详情", ("workflows",), param_mode="path"),
    RouteSpec("GET", "/api/openapi.json", "_openapi", "handle_openapi",
              "本服务 OpenAPI 3.1 文档（PY4-A：路由表生成）", ("meta",)),
    # ── 任务查询（GET）────────────────────────────────────────────────────
    RouteSpec("GET", "/api/tasks", "tasks", "handle_tasks",
              "任务列表（过滤/分页/噪音排除）", ("tasks",),
              params_meta=(("status", "query", "状态过滤"), ("assignee", "query", "负责人过滤"),
                           ("limit", "query", "页大小"), ("offset", "query", "偏移"))),
    RouteSpec("GET", "/api/tasks/{id}", "tasks", "handle_task_get",
              "任务详情", ("tasks",), param_mode="path"),
    # ── A2A（python handlers_a2a；M2d 对角面）────────────────────────────
    RouteSpec("GET", "/api/a2a/agent-cards", "a2a", "handle_a2a_agent_card_list",
              "A2A agent 卡片目录", ("a2a",)),
    RouteSpec("GET", "/api/a2a/agent-card/{id}", "a2a", "handle_a2a_agent_card_get",
              "A2A agent 卡片详情", ("a2a",), param_mode="path"),
    RouteSpec("GET", "/api/a2a/protocol", "a2a", "handle_a2a_protocol_status",
              "A2A 协议状态（spec 版本追踪）", ("a2a",)),
    RouteSpec("POST", "/api/a2a/rpc/{id}", "a2a", "handle_a2a_rpc",
              "A2A JSON-RPC 入站代理（SendMessage/GetTask/CancelTask）", ("a2a",),
              param_mode="path"),
    # ── 任务 / 发令（POST）───────────────────────────────────────────────
    RouteSpec("POST", "/api/tasks/create", "tasks", "handle_task_create",
              "建任务（v3 A2A Envelope；legacy→410）", ("tasks",)),
    RouteSpec("POST", "/api/command/draft", "tasks", "handle_command_draft",
              "发令草稿预演（D4：tier0→LLM 无副作用）", ("command",)),
    RouteSpec("POST", "/api/workflows/{id}", "workflows", "handle_workflow_save",
              "创建/更新工作流模板", ("workflows",), param_mode="path"),
    RouteSpec("POST", "/api/workflows/{id}/delete", "workflows", "handle_workflow_delete",
              "删除工作流模板", ("workflows",), param_mode="path_suffix:/delete"),
    RouteSpec("POST", "/api/agents/{id}/step-result", "tasks", "handle_agent_step_result",
              "agent 工单执行回执（落 msg-results + 立即推进）", ("tasks",),
              param_mode="path_suffix:/step-result"),
    # ── 身份（PATCH，经 do_POST 转发，self.command 区分）─────────────────
    RouteSpec("PATCH", "/api/identities/{id}", "tasks", "handle_identity_rename",
              "内置身份改名（显示名，id 稳定）", ("identity",), param_mode="path"),
]


def dispatch(handler_self: Any, method: str, path: str) -> bool:
    """表优先分发；命中返回 True（已响应），未命中返回 False（走原 elif 链）。

    长路径优先匹配：`/api/x/{id}/delete` 必须先于 `/api/x/{id}`（否则后缀
    被当作参数吞掉路由到错误 handler——冒烟实证过）。
    """
    for spec in sorted(ROUTES, key=lambda s: len(s.path), reverse=True):
        if spec.method != method:
            continue
        param = spec.match(path)
        if param is None:
            continue
        if spec.module == "_openapi":
            from lib.api.openapi import handle_openapi
            handle_openapi(handler_self)
            return True
        from lib.api.base import _get_handlers  # 运行期取（base 先于本模块加载完成）
        fn = getattr(_get_handlers()[spec.module], spec.action)
        if spec.param_mode == "none":
            fn(handler_self)
        else:
            real = param
            if spec.param_mode.startswith("path_suffix:"):
                suffix = spec.param_mode.split(":", 1)[1]
                if real.endswith(suffix):
                    real = real[: -len(suffix)]
            fn(handler_self, real)
        return True
    return False
