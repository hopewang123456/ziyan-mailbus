"""声明式路由表（PY4-Option A）— 分发 + OpenAPI 元数据同源。

设计（提案 2026-10-27-python-http-1-3-1.md Option A）：
- 本表是**分发的优先层**：do_GET/do_POST 先查表，未命中回退
  base.py 既有 elif 链——渐进迁移零行为变化（D9）；
- 每条路由带 OpenAPI 3.1 形状元数据（summary/tags/params/body/response），
  是 openapi.py 生成器的唯一输入，也是未来的权限点清单（D15 预留）；
- 路径以 ``{param}`` 结尾 → 前缀匹配，剩余段为路径参数；
  ``param_mode="path_suffix:X"`` 表示参数尾部携带后缀 X（如 {id}/delete）；
- 多路径参数（如 /api/tasks/{id}/fsm/{action}）：match() 返回参数字典，
  dispatch() 按路径中 ``{param}`` 的出现顺序依次传给 handler。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str  # 精确路径；{param} 为路径参数（可在任意段，如 {id}/delete）
    module: str  # _get_handlers() 返回的 handler 集 key
    action: str  # handler 函数名
    summary: str = ""
    tags: tuple = ()
    param_mode: str = "none"  # none | path | path_suffix:<suffix>
    params_meta: tuple = field(default=())  # OpenAPI query 参数补述 (name, in, desc[, type])
    body_meta: tuple = field(default=())  # OpenAPI requestBody 声明 ((name, type, desc), ...)
    response_meta: tuple = field(default=())  # OpenAPI 响应声明 ((name, type, desc), ...)

    def __post_init__(self) -> None:
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.path)
        object.__setattr__(self, "_regex", re.compile("^" + pattern + "$"))

    @property
    def path_params(self) -> tuple:
        """路径中 ``{param}`` 按出现顺序的参数名（多参 dispatch 的传参顺序）。"""
        return tuple(re.findall(r"\{(\w+)\}", self.path))

    def match(self, path: str) -> Optional[Dict[str, str]]:
        """None=不匹配；否则返回 {参数名: 捕获值}（无参数则空字典）。

        ``param_mode="path_suffix:X"`` 时，末位参数剥离后缀 X（如
        ``/api/workflows/{id}/delete`` 捕获 ``id="x"`` 而非 ``"x/delete"``）。
        """
        m = self._regex.match(path)  # type: ignore[attr-defined]
        if not m:
            return None
        groups = dict(m.groupdict())
        if self.param_mode.startswith("path_suffix:"):
            suffix = self.param_mode.split(":", 1)[1]
            names = self.path_params
            if names:
                last = names[-1]
                if groups.get(last, "").endswith(suffix):
                    groups[last] = groups[last][: -len(suffix)]
        return groups


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
    RouteSpec("GET", "/api/agents", "system", "handle_agents",
              "agent 列表与配置（含 access/agent.json registry）", ("agents",),
              response_meta=(("agents", "object", "agent 名 → 配置详情"),
                             ("canonical_root", "string", "mailbus 根目录"))),
    RouteSpec("GET", "/api/stats", "system", "handle_stats",
              "消息统计/报表（总量+状态分布+agent 排行+响应时间）", ("ops",),
              response_meta=(("total_messages", "integer", "消息总量"),
                             ("status_distribution", "object", "状态分布"),
                             ("agent_stats", "object", "逐 agent 统计"))),
    RouteSpec("GET", "/api/acceptance", "system", "handle_acceptance",
              "验收观察项对账（六项健康检查）", ("ops",),
              response_meta=(("status", "string", "ok|error"),
                             ("ok", "boolean", "是否全部通过"),
                             ("checked_at", "string", "检查时刻"),
                             ("items", "object", "逐项检查结果"))),
    RouteSpec("GET", "/api/agents/{agent}/unread", "inbox", "handle_agent_unread",
              "指定 agent 的未读计数", ("agents",), param_mode="path",
              response_meta=(("agent", "string", "agent 名"),
                             ("unread", "integer", "未读消息数"))),
    RouteSpec("GET", "/api/command/inbox", "tasks", "handle_command_inbox",
              "子言收件箱四路聚合（manager-pending+human-queue+alerts+未读）", ("command",)),
    # ── SSE 流（PY4-A 双栈；差量快照：变化才推）─────────────────────────
    RouteSpec("GET", "/api/command/inbox/stream", "tasks", "handle_command_inbox_stream",
              "收件箱聚合 SSE 差量流（snapshot/heartbeat/done）", ("command",)),
    RouteSpec("GET", "/api/metrics/stream", "system", "handle_metrics_stream",
              "指标快照 SSE 差量流（snapshot/heartbeat/done）", ("metrics",)),
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
    RouteSpec("GET", "/api/tasks/{id}/fsm", "tasks", "handle_task_fsm_get",
              "任务状态机摘要（Dashboard 用）", ("tasks",), param_mode="path"),
    # ── 收件箱（GET）──────────────────────────────────────────────────────
    RouteSpec("GET", "/api/inbox/{agent}", "inbox", "handle_inbox",
              "指定 agent 的 inbox 内容（?status_filter/?limit）", ("inbox",),
              param_mode="path",
              params_meta=(("status_filter", "query", "状态过滤"), ("limit", "query", "最近 N 条"))),
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
    # M2d-b1/b2b：SDK 对等端点（java A2aSdkController 同路径；官方裸 Task wire 形状 + 0.2/0.3 双名）
    RouteSpec("POST", "/api/a2a/sdk/{id}", "a2a", "handle_a2a_sdk_rpc",
              "A2A SDK 面（官方 Task 形状；0.2/0.3 双方法名）", ("a2a",),
              param_mode="path"),
    # ── 任务 / 发令（POST）───────────────────────────────────────────────
    RouteSpec("POST", "/api/tasks/create", "tasks", "handle_task_create",
              "建任务（v3 A2A Envelope；legacy→410）", ("tasks",),
              body_meta=(("task_id", "string", "任务 id（必填）"),
                         ("intent", "string", "任务意图（必填）"),
                         ("initiator", "string", "发起者（必填）"),
                         ("mode", "string", "explicit|auto（必填）"),
                         ("tier", "string", "执行层级（必填）"),
                         ("planned_chain", "array", "显式计划链（mode=explicit 时必填）")),
              response_meta=(("status", "string", "ok|error"),
                             ("task_id", "string", "创建的任务 id"),
                             ("fsm", "object", "状态机摘要"),
                             ("error", "string", "错误码（失败时）"))),
    RouteSpec("POST", "/api/tasks/{id}/fsm/{action}", "tasks", "handle_task_fsm_action",
              "任务状态机动作（rollback/skip/cancel/pause/priority/accept…）", ("tasks",),
              param_mode="path",
              body_meta=(("reason", "string", "动作原因（可选）")),
              response_meta=(("status", "string", "ok|error"),
                             ("fsm", "object", "动作后的状态机摘要"),
                             ("action", "string", "实际执行的动作"))),
    RouteSpec("POST", "/api/command/draft", "tasks", "handle_command_draft",
              "发令草稿预演（D4：tier0→LLM 无副作用）", ("command",),
              body_meta=(("question", "string", "发令意图描述"),
                         ("target", "string", "目标 agent（可选）")),
              response_meta=(("status", "string", "ok|error"),
                             ("planned_chain", "array", "预演出的计划链"),
                             ("plan_meta", "object", "计划元信息"))),
    RouteSpec("POST", "/api/assistant/ask", "internal_llm", "handle_assistant_ask",
              "AI 助手问答（指标语义层 + RAG 手册）", ("assistant",),
              body_meta=(("question", "string", "问题（必填）"),),
              response_meta=(("status", "string", "ok|error"),
                             ("answer", "string", "回答正文"),
                             ("citations", "array", "手册引用"))),
    RouteSpec("POST", "/api/workflows/{id}", "workflows", "handle_workflow_save",
              "创建/更新工作流模板", ("workflows",), param_mode="path"),
    RouteSpec("POST", "/api/workflows/{id}/delete", "workflows", "handle_workflow_delete",
              "删除工作流模板", ("workflows",), param_mode="path_suffix:/delete"),
    RouteSpec("POST", "/api/agents/{id}/step-result", "tasks", "handle_agent_step_result",
              "agent 工单执行回执（落 msg-results + 立即推进）", ("tasks",),
              param_mode="path_suffix:/step-result"),
    # ── 收件箱动作（POST；java 对等面）────────────────────────────────────
    RouteSpec("POST", "/api/inbox/ack/{id}", "inbox", "handle_inbox_ack",
              "确认（ack）单条消息", ("inbox",), param_mode="path",
              response_meta=(("status", "string", "ok|error"),
                             ("id", "string", "消息 id"),
                             ("state", "string", "确认后状态"))),
    RouteSpec("POST", "/api/inbox/{agent}/archive", "inbox", "handle_inbox_archive",
              "归档 agent 的已结算消息", ("inbox",), param_mode="path",
              body_meta=(("dry_run", "boolean", "只演算不落盘（可选）"),),
              response_meta=(("status", "string", "ok|error"),
                             ("agent", "string", "agent 名"),
                             ("archived", "integer", "归档条数"),
                             ("ids", "array", "被归档的消息 id"))),
    RouteSpec("POST", "/api/inbox/{agent}/send", "inbox", "handle_inbox_send",
              "向指定 agent 发消息", ("inbox",), param_mode="path",
              body_meta=(("from", "string", "发送方 agent"),
                         ("content", "string", "消息正文（必填）")),
              response_meta=(("status", "string", "ok|error"),
                             ("id", "string", "消息 id"),
                             ("state", "string", "初始状态"))),
    # ── 身份（PATCH，经 do_POST 转发，self.command 区分）─────────────────
    RouteSpec("PATCH", "/api/identities/{id}", "tasks", "handle_identity_rename",
              "内置身份改名（显示名，id 稳定）", ("identity",), param_mode="path"),
    # ── 迁表批一（2026-10-29）：GET 内联字典 46 条 + permit 转真 handler ──
    RouteSpec("GET", "/api/frameworks", "system", "handle_frameworks",
              "frameworks", ("system",)),
    RouteSpec("GET", "/api/tasks/audit/stats/trend", "tasks", "handle_task_audit_trend",
              "task audit trend", ("tasks",)),
    RouteSpec("GET", "/api/tasks/audit/stats", "tasks", "handle_task_audit_stats",
              "task audit stats", ("tasks",)),
    RouteSpec("GET", "/api/tasks/audit/pending", "tasks", "handle_task_audit_pending",
              "task audit pending", ("tasks",)),
    RouteSpec("GET", "/api/heartbeat", "system", "handle_heartbeat",
              "heartbeat", ("system",)),
    RouteSpec("GET", "/api/alerts", "system", "handle_alerts",
              "alerts", ("system",)),
    RouteSpec("GET", "/api/config", "system", "handle_config",
              "config", ("system",)),
    RouteSpec("GET", "/api/launch", "system", "handle_list_launchable",
              "list launchable", ("system",)),
    RouteSpec("GET", "/api/bulletin", "tasks", "handle_bulletin",
              "bulletin", ("tasks",)),
    RouteSpec("GET", "/api/permission", "tasks", "handle_permission",
              "permission", ("tasks",)),
    RouteSpec("GET", "/api/reports", "system", "handle_reports",
              "reports", ("system",)),
    RouteSpec("GET", "/api/patrol-reports", "system", "handle_patrol_reports",
              "patrol reports", ("system",)),
    RouteSpec("GET", "/api/reviews", "system", "handle_code_reviews",
              "code reviews", ("system",)),
    RouteSpec("GET", "/api/reviews/projects", "system", "handle_code_reviews_projects",
              "code reviews projects", ("system",)),
    RouteSpec("GET", "/api/replies", "inbox", "handle_replies",
              "replies", ("inbox",)),
    RouteSpec("GET", "/api/skill-usage", "tasks", "handle_skill_usage",
              "skill usage", ("tasks",)),
    RouteSpec("GET", "/api/skill-use", "tasks", "handle_skill_use",
              "skill use", ("tasks",)),
    RouteSpec("GET", "/api/templates", "system", "handle_templates",
              "templates", ("system",)),
    RouteSpec("GET", "/api/external-tools", "system", "handle_external_tools",
              "external tools", ("system",)),
    RouteSpec("GET", "/api/clinic/tools", "system", "handle_clinic_tools",
              "clinic tools", ("system",)),
    RouteSpec("GET", "/api/clinic/jobs", "system", "handle_clinic_jobs",
              "clinic jobs", ("system",)),
    RouteSpec("GET", "/api/test-agents", "system", "handle_test_agents",
              "test agents", ("system",)),
    RouteSpec("GET", "/api/doctor", "system", "handle_doctor",
              "doctor", ("system",)),
    RouteSpec("GET", "/api/failover/metrics", "system", "handle_failover_metrics",
              "failover metrics", ("system",)),
    RouteSpec("GET", "/api/tokens/summary", "system", "handle_token_summary",
              "token summary", ("system",)),
    RouteSpec("GET", "/api/demo/trace", "system", "handle_demo_trace",
              "demo trace", ("system",)),
    RouteSpec("GET", "/api/agents/assembly", "system", "handle_agent_assembly",
              "agent assembly", ("system",)),
    RouteSpec("GET", "/api/tasks/trace", "tasks", "handle_task_trace",
              "task trace", ("tasks",)),
    RouteSpec("GET", "/api/locale/errors", "system", "handle_locale_errors",
              "locale errors", ("system",)),
    RouteSpec("GET", "/api/workload", "system", "handle_workload",
              "workload", ("system",)),
    RouteSpec("GET", "/api/send-msg", "inbox", "handle_send_msg",
              "send msg", ("inbox",)),
    RouteSpec("GET", "/api/avatars/manifest", "system", "handle_avatars_manifest",
              "avatars manifest", ("system",)),
    RouteSpec("GET", "/api/internal-llm/status", "internal_llm", "handle_internal_llm_status",
              "internal llm status", ("internal_llm",)),
    RouteSpec("GET", "/api/internal-llm/health", "internal_llm", "handle_internal_llm_health",
              "internal llm health", ("internal_llm",)),
    RouteSpec("GET", "/api/intake", "intake", "handle_intake_list",
              "intake list", ("intake",)),
    RouteSpec("GET", "/api/settings/sections", "settings", "handle_settings_sections",
              "settings sections", ("settings",)),
    RouteSpec("GET", "/api/settings/env", "settings", "handle_settings_env_get",
              "settings env get", ("settings",)),
    RouteSpec("GET", "/api/settings/paths", "settings", "handle_settings_paths",
              "settings paths", ("settings",)),
    RouteSpec("GET", "/api/settings/compose-files", "settings", "handle_compose_files_list",
              "compose files list", ("settings",)),
    RouteSpec("GET", "/api/settings/integrations", "settings", "handle_integrations",
              "integrations", ("settings",)),
    RouteSpec("GET", "/api/skills/index", "settings", "handle_skills_index",
              "skills index", ("settings",)),
    RouteSpec("GET", "/api/discover", "lifecycle", "handle_discover",
              "discover", ("lifecycle",)),
    RouteSpec("GET", "/api/align", "lifecycle", "handle_align",
              "align", ("lifecycle",)),
    RouteSpec("GET", "/api/agents/active", "lifecycle", "handle_active_agents",
              "active agents", ("lifecycle",)),
    RouteSpec("GET", "/api/chain/budget", "lifecycle", "handle_chain_budget",
              "chain budget", ("lifecycle",)),
    RouteSpec("GET", "/api/config/mailbus-token", "lifecycle", "handle_mailbus_token",
              "mailbus token", ("lifecycle",)),
    RouteSpec("GET", "/api/bulletin/permit", "tasks", "handle_bulletin_permit_get",
              "bulletin permit get", ("tasks",)),

    # ── 迁表批一（2026-10-29）：POST 精确路径 27 条（device 链保留原链）──
    RouteSpec("POST", "/api/launch", "system", "handle_launch",
              "launch", ("system",)),
    RouteSpec("POST", "/api/bulletin/post", "tasks", "handle_bulletin_post",
              "bulletin post", ("tasks",)),
    RouteSpec("POST", "/api/bulletin/permit", "tasks", "handle_bulletin_permit",
              "bulletin permit", ("tasks",)),
    RouteSpec("POST", "/api/permission", "tasks", "handle_permission",
              "permission", ("tasks",)),
    RouteSpec("POST", "/api/skill-use", "tasks", "handle_skill_use",
              "skill use", ("tasks",)),
    RouteSpec("POST", "/api/metrics/layout", "system", "handle_metrics_layout",
              "metrics layout", ("system",)),
    RouteSpec("POST", "/api/metrics/snapshot", "system", "handle_metrics_snapshot",
              "metrics snapshot", ("system",)),
    RouteSpec("POST", "/api/tasks/update", "tasks", "handle_task_update",
              "task update", ("tasks",)),
    RouteSpec("POST", "/api/tasks/audit", "tasks", "handle_task_audit",
              "task audit", ("tasks",)),
    RouteSpec("POST", "/api/intake/spawn-analyze", "intake", "handle_intake_spawn_analyze",
              "intake spawn analyze", ("intake",)),
    RouteSpec("POST", "/api/send-msg", "inbox", "handle_send_msg",
              "send msg", ("inbox",)),
    RouteSpec("POST", "/api/agents/scan", "lifecycle", "handle_agent_scan",
              "agent scan", ("lifecycle",)),
    RouteSpec("POST", "/api/agent-instances", "lifecycle", "handle_agent_instance_upsert",
              "agent instance upsert", ("lifecycle",)),
    RouteSpec("POST", "/api/agent-instances/load-roles", "lifecycle", "handle_agent_instance_load_roles",
              "agent instance load roles", ("lifecycle",)),
    RouteSpec("POST", "/api/agent-instances/discover", "lifecycle", "handle_agent_instance_discover",
              "agent instance discover", ("lifecycle",)),
    RouteSpec("POST", "/api/agent-instances/test-connection", "lifecycle", "handle_agent_instance_test_connection",
              "agent instance test connection", ("lifecycle",)),
    RouteSpec("POST", "/api/demo/run", "system", "handle_demo_run",
              "demo run", ("system",)),
    RouteSpec("POST", "/api/demo/clean", "system", "handle_demo_clean",
              "demo clean", ("system",)),
    RouteSpec("POST", "/api/internal-llm/dry-run", "internal_llm", "handle_internal_llm_dry_run",
              "internal llm dry run", ("internal_llm",)),
    RouteSpec("POST", "/api/internal-llm/rebuild-rag", "internal_llm", "handle_internal_llm_rebuild_rag",
              "internal llm rebuild rag", ("internal_llm",)),
    RouteSpec("POST", "/api/attachments/upload", "attachments", "handle_attachment_upload",
              "attachment upload", ("attachments",)),
    RouteSpec("POST", "/api/clinic/run", "system", "handle_clinic_run",
              "clinic run", ("system",)),
    RouteSpec("POST", "/api/dev/reload", "system", "handle_dev_reload",
              "dev reload", ("system",)),
    RouteSpec("POST", "/api/drill/video-publish", "drill", "handle_drill_video_publish",
              "drill video publish", ("drill",)),
    RouteSpec("POST", "/api/agents/recruit", "system", "handle_agent_recruit",
              "agent recruit", ("system",)),
    RouteSpec("POST", "/api/settings/env", "settings", "handle_settings_env_patch",
              "settings env patch", ("settings",)),
    RouteSpec("POST", "/api/align", "lifecycle", "handle_align",
              "align", ("lifecycle",)),
    RouteSpec("POST", "/api/chain/budget", "lifecycle", "handle_chain_budget",
              "chain budget", ("lifecycle",)),
    RouteSpec("POST", "/api/a2a/tasks", "a2a", "handle_a2a_tasks_create",
              "a2a tasks create", ("a2a",)),

    # ── 迁表批二（2026-10-29）：path_suffix / 双参 / 精确 POST 13 条 + GET 6 条 ──
    RouteSpec("POST", "/api/intake/{id}/spawn", "intake", "handle_intake_spawn",
              "intake spawn", ("intake",), param_mode="path_suffix:/spawn"),
    RouteSpec("POST", "/api/human-queue/{id}/resolve", "tasks", "handle_human_queue_resolve",
              "human queue resolve", ("tasks",), param_mode="path_suffix:/resolve"),
    RouteSpec("POST", "/api/agents/{agent}/step-result", "step_result", "handle_agent_step_result",
              "agent step result", ("step_result",), param_mode="path_suffix:/step-result"),
    RouteSpec("POST", "/api/frameworks/{id}/enable", "lifecycle", "handle_framework_enable",
              "framework enable", ("lifecycle",), param_mode="path_suffix:/enable"),
    RouteSpec("POST", "/api/frameworks/{id}/disable", "lifecycle", "handle_framework_disable",
              "framework disable", ("lifecycle",), param_mode="path_suffix:/disable"),
    RouteSpec("POST", "/api/agents/{agent}/enable", "lifecycle", "handle_role_enable",
              "role enable", ("lifecycle",), param_mode="path_suffix:/enable"),
    RouteSpec("POST", "/api/actions/update/{agent}/{msg_id}", "inbox", "handle_actions_update",
              "actions update", ("inbox",), param_mode="path"),
    RouteSpec("POST", "/api/mark-read/{id}", "inbox", "handle_mark_read",
              "mark read", ("inbox",), param_mode="path"),
    RouteSpec("POST", "/api/config/mailbus-token", "lifecycle", "handle_mailbus_token",
              "mailbus token", ("lifecycle",)),
    RouteSpec("POST", "/api/config/mailbus-token/rotate", "lifecycle", "handle_mailbus_token",
              "mailbus token rotate", ("lifecycle",)),
    RouteSpec("POST", "/api/a2a/rpc/{agent}", "a2a", "handle_a2a_rpc",
              "A2A JSON-RPC 入站代理（SendMessage/GetTask/CancelTask）", ("a2a",), param_mode="path"),
    RouteSpec("POST", "/api/settings/section/services/probe", "settings", "handle_settings_services_probe",
              "settings services probe", ("settings",)),
    RouteSpec("POST", "/api/settings/section/{section}", "settings", "handle_settings_section_patch",
              "settings section patch", ("settings",), param_mode="path"),
    RouteSpec("POST", "/api/workflows/{id}", "workflows", "handle_workflow_save",
              "workflow save", ("workflows",), param_mode="path"),
    RouteSpec("GET", "/api/manager/pending", "tasks", "handle_manager_pending",
              "manager pending", ("tasks",)),
    RouteSpec("GET", "/api/agent-profile/{agent}", "system", "handle_agent_profile",
              "agent profile", ("system",), param_mode="path"),
    RouteSpec("GET", "/api/harness-reports/{sha}", "system", "handle_harness_report",
              "harness report", ("system",), param_mode="path"),
    RouteSpec("GET", "/api/ping/{target}", "system", "handle_ping",
              "ping", ("system",), param_mode="path"),
    RouteSpec("GET", "/api/reviews/{name}", "system", "handle_code_reviews_detail",
              "code review detail", ("system",), param_mode="path"),
    RouteSpec("GET", "/api/search", "system", "handle_search",
              "search", ("system",)),

    # ── 迁表批三（2026-10-29）：gates 四条（双参夹常量段）+ 聚合分支拆解 ──
    RouteSpec("POST", "/api/tasks/{id}/gates/{gate_id}/approve", "gates", "handle_gate_approve",
              "task gate approve", ("gates",), param_mode="path"),
    RouteSpec("POST", "/api/tasks/{id}/gates/{gate_id}/deny", "gates", "handle_gate_deny",
              "task gate deny", ("gates",), param_mode="path"),
    RouteSpec("POST", "/api/intake/{id}/gates/{gate_id}/approve", "intake", "handle_intake_gate_approve",
              "intake gate approve", ("intake",), param_mode="path"),
    RouteSpec("POST", "/api/intake/{id}/gates/{gate_id}/deny", "intake", "handle_intake_gate_deny",
              "intake gate deny", ("intake",), param_mode="path"),
    RouteSpec("POST", "/api/positions/{role_type}", "tasks", "handle_position_update",
              "position update", ("tasks",), param_mode="path"),
    RouteSpec("POST", "/api/metrics/rules/{id}", "system", "handle_metrics_rule_patch",
              "metrics rule patch", ("system",), param_mode="path"),
    RouteSpec("POST", "/api/identities/{id}", "system", "handle_identity_rename",
              "identity rename", ("system",), param_mode="path"),
    RouteSpec("GET", "/api/workflows/{id}", "workflows", "handle_workflow_get",
              "workflow get", ("workflows",), param_mode="path"),
    RouteSpec("GET", "/api/intake/{id}", "intake", "handle_intake_get",
              "intake get", ("intake",), param_mode="path"),
    RouteSpec("GET", "/api/intake/{id}/tasks", "intake", "handle_intake_tasks",
              "intake tasks", ("intake",), param_mode="path"),
    RouteSpec("GET", "/api/human-queue", "tasks", "handle_human_queue",
              "human queue list", ("tasks",)),
    RouteSpec("GET", "/api/settings/section/{section}", "settings", "handle_settings_section_get",
              "settings section get", ("settings",), param_mode="path"),

]


def dispatch(handler_self: Any, method: str, path: str) -> bool:
    """表优先分发；命中返回 True（已响应），未命中返回 False（走原 elif 链）。

    长路径优先匹配：`/api/x/{id}/delete` 必须先于 `/api/x/{id}`（否则后缀
    被当作参数吞掉路由到错误 handler——冒烟实证过）。

    多路径参数按 path 中 ``{param}`` 出现顺序传参：如
    ``/api/tasks/{id}/fsm/{action}`` → handler(task_id, action)。
    """
    for spec in sorted(ROUTES, key=lambda s: len(s.path), reverse=True):
        if spec.method != method:
            continue
        params = spec.match(path)
        if params is None:
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
            fn(handler_self, *(params[name] for name in spec.path_params))
        return True
    return False
