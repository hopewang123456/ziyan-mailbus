"""
mailbus HTTP API — 任务/公告板/Skill 相关路由处理器

处理: /api/tasks, /api/bulletin, /api/bulletin/post, /api/bulletin/permit,
      /api/permission, /api/skill-usage, /api/skill-use
"""

import os
import json
import sys
from lib.infra.utils import json_read, json_write, _now_iso
from lib import composition
from lib.application.orchestration.tracker import (
    TaskTracker,
    TaskStatus,
    SKIP_TIMEOUT_PREFIXES,
    append_task_event,
)
from lib.application.orchestration.pipeline.chain import normalize_task_chain, is_pipeline_step

# Dashboard 默认分页（无 query 时也生效，避免一次返回 400+ 任务拖死浏览器）
DEFAULT_TASKS_LIMIT = 120


def _is_noise_task_id(task_id: str) -> bool:
    if not task_id:
        return True
    return any(task_id.startswith(p) for p in SKIP_TIMEOUT_PREFIXES)


def _normalize_tasks_for_api(tasks: list, data_dir: str = "") -> list:
    """API 返回前规范化 chain 格式，并补全 audit_reviewer / needs_audit / fsm。"""
    from lib.application.orchestration.audit_dispatch import task_requires_audit

    for task in tasks:
        normalize_task_chain(task)
        chain = task.get("chain") or []
        if chain and is_pipeline_step(chain[0]) and not task.get("audit_reviewer"):
            from lib.infra.org_defaults import org_default
            task["audit_reviewer"] = org_default(data_dir, "reviewer")
        task["needs_audit"] = task_requires_audit(task)
        if chain and is_pipeline_step(chain[0]):
            composition.ensure_fsm(task)
            task["fsm"] = composition.fsm_summary(task)
    return tasks


def handle_tasks(handler):
    """GET /api/tasks — 获取任务追踪列表，支持查询参数过滤

    查询参数:
        ?status=success          — 按状态过滤
        ?assignee=agent-a       — 按负责人过滤
        &audit_status=audited    — 审计状态 (audited/pending-audit)
        &audit_status=pending-audit
        &reviewer=agent-c       — 按审查人过滤
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
        result["tasks"] = _normalize_tasks_for_api(tasks, handler.data_dir)
        handler._send_json(result)
    else:
        all_tasks = tracker.list_all()
        if exclude_noise:
            all_tasks = [t for t in all_tasks if not _is_noise_task_id(t.get("task_id", ""))]
        total = len(all_tasks)
        page = all_tasks[offset:offset + limit]
        handler._send_json({
            "tasks": _normalize_tasks_for_api(page, handler.data_dir),
            "count": len(page),
            "total": total,
            "limit": limit,
            "offset": offset,
            "exclude_noise": exclude_noise,
        })


def _plan_task_with_deadline(envelope: dict, *, data_dir: str, config: dict, default_timeout: float = 45.0) -> dict:
    """plan_task 带总超时闸。

    internal LLM 慢/挂时同步 HTTP 请求会假死（实测 ~6 分钟）；超时后降级为
    Tier-0 单步兜底链（role_type=1），建单立刻返回，plan_meta 标注
    timeout_fallback。超时秒数可经 config.mailbus_internal_llm.plan_timeout_seconds 调整。
    """
    import threading
    from lib.application.orchestration.router.planner import PlanError, plan_task

    llm_cfg = (config or {}).get("mailbus_internal_llm") or {}
    try:
        timeout = float(llm_cfg.get("plan_timeout_seconds") or default_timeout)
    except (TypeError, ValueError):
        timeout = default_timeout

    result: dict = {}

    def _run():
        try:
            result["out"] = plan_task(envelope, data_dir=data_dir, config=config)
        except PlanError as exc:
            result["error"] = exc
        except Exception as exc:  # planner 自身异常按 plan_failed 处理
            result["error"] = PlanError("plan_failed", f"planner crashed: {exc}")

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    if "out" in result:
        return result["out"]
    if worker.is_alive():
        return {
            "planned_chain": [{"role_type": 1, "reason": "plan_timeout_fallback"}],
            "plan_meta": {
                "method": "timeout_fallback",
                "task_type_guess": envelope.get("task_type"),
                "confidence": 0.1,
                "provider_used": "none",
            },
        }
    raise result.get("error") or PlanError("plan_failed", "planner failed")


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
            out = _plan_task_with_deadline(body, data_dir=data_dir, config=config)
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
        "reviewer": "agent-c",
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
    from lib.infra.org_defaults import org_default_list
    reviewers = org_default_list(handler.data_dir, "audit_reviewers")
    if reviewer not in reviewers:
        handler._send_json(
            {"error": f"reviewer 不在白名单（{'/'.join(reviewers)}）"}, 403
        )
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
    _normalize_tasks_for_api([task], handler.data_dir)
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
        "by_reviewer": {"agent-c": {"pass": 30, "fail": 2, "warn": 1, "total": 33}, ...},
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
        "<HERMES_DATA>" if sys.platform == "win32" else "/mnt/<HERMES_DATA>",
    ).replace("\\", "/").rstrip("/")
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents_cfg = cfg.get("agents") or {}
    hermes_profiles = {}
    for agent_id, ac in agents_cfg.items():
        if (ac or {}).get("type") not in ("hermes", "hermes_profile"):
            continue
        profile = (ac or {}).get("profile") or ""
        if profile:
            hermes_profiles[agent_id] = (
                f"{hermes_base}/.hermes/profiles/{profile}/skills/.usage.json"
            )
        else:
            hermes_profiles[agent_id] = f"{hermes_base}/.hermes/skills/.usage.json"
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


def handle_manager_pending(handler):
    """GET /api/manager/pending — 管理者「待我处理」聚合（协调台数据源）。"""
    from lib.application.queries.manager import manager_pending

    handler._send_json(manager_pending(handler.data_dir))


def handle_task_fsm_get(handler, task_id: str):
    """GET /api/tasks/<task_id>/fsm — 状态机摘要（Dashboard 用）。"""
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"error": "not_found"}, 404)
        return
    composition.ensure_fsm(task)
    handler._send_json({"status": "ok", "fsm": composition.fsm_summary(task)})


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
    for key in ("attachments", "selected_copy_id", "brief", "action",
                "agent", "station"):  # station_vacancy 裁决：临时指名 / 改派工位
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
        append_task_event(task, "fsm:approve_plan", actor="manager", note=reason)
        json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        handler._send_json({
            "status": "ok",
            "fsm": composition.fsm_summary(task),
            "dispatch_ok": outcome.get("dispatch_ok"),
            "action": outcome.get("action"),
        })
        return

    if action == "approve-join":
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step

        outcome = composition.apply_approve_join(task, body, data_dir=handler.data_dir)
        if not outcome.get("ok"):
            handler._send_json({"status": "error", **outcome}, 400)
            return
        append_task_event(task, "fsm:approve_join", actor="manager", note=reason)
        json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        dispatch_ok = None
        nxt = outcome.get("next_step")
        if nxt:
            dispatch_ok = dispatch_fsm_step(
                handler.data_dir, task_id, nxt,
                summary=body.get("reason") or task.get("summary", ""),
            )
            if dispatch_ok:
                composition.mark_step_dispatched(nxt)
                json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        handler._send_json({
            "status": "ok",
            "fsm": composition.fsm_summary(task),
            "action": outcome.get("action"),
            "dispatch_ok": dispatch_ok,
            "next_person": outcome.get("next_person"),
        })
        return

    if action == "accept":
        from lib.application.orchestration.actions import apply_accept
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step

        outcome = apply_accept(task, body, data_dir=handler.data_dir)
        if not outcome.get("ok"):
            handler._send_json({"status": "error", **outcome}, 400)
            return
        append_task_event(task, "fsm:accept", actor="manager", note=reason)
        json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        dispatch_ok = None
        nxt = outcome.get("next_step")
        if nxt:
            dispatch_ok = dispatch_fsm_step(
                handler.data_dir, task_id, nxt,
                summary=body.get("reason") or task.get("summary", ""),
            )
            if dispatch_ok:
                composition.mark_step_dispatched(nxt)
                json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
        handler._send_json({
            "status": "ok",
            "fsm": composition.fsm_summary(task),
            "action": outcome.get("action"),
            "dispatch_ok": dispatch_ok,
        })
        return

    if action == "rollback":
        outcome = composition.apply_rollback(
            task,
            to_step=body.get("to_step"),
            to_person=body.get("to_agent") or body.get("to_person"),
            reason=reason,
        )
    elif action == "skip":
        outcome = composition.apply_skip(task, reason=reason)
    elif action == "cancel":
        outcome = composition.apply_cancel(
            task, reason=reason, data_dir=handler.data_dir, agents=handler.agents,
        )
    elif action == "continue":
        from lib.application.orchestration.task_recover import recover_continue

        outcome = recover_continue(
            handler.data_dir, task_id, reason=reason or "dashboard_continue",
        )
        if outcome.get("ok"):
            task = tracker.get(task_id) or task
            append_task_event(task, "fsm:continue", actor="manager", note=reason)
            json_write(os.path.join(handler.data_dir, "tasks", f"{task_id}.json"), task)
            composition.ensure_fsm(task)
            handler._send_json({
                "status": "ok",
                "action": outcome.get("action"),
                "fsm": composition.fsm_summary(task),
                "dispatch_ok": outcome.get("dispatch_ok"),
                "step_id": outcome.get("step_id"),
            })
            return
    elif action == "pause":
        outcome = composition.apply_pause(task, reason=reason)
    elif action == "priority":
        composition.ensure_fsm(task)
        p = body.get("priority")
        if p is None:
            handler._send_json({"error": "missing priority"}, 400)
            return
        try:
            task["fsm"]["priority"] = int(p)
        except (TypeError, ValueError):
            handler._send_json({"error": "invalid priority", "hint": "需要整数"}, 400)
            return
        outcome = {"ok": True, "action": "priority", "task": task}
    else:
        handler._send_json({"error": f"unknown action: {action}"}, 400)
        return

    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, 400)
        return

    task_path = os.path.join(handler.data_dir, "tasks", f"{task_id}.json")
    append_task_event(
        task,
        "fsm:" + action.replace("-", "_"),
        actor="manager",
        note=reason,
        data={
            "to_step": body.get("to_step") or "",
            "to_agent": body.get("to_agent") or body.get("to_person") or "",
        },
    )
    json_write(task_path, task)

    dispatch_ok = None
    if action == "rollback" and outcome.get("next_step"):
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step

        nxt = outcome["next_step"]
        dispatch_ok = dispatch_fsm_step(
            handler.data_dir,
            task_id,
            nxt,
            summary=reason or task.get("summary", ""),
        )
        if dispatch_ok:
            composition.mark_step_dispatched(nxt)
            json_write(task_path, task)
        else:
            from lib.infra.mbus_log import warn
            warn(f"[api] rollback dispatch failed task={task_id[:24]}")

    handler._send_json({
        "status": "ok",
        "action": outcome.get("action"),
        "fsm": composition.fsm_summary(task),
        "next_step": outcome.get("next_step"),
        "dispatch_ok": dispatch_ok,
    })


def handle_task_trace(handler):
    """GET /api/tasks/trace?id=<task_id> — E9 生命周期回放时序。"""
    qs = handler.path.split("?", 1)[1] if "?" in handler.path else ""
    params = dict(part.split("=", 1) for part in qs.split("&") if "=" in part)
    task_id = params.get("id", "").strip()
    if not task_id:
        handler._send_json({"status": "error", "error": "id required"}, 400)
        return
    from lib.application.ops.task_trace import task_trace

    try:
        trace = task_trace(handler.data_dir, task_id)
        handler._send_json({"status": "ok", "trace": trace})  # task 状态放 trace.status，不覆盖外层 ok
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 404)
    except Exception as exc:
        handler._send_json({"status": "error", "error": str(exc)[:300]}, 500)


def handle_command_draft(handler):
    """POST /api/command/draft — 发令窗口草稿预演（D4 草稿确认制）。

    入参 {"intent": "..."}；无副作用地走 plan_task（tier0 规则优先，
    无匹配时 internal LLM 生成——与正式创建同一逻辑，保证「所见即所发」），
    返回 planned_chain 供前端预览/调整；确认后前端按 mode=explicit 提交，
    不再二次规划。LLM/规划失败显式报错，不静默降级。
    """
    body = handler._read_post_body()
    intent = str(body.get("intent") or "").strip()
    if not intent:
        handler._send_api_error("fatal", 400, detail="缺少 intent（需求描述）")
        return

    from lib.application.orchestration.router.planner import PlanError, plan_task
    from lib.composition import llm_error_type

    envelope = {
        "task_id": f"draft-{handler.data_dir and '' or ''}",  # 占位；plan_task 不落盘
        "intent": intent,
        "initiator": "ziyan",
        "task_type": str(body.get("task_type") or "custom").lower(),
        "tier": str(body.get("tier") or "M"),
        "mode": "auto",  # auto 才会走 tier0→LLM 链；确认后前端改 explicit 提交
    }
    try:
        planned = plan_task(envelope, data_dir=handler.data_dir)
    except PlanError as exc:
        handler._send_json(
            {"status": "error", "error": exc.code, "message": str(exc)}, 422
        )
        return
    except llm_error_type() as exc:
        handler._send_json(
            {"status": "error", "error": "llm_error", "message": str(exc)}, 503
        )
        return
    chain = planned.get("planned_chain") or []
    # 防幻觉：role_type 全量校验（B6 精神——LLM 只翻译，口径由语义层把关）
    from lib.composition import get_locale

    valid = set(get_locale(handler.data_dir).valid_role_types())
    chain = [s for s in chain if int(s.get("role_type") or 0) in valid]
    if not chain:
        handler._send_json(
            {"status": "error", "error": "draft_empty",
             "message": "草稿为空（LLM 输出未含有效职位）"}, 422
        )
        return
    handler._send_json({
        "status": "ok",
        "draft": {
            "planned_chain": chain,
            "plan_meta": planned.get("plan_meta") or {},
            "intent": intent,
        },
    })


# ── P1 五批：子言被唤起消息聚合（D1 双向窗口的「被唤起」侧）─────────────────

_MP_ACTIONS = {
    # manager-pending / human-queue 的 bucket/type → 可执行 FSM 动作（label 中文）
    "plan_approval": [("approve-plan", "批准计划"), ("rollback", "回退")],
    "acceptance": [("accept", "验收"), ("rollback", "回退")],
    "coordination": [("continue", "继续"), ("rollback", "回退")],
}


def collect_command_inbox(data_dir: str) -> dict:
    """子言收件箱四路聚合的**纯函数**版本（不写响应）。

    GET /api/command/inbox 与 SSE /api/command/inbox/stream 共用，
    保证两条出口的载荷逐字段同形（PY4-A 双栈 SSE）。
    """
    import json as _json
    from lib.application.queries.manager import manager_pending
    from lib.composition import get_recent_alerts, load_human_queue
    from lib.infra.utils import json_read, resolve_paths

    items: list = []

    # 1) manager pending（计划待批/待终验/待协调）
    mp = manager_pending(data_dir)
    for it in (mp or {}).get("items") or []:
        bucket = str(it.get("bucket") or it.get("type") or "")
        task_id = str(it.get("task_id") or "")
        items.append({
            "source": "manager_pending",
            "id": f"mp:{task_id}:{bucket}",
            "ts": it.get("updated_at") or it.get("created_at") or "",
            "text": f"{it.get('title') or bucket}（{task_id}）",
            "tone": "warn",
            "task_id": task_id,
            "actions": [
                {"action": a, "label": label, "task_id": task_id}
                for a, label in _MP_ACTIONS.get(bucket, [])
            ],
        })

    # 2) human queue（pending；load_queue 返回全量，此处过滤）
    hq = load_human_queue(data_dir) or {}
    for it in (hq.get("items") or [])[:50]:
        if it.get("status") != "pending":
            continue
        itype = str(it.get("type") or "")
        task_id = str(it.get("task_id") or "")
        if any(i["id"] == f"mp:{task_id}:{itype}" for i in items):
            continue  # 与 manager-pending 重复的待批项
        items.append({
            "source": "human_queue",
            "id": f"hq:{it.get('id')}",
            "ts": it.get("created_at") or "",
            "text": f"{it.get('title') or itype}（{task_id or it.get('id')}）",
            "tone": "warn",
            "task_id": task_id,
            "actions": [
                {"action": a, "label": label, "task_id": task_id}
                for a, label in _MP_ACTIONS.get(itype, [])
            ],
        })

    # 3) alerts（severity 高者优先，取最近 5 条未消警）
    for al in (get_recent_alerts(data_dir, limit=5) or []):
        sev = str(al.get("severity") or "info")
        items.append({
            "source": "alert",
            "id": f"al:{al.get('id')}",
            "ts": str(al.get("ts") or al.get("time") or ""),
            "text": f"[{sev}] {al.get('message') or al.get('type')}",
            "tone": "critical" if sev == "critical" else "warn",
            "actions": [],
        })

    # 4) 子言真 inbox（第四批打通的收件通道；未读消息）
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], "ziyan", "inbox.json")
    inbox_doc = json_read(inbox_file, {})
    ziyan_unread = 0
    terminal = {"done", "closed", "rejected", "failed", "archived", "sent"}
    for m in (inbox_doc.get("messages") or [])[-20:]:
        state = m.get("state") or m.get("status") or ""
        if state in terminal:
            continue
        ziyan_unread += 1
        items.append({
            "source": "inbox",
            "id": f"in:{m.get('id')}",
            "ts": m.get("created_at") or "",
            "text": f"来自 {m.get('from')}：{(m.get('content') or '')[:120]}",
            "tone": "info",
            "actions": [],
        })

    return {
        "status": "ok",
        "identity": {"id": "ziyan"},
        "unread": len(items),
        "ziyan_inbox_unread": ziyan_unread,
        "items": items,
    }


def handle_command_inbox(handler):
    """GET /api/command/inbox — 子言收件箱聚合（四路 → 统一消息流）。

    一期 UI 聚合（P1 规划）：manager-pending + human-queue(pending) + alerts
    + 子言 inbox 未读；动作按钮走既有 /api/tasks/{id}/fsm/{action}。
    二期子言真节点通道就绪后，inbox 路为真收件（第四批已通）。
    """
    handler._send_json(collect_command_inbox(handler.data_dir))


def handle_command_inbox_stream(handler):
    """GET /api/command/inbox/stream — 收件箱聚合的 SSE 差量流。

    载荷与 GET /api/command/inbox 同形；变化才推 snapshot，无变化发心跳。
    """
    from lib.api.sse import (
        StreamLimitExceeded, acquire_stream_slot, begin_stream, end_stream,
        release_stream_slot, send_event, stream_snapshot,
    )
    from lib.core.a2a.config import load_transport_config

    try:
        acquire_stream_slot()
    except StreamLimitExceeded as exc:
        handler._send_api_error("too_many_streams", 503, detail=str(exc))
        return
    try:
        cfg = load_transport_config(data_dir=handler.data_dir).get("api") or {}
        begin_stream(handler)
        try:
            stream_snapshot(
                handler,
                lambda: collect_command_inbox(handler.data_dir),
                poll_sec=float(cfg.get("stream_poll_sec", 1.0)),
                timeout_sec=float(cfg.get("stream_timeout_sec", 300)),
                heartbeat_sec=float(cfg.get("stream_heartbeat_sec", 15)),
                max_events=int(cfg.get("stream_max_events", 0)),
            )
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端断开
        except Exception as exc:
            try:
                send_event(handler, "error", {"error": "stream_error", "message": str(exc)})
            except Exception:
                pass
        end_stream(handler)
    finally:
        release_stream_slot()


# ── P3 管理中心：职位（role_type）写端点 ────────────────────────────────

_POSITION_PATCH_KEYS = ("display", "candidates", "inputs", "default_sla_minutes", "key")


def handle_position_update(handler, role_type: int):
    """PATCH /api/positions/{role_type} — 管理中心编辑职位（D3 表单 schema 来源）。

    写 {data_dir}/roles/json/role-types.json（SoT 首选路径）——seed 不动。
    允许字段：display/candidates/inputs/default_sla_minutes/key（白名单）。
    inputs 逐项校验 name/type/required，type 限 string|text|enum|number|boolean。
    """
    from lib.infra.utils import json_read, json_write

    body = handler._read_post_body()
    fields = body.get("fields") if isinstance(body.get("fields"), dict) else body
    if not isinstance(fields, dict):
        handler._send_api_error("fatal", 400, detail="需要 fields 对象")
        return
    unknown = [k for k in fields if k not in _POSITION_PATCH_KEYS]
    if unknown:
        handler._send_api_error("fatal", 400, detail=f"不可编辑字段: {', '.join(unknown)}")
        return
    if "inputs" in fields:
        err = _validate_position_inputs(fields["inputs"])
        if err:
            handler._send_api_error("fatal", 400, detail=err)
            return

    path = os.path.join(handler.data_dir, "roles", "json", "role-types.json")
    doc = json_read(path, {})
    roles = doc.get("roles")
    if not isinstance(roles, dict):
        handler._send_api_error("not_found", 404, detail="role-types SoT 不存在或格式不符")
        return
    key = str(int(role_type))
    entry = roles.get(key)
    if not isinstance(entry, dict):
        handler._send_api_error("not_found", 404, detail=f"职位 role_type={role_type} 不存在")
        return
    entry = dict(entry)
    for k, v in fields.items():
        entry[k] = v
    roles[key] = entry
    doc["roles"] = roles
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, doc)
    handler._send_json({"status": "ok", "role_type": int(role_type), "entry": entry})


def _validate_position_inputs(inputs) -> str:
    if not isinstance(inputs, list):
        return "inputs 必须是数组"
    allowed = {"string", "text", "enum", "number", "boolean"}
    for i, f in enumerate(inputs):
        if not isinstance(f, dict):
            return f"inputs[{i}] 必须是对象"
        if not f.get("name"):
            return f"inputs[{i}] 缺 name"
        if f.get("type") not in allowed:
            return f"inputs[{i}].type 必须是 {'/'.join(sorted(allowed))}"
        if f.get("type") == "enum" and not f.get("options"):
            return f"inputs[{i}] enum 类型需 options"
    return ""

def handle_bulletin_permit_get(handler):
    """GET /api/bulletin/permit — 查询公告发布许可（读 permission.json，与 POST 写入同源）。

    迁表批一时曾读内存类属性（恒为初始 []），改为读持久化——java BulletinController 同语义。
    """
    from lib.infra.utils import json_read

    perm = json_read(handler.permission_file, {}) or {}
    permit = perm.get("bulletin")
    handler._send_json({"permit": permit if permit is not None else False})
