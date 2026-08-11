"""
ziyan-mailbus HTTP API — 任务/公告板/Skill 相关路由处理器

处理: /api/tasks, /api/bulletin, /api/bulletin/post, /api/bulletin/permit,
      /api/permission, /api/skill-usage, /api/skill-use
"""

import os
import json
import sys
from lib.infra.utils import json_read, json_write, _now_iso
from lib.application.orchestration.tracker import TaskTracker, TaskStatus, SKIP_TIMEOUT_PREFIXES
from lib.application.orchestration.pipeline.chain import normalize_task_chain, is_pipeline_step

# Dashboard 默认分页（无 query 时也生效，避免一次返回 400+ 任务拖死浏览器）
DEFAULT_TASKS_LIMIT = 120


def _is_noise_task_id(task_id: str) -> bool:
    if not task_id:
        return True
    return any(task_id.startswith(p) for p in SKIP_TIMEOUT_PREFIXES)


def _normalize_tasks_for_api(tasks: list) -> list:
    """API 返回前规范化 chain 格式，并补全 audit_reviewer / needs_audit / fsm。"""
    from lib.application.orchestration.audit_dispatch import task_requires_audit
    from lib.adapters.orchestration.task_fsm import ensure_fsm, fsm_summary

    for task in tasks:
        normalize_task_chain(task)
        chain = task.get("chain") or []
        if chain and is_pipeline_step(chain[0]) and not task.get("audit_reviewer"):
            task["audit_reviewer"] = "lingjian"
        task["needs_audit"] = task_requires_audit(task)
        if chain and is_pipeline_step(chain[0]):
            ensure_fsm(task)
            task["fsm"] = fsm_summary(task)
    return tasks


def handle_tasks(handler):
    """GET /api/tasks — 获取任务追踪列表，支持查询参数过滤

    查询参数:
        ?status=success          — 按状态过滤
        ?assignee=lingxiao       — 按负责人过滤
        &audit_status=audited    — 审计状态 (audited/pending-audit)
        &audit_status=pending-audit
        &reviewer=lingjian       — 按审查人过滤
        &limit=50                — 每页数量（默认 120）
        &offset=0                — 偏移量（默认 0）
        &exclude_noise=1         — 排除 remind-/tracker-remind- 等系统噪音（默认 1）
    """
    tracker = TaskTracker(handler.data_dir)

    # 检查是否有查询参数
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    status = params.get("status", [None])[0]
    assignee = params.get("assignee", [None])[0]
    audit_status = params.get("audit_status", [None])[0]
    reviewer = params.get("reviewer", [None])[0]
    exclude_noise = params.get("exclude_noise", ["1"])[0].lower() not in ("0", "false", "no")

    try:
        limit = int(params.get("limit", [str(DEFAULT_TASKS_LIMIT)])[0])
    except (ValueError, TypeError):
        limit = DEFAULT_TASKS_LIMIT
    limit = max(1, min(limit, 500))
    try:
        offset = int(params.get("offset", ["0"])[0])
    except (ValueError, TypeError):
        offset = 0

    # 如果有任何筛选参数，使用 list_by_filters
    if any([status, assignee, audit_status, reviewer]):
        result = tracker.list_by_filters(
            status=status,
            assignee=assignee,
            audit_status=audit_status,
            reviewer=reviewer,
            limit=limit,
            offset=offset,
        )
        tasks = result.get("tasks") or []
        if exclude_noise:
            tasks = [t for t in tasks if not _is_noise_task_id(t.get("task_id", ""))]
        result["tasks"] = _normalize_tasks_for_api(tasks)
        handler._send_json(result)
    else:
        all_tasks = tracker.list_all()
        if exclude_noise:
            all_tasks = [t for t in all_tasks if not _is_noise_task_id(t.get("task_id", ""))]
        total = len(all_tasks)
        page = all_tasks[offset:offset + limit]
        handler._send_json({
            "tasks": _normalize_tasks_for_api(page),
            "count": len(page),
            "total": total,
            "limit": limit,
            "offset": offset,
            "exclude_noise": exclude_noise,
        })


def create_task_from_envelope(data_dir: str, body: dict) -> tuple[dict, int]:
    """从 A2A Envelope 创建任务。返回 (response_body, http_status)。"""
    from lib.application.orchestration.router.envelope_validate import is_legacy_create_body, validate_envelope
    from lib.application.orchestration.router.planner import PlanError, needs_plan_approval, plan_task
    from lib.application.orchestration.router.dispatch import (
        dispatch_first_step,
        set_await_plan_approval,
        start_executing,
    )

    if is_legacy_create_body(body):
        return ({
            "status": "error",
            "error": "legacy_deprecated",
            "message": "Use A2A Envelope; see store/rules/a2a-task-create-api.md",
        }, 410)

    errors = validate_envelope(body, data_dir=data_dir)
    if errors:
        return ({
            "status": "error",
            "error": "schema_invalid",
            "details": errors,
        }, 400)

    task_id = body.get("task_id", "")
    tracker = TaskTracker(data_dir)
    if tracker.get(task_id):
        return ({
            "status": "error",
            "error": "task_exists",
            "message": f"任务 {task_id} 已存在",
        }, 409)

    try:
        if body.get("mode") == "explicit":
            planned = body["planned_chain"]
            plan_meta = {
                "method": "rules",
                "task_type_guess": body.get("task_type"),
                "confidence": 1.0,
                "provider_used": "rules",
            }
            from lib.application.orchestration.dispatch.collab_plan import expand_planned_chain_for_collab
            planned = expand_planned_chain_for_collab(planned, body)
        else:
            config = json_read(os.path.join(data_dir, "config.json"), {})
            out = plan_task(body, data_dir=data_dir, config=config)
            planned = out["planned_chain"]
            plan_meta = out["plan_meta"]
            from lib.application.orchestration.dispatch.collab_plan import expand_planned_chain_for_collab
            planned = expand_planned_chain_for_collab(planned, body)
    except PlanError as e:
        return ({
            "status": "error",
            "error": e.code,
            "message": str(e),
        }, 400)

    task = tracker.create_from_envelope(
        body, planned_chain=planned, plan_meta=plan_meta,
    )

    from lib.application.workflow.engine import bind_workflow
    bind_workflow(task, body, data_dir=data_dir)
    json_write(tracker._task_path(task_id), task)

    config = json_read(os.path.join(data_dir, "config.json"), {})
    if needs_plan_approval(body, config):
        set_await_plan_approval(task)
        from lib.composition import build_orchestration

        chain = task.get("chain") or []
        head = chain[0] if chain else {}
        planned = head.get("planned_role_types") or []
        orch = build_orchestration(data_dir)
        hq_id = orch.human_gate.enqueue({
            "type": "plan_approval",
            "status": "pending",
            "title": f"批准任务计划 · {task_id[:32]}",
            "hint": f"planned_role_types: {planned}",
            "task_id": task_id,
            "context": {
                "intent": task.get("intent") or task.get("summary", ""),
                "tier": task.get("tier"),
                "task_type": task.get("task_type"),
                "planned_role_types": planned,
                "plan_meta": task.get("plan_meta"),
            },
        })
        task["fsm"]["human_queue_id"] = hq_id
        json_write(tracker._task_path(task_id), task)
        return ({"status": "ok", "task": task, "human_queue_id": hq_id}, 201)

    start_executing(task)
    dispatch_first_step(data_dir, task)
    return ({"status": "ok", "task": task}, 201)


def handle_task_create(handler):
    """POST /api/tasks/create — v3 A2A Envelope（Legacy → 410）。"""
    body = handler._read_post_body()
    resp, status = create_task_from_envelope(handler.data_dir, body)
    handler._send_json(resp, status)


def handle_task_update(handler):
    """POST /api/tasks/update — 更新任务状态"""
    body = handler._read_post_body()
    task_id = body.get("task_id", "")
    status = body.get("status", "")
    error = body.get("error", None)

    if not task_id:
        handler._send_json({"error": "缺少 task_id"}, 400)
        return
    if status not in TaskStatus.ALL:
        handler._send_json(
            {"error": f"无效状态 {status}，可选: {', '.join(sorted(TaskStatus.ALL))}"},
            400,
        )
        return

    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"error": f"任务 {task_id} 不存在"}, 404)
        return

    updated = tracker.update_status(task_id, status, error=error)
    handler._send_json({"status": "ok", "task": updated})


def handle_task_audit(handler):
    """POST /api/tasks/audit — 追加审计记录到任务

    请求体示例:
    {
        "task_id": "xxx",
        "reviewer": "lingjian",
        "result": "pass|fail|warn",
        "issues": [{"desc": "问题描述", "severity": "high", "file": "path/to/file.py", "line": 42}],
        "summary": "审计摘要",
        "report_file": "审查报告路径",
        "category": "code_review|design|security|performance|other",
        "severity": "critical|high|normal|low",
        "affected_components": ["component_a", "component_b"]
    }
    """
    body = handler._read_post_body()
    task_id = body.get("task_id", "")
    reviewer = body.get("reviewer", "")
    result = body.get("result", "")
    issues = body.get("issues", None)
    summary = body.get("summary", "")
    report_file = body.get("report_file", "")
    category = body.get("category", "")
    severity = body.get("severity", "normal")
    affected_components = body.get("affected_components", None)

    if not task_id:
        handler._send_json({"error": "缺少 task_id"}, 400)
        return
    if not reviewer:
        handler._send_json({"error": "缺少 reviewer"}, 400)
        return
    if result not in ("pass", "fail", "warn"):
        handler._send_json({"error": "result 必须是 pass/fail/warn"}, 400)
        return
    if reviewer not in ("lingjian", "lingyan"):
        handler._send_json({"error": "reviewer 不在白名单（lingjian/lingyan）"}, 403)
        return
    if severity not in ("critical", "high", "normal", "low"):
        handler._send_json({"error": "severity 必须是 critical/high/normal/low"}, 400)
        return

    tracker = TaskTracker(handler.data_dir)
    task = tracker.add_audit(
        task_id=task_id,
        reviewer=reviewer,
        result=result,
        issues=issues,
        summary=summary,
        report_file=report_file,
        category=category,
        severity=severity,
        affected_components=affected_components,
    )
    if not task:
        handler._send_json({"error": f"任务 {task_id} 不存在"}, 404)
        return
    handler._send_json({"status": "ok", "task": task})


def handle_task_get(handler, task_id: str):
    """GET /api/tasks/<task_id> — 获取单任务详情"""
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"error": "not_found"}, 404)
        return
    _normalize_tasks_for_api([task])
    handler._send_json({"task": task})


def handle_task_audit_trend(handler):
    """GET /api/tasks/audit/stats/trend — 获取审计趋势（按日/周/月聚合）

    查询参数:
        ?period=day          — 聚合周期: day/week/month（默认 day）
        ?days=30             — 回溯天数（默认 30）

    返回:
    {
        "trend": [
            {"period": "2026-06-01", "total": 10, "pass": 8, "fail": 1, "warn": 1, "pass_rate": 80.0},
            ...
        ],
        "summary": {
            "total_audits": 100,
            "avg_pass_rate": 80.0,
            "period": "day",
            "days": 30
        }
    }
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    period = params.get("period", ["day"])[0]
    if period not in ("day", "week", "month"):
        period = "day"
    try:
        days = int(params.get("days", ["30"])[0])
    except (ValueError, TypeError):
        days = 30
    if days < 1:
        days = 1
    if days > 365:
        days = 365

    tracker = TaskTracker(handler.data_dir)
    result = tracker.audit_trend(period=period, days=days)
    handler._send_json(result)


def handle_task_audit_stats(handler):
    """GET /api/tasks/audit/stats — 获取审计聚合统计

    返回:
    {
        "total_tasks": 100,
        "audited_tasks": 45,
        "pending_audit_tasks": 12,
        "pass_count": 60,
        "fail_count": 5,
        "warn_count": 3,
        "pass_rate": 88.2,
        "total_audit_entries": 68,
        "by_reviewer": {"lingjian": {"pass": 30, "fail": 2, "warn": 1, "total": 33}, ...},
        "by_category": {"code_review": 40, "design": 10, ...},
        "by_severity": {"normal": 50, "high": 10, ...},
        "latest_audits": [...]
    }
    """
    tracker = TaskTracker(handler.data_dir)
    stats = tracker.audit_stats()
    handler._send_json(stats)


def handle_task_audit_pending(handler):
    """GET /api/tasks/audit/pending — 获取待审计任务列表

    查询参数:
        ?limit=50 — 最大返回数量（默认 50）
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    try:
        limit = int(params.get("limit", ["50"])[0])
    except (ValueError, TypeError):
        limit = 50

    tracker = TaskTracker(handler.data_dir)
    pending = tracker.list_pending_audit(limit=limit)
    handler._send_json({
        "tasks": pending,
        "count": len(pending),
        "limit": limit,
    })


def handle_bulletin(handler):
    """GET /api/bulletin — 获取公告板"""
    data = json_read(handler.bulletin_file, {"bulletins": []})
    handler._send_json(data)


def handle_bulletin_post(handler):
    """POST /api/bulletin/post — 发布公告"""
    body = handler._read_post_body()
    content = body.get("content", "").strip()
    author = body.get("author", "").strip()
    if not content:
        handler._send_json({"error": "缺少 content"}, 400)
        return
    data = json_read(handler.bulletin_file, {"bulletins": []})
    entry = {
        "id": f"bulletin-{_now_iso()[:10]}-{len(data['bulletins']) + 1}",
        "content": content,
        "author": author or "anonymous",
        "created_at": _now_iso(),
    }
    data["bulletins"].append(entry)
    json_write(handler.bulletin_file, data)
    handler._send_json({"status": "ok", "entry": entry})


def handle_bulletin_permit(handler):
    """POST /api/bulletin/permit — 配置公告权限"""
    body = handler._read_post_body()
    agents = body.get("agents", [])
    if not isinstance(agents, list):
        handler._send_json({"error": "agents 必须是列表"}, 400)
        return
    handler.bulletin_permit = agents
    # 持久化
    perm_data = json_read(handler.permission_file, {})
    perm_data["bulletin"] = agents
    json_write(handler.permission_file, perm_data)
    handler._send_json({"status": "ok", "permit": agents})


def handle_permission(handler):
    """GET/POST /api/permission — 权限管理"""
    if handler.command == "POST":
        body = handler._read_post_body()
        perm_data = json_read(handler.permission_file, {})
        if "permissions" in body and isinstance(body["permissions"], dict):
            perm_data["permissions"] = body["permissions"]
        if "bulletin" in body and isinstance(body["bulletin"], list):
            perm_data["bulletin"] = body["bulletin"]
        perm_data["updated_at"] = _now_iso()
        json_write(handler.permission_file, perm_data)
        handler._send_json({"status": "ok", "permissions": perm_data.get("permissions", {})})
    else:
        data = json_read(handler.permission_file, {})
        if "permissions" not in data:
            data = {"permissions": data, "bulletin": data.get("bulletin", [])}
        handler._send_json(data)


def handle_skill_usage(handler):
    """GET /api/skill-usage — 技能使用统计（聚合所有来源）"""
    data_dir = handler.data_dir
    merged = {}

    # 0. mailbus 统一 skill 使用记录
    bus_file = os.path.join(data_dir, "skill-usage.json")
    bus_data = json_read(bus_file, {})
    for skill, agent_data in bus_data.items():
        merged[skill] = {"agents": {}}
        for agent, rec in agent_data.items():
            merged[skill]["agents"][agent] = {
                "use_count": rec.get("use_count", 0),
                "view_count": rec.get("view_count", 0),
                "last_used": (rec.get("last_used") or "")[:16],
                "state": "active",
            }
        merged[skill]["total_use"] = sum(
            a.get("use_count", 0) for a in merged[skill]["agents"].values()
        )
        merged[skill]["total_view"] = sum(
            a.get("view_count", 0) for a in merged[skill]["agents"].values()
        )
        merged[skill]["last_used"] = max(
            (a.get("last_used", "") for a in merged[skill]["agents"].values()),
            default="",
        )

    # 1. Hermes usage.json（补充不在 bus 记录中的 skill）
    hermes_base = os.environ.get(
        "HERMES_DATA",
        "E:/hermes-data" if sys.platform == "win32" else "/mnt/e/hermes-data",
    ).replace("\\", "/").rstrip("/")
    hermes_profiles = {
        "lingzhao": f"{hermes_base}/.hermes/skills/.usage.json",
        "lingxi": f"{hermes_base}/.hermes/profiles/lingxi/skills/.usage.json",
    }
    for agent, path in hermes_profiles.items():
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for skill, rec in data.items():
                    if skill not in merged:
                        merged[skill] = {"agents": {}}
                    merged[skill]["agents"][agent] = {
                        "use_count": rec.get("use_count", 0),
                        "view_count": rec.get("view_count", 0),
                        "last_used": (rec.get("last_used_at") or "")[:16],
                        "state": rec.get("state", "active"),
                    }
                    merged[skill]["total_use"] = sum(
                        a.get("use_count", 0) for a in merged[skill]["agents"].values()
                    )
                    merged[skill]["total_view"] = sum(
                        a.get("view_count", 0) for a in merged[skill]["agents"].values()
                    )
                    merged[skill]["last_used"] = max(
                        (a.get("last_used", "") for a in merged[skill]["agents"].values()),
                        default="",
                    )
            except Exception:
                pass

    # 2. CLI 框架 skill 目录扫描（registry → host skills 路径）
    from ..sync_layers import dashboard_skills_dirs

    cli_skills = dashboard_skills_dirs()
    for agent, skill_dir in cli_skills.items():
        skill_dir = skill_dir.replace("\\", "/")
        if not os.path.isdir(skill_dir):
            continue
        for root, dirs, files in os.walk(skill_dir):
            for f in files:
                if f == "SKILL.md" or f.endswith("-skill.md"):
                    skill_name = os.path.basename(root) if f == "SKILL.md" else f.replace("-skill.md", "").replace(".md", "")
                    if skill_name:
                        if skill_name not in merged:
                            merged[skill_name] = {"agents": {}}
                        if agent not in merged[skill_name]["agents"]:
                            merged[skill_name]["agents"][agent] = {
                                "use_count": 0,
                                "view_count": 0,
                                "last_used": "",
                                "state": "installed",
                            }
                        merged[skill_name]["total_use"] = sum(
                            a.get("use_count", 0) for a in merged[skill_name]["agents"].values()
                        )
                        merged[skill_name]["last_used"] = max(
                            (a.get("last_used", "") for a in merged[skill_name]["agents"].values()),
                            default="",
                        )

    # 按使用次数排序
    sorted_skills = sorted(
        merged.items(),
        key=lambda x: -(x[1].get("total_use", 0) or 0),
    )
    handler._send_json({
        "skills": [{"name": n, **d} for n, d in sorted_skills],
        "total_skills": len(sorted_skills),
    })


def handle_skill_use(handler):
    """GET/POST /api/skill-use — 记录技能使用"""
    if handler.command == "POST":
        body = handler._read_post_body()
        skill = body.get("skill", "")
        agent = body.get("agent", "")
        if not skill or not agent:
            handler._send_json({"error": "缺少 skill 或 agent"}, 400)
            return
        skill_file = os.path.join(handler.data_dir, "skill-usage.json")
        data = json_read(skill_file, {})
        if skill not in data:
            data[skill] = {}
        if agent not in data[skill]:
            data[skill][agent] = {"use_count": 0, "view_count": 0, "last_used": ""}
        data[skill][agent]["use_count"] += 1
        data[skill][agent]["last_used"] = _now_iso()
        json_write(skill_file, data)
        handler._send_json({"status": "ok"})
    else:
        handle_skill_usage(handler)


def handle_task_fsm_get(handler, task_id: str):
    """GET /api/tasks/<task_id>/fsm — 状态机摘要（Dashboard 用）。"""
    from lib.adapters.orchestration.task_fsm import ensure_fsm, fsm_summary

    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"error": "not_found"}, 404)
        return
    ensure_fsm(task)
    handler._send_json({"status": "ok", "fsm": fsm_summary(task)})


def handle_human_queue(handler):
    """GET /api/human-queue — 人工待办列表。"""
    from lib.composition import build_orchestration
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(handler.path)
    qs = parse_qs(parsed.query or "")
    status = (qs.get("status") or ["pending"])[0]
    qtype = (qs.get("type") or [""])[0]
    task_id = (qs.get("task_id") or [""])[0]
    intake_id = (qs.get("intake_id") or [""])[0]
    try:
        limit = int((qs.get("limit") or ["50"])[0])
        offset = int((qs.get("offset") or ["0"])[0])
    except ValueError:
        handler._send_json({"error": "invalid limit/offset"}, 400)
        return

    orch = build_orchestration(handler.data_dir)
    items, meta = orch.human_gate.list_items(
        status=status,
        qtype=qtype,
        task_id=task_id,
        intake_id=intake_id,
        limit=limit,
        offset=offset,
    )
    handler._send_json({
        "status": "ok",
        "version": meta["version"],
        "updated_at": meta["updated_at"],
        "total": meta["total"],
        "items": items,
    })


def handle_human_queue_resolve(handler, item_id: str):
    """POST /api/human-queue/<id>/resolve — 审批/驳回人工待办。"""
    from lib.composition import build_orchestration

    body = handler._read_post_body()
    decision = (body.get("decision") or "approved").lower()
    if decision not in ("approved", "denied"):
        handler._send_json({"error": "decision must be approved or denied"}, 400)
        return
    resolution = {
        "decision": decision,
        "reviewer": body.get("reviewer") or "dashboard",
        "comment": body.get("comment") or body.get("reason") or "",
        "reason": body.get("reason") or "",
    }
    for key in ("attachments", "selected_copy_id", "brief", "action"):
        if key in body:
            resolution[key] = body[key]
    orch = build_orchestration(handler.data_dir)
    out = orch.human_gate.resolve(item_id, resolution)
    item, side = out.get("item"), out.get("side") or {}
    if not item:
        handler._send_json({"error": side.get("error", "not_found")}, 404)
        return
    if side.get("error") and not side.get("ok", True):
        handler._send_json({"status": "partial", "item": item, **side}, 400)
        return
    handler._send_json({"status": "ok", "item": item, **side})


def handle_task_fsm_action(handler, task_id: str, action: str):
    """POST /api/tasks/<id>/fsm/{rollback|skip|cancel|pause|priority}"""
    from lib.adapters.orchestration.task_fsm import (
        apply_cancel,
        apply_pause,
        apply_rollback,
        apply_skip,
        ensure_fsm,
        fsm_summary,
    )

    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"error": "not_found"}, 404)
        return

    body = handler._read_post_body() if handler.command == "POST" else {}
    reason = body.get("reason", "")

    if action == "approve-plan":
        from lib.application.orchestration.actions import apply_approve_plan

        outcome = apply_approve_plan(task, body, data_dir=handler.data_dir)
        if not outcome.get("ok"):
            code = 400
            handler._send_json({"status": "error", **outcome}, code)
            return
        json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        handler._send_json({
            "status": "ok",
            "fsm": fsm_summary(task),
            "dispatch_ok": outcome.get("dispatch_ok"),
            "action": outcome.get("action"),
        })
        return

    if action == "accept":
        from lib.application.orchestration.actions import apply_accept
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step
        from lib.adapters.orchestration.task_fsm import mark_step_dispatched

        outcome = apply_accept(task, body, data_dir=handler.data_dir)
        if not outcome.get("ok"):
            handler._send_json({"status": "error", **outcome}, 400)
            return
        json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        dispatch_ok = None
        nxt = outcome.get("next_step")
        if nxt:
            dispatch_ok = dispatch_fsm_step(
                handler.data_dir, task_id, nxt,
                summary=body.get("reason") or task.get("summary", ""),
            )
            if dispatch_ok:
                mark_step_dispatched(nxt)
                json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        handler._send_json({
            "status": "ok",
            "fsm": fsm_summary(task),
            "action": outcome.get("action"),
            "dispatch_ok": dispatch_ok,
        })
        return

    if action == "rollback":
        outcome = apply_rollback(
            task,
            to_step=body.get("to_step"),
            to_person=body.get("to_agent") or body.get("to_person"),
            reason=reason,
        )
    elif action == "skip":
        outcome = apply_skip(task, reason=reason)
    elif action == "cancel":
        outcome = apply_cancel(
            task, reason=reason, data_dir=handler.data_dir, agents=handler.agents,
        )
    elif action == "continue":
        from lib.application.orchestration.task_recover import recover_continue

        outcome = recover_continue(
            handler.data_dir, task_id, reason=reason or "dashboard_continue",
        )
        if outcome.get("ok"):
            task = tracker.get(task_id) or task
            ensure_fsm(task)
            handler._send_json({
                "status": "ok",
                "action": outcome.get("action"),
                "fsm": fsm_summary(task),
                "dispatch_ok": outcome.get("dispatch_ok"),
                "step_id": outcome.get("step_id"),
            })
            return
    elif action == "pause":
        outcome = apply_pause(task, reason=reason)
    elif action == "priority":
        ensure_fsm(task)
        p = body.get("priority")
        if p is None:
            handler._send_json({"error": "missing priority"}, 400)
            return
        task["fsm"]["priority"] = int(p)
        outcome = {"ok": True, "action": "priority", "task": task}
    else:
        handler._send_json({"error": f"unknown action: {action}"}, 400)
        return

    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, 400)
        return

    task_path = os.path.join(handler.data_dir, "tasks", f"{task_id}.json")
    json_write(task_path, task)

    dispatch_ok = None
    if action == "rollback" and outcome.get("next_step"):
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step
        from lib.adapters.orchestration.task_fsm import mark_step_dispatched

        nxt = outcome["next_step"]
        dispatch_ok = dispatch_fsm_step(
            handler.data_dir,
            task_id,
            nxt,
            summary=reason or task.get("summary", ""),
        )
        if dispatch_ok:
            mark_step_dispatched(nxt)
            json_write(task_path, task)
        else:
            from lib.infra.mbus_log import warn
            warn(f"[api] rollback dispatch failed task={task_id[:24]}")

    handler._send_json({
        "status": "ok",
        "action": outcome.get("action"),
        "fsm": fsm_summary(task),
        "next_step": outcome.get("next_step"),
        "dispatch_ok": dispatch_ok,
    })
