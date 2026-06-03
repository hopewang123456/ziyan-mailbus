"""
ziyan-mailbus HTTP API — 任务/公告板/Skill 相关路由处理器

处理: /api/tasks, /api/bulletin, /api/bulletin/post, /api/bulletin/permit,
      /api/permission, /api/skill-usage, /api/skill-use
"""

import os
import json
from lib.utils import json_read, json_write, _now_iso
from lib.tracker import TaskTracker, TaskStatus


def handle_tasks(handler):
    """GET /api/tasks — 获取任务追踪列表"""
    tracker = TaskTracker(handler.data_dir)
    tasks = tracker.list_all()
    handler._send_json({"tasks": tasks, "count": len(tasks)})


def handle_task_create(handler):
    """POST /api/tasks/create — 创建新任务"""
    body = handler._read_post_body()
    task_id = body.get("task_id", "")
    summary = body.get("summary", "")
    assignee = body.get("assignee", "")
    deliverable = body.get("deliverable", "")
    chain_hops = body.get("chain", None)

    if not task_id:
        handler._send_json({"error": "缺少 task_id"}, 400)
        return
    if not summary:
        handler._send_json({"error": "缺少 summary"}, 400)
        return

    tracker = TaskTracker(handler.data_dir)
    existing = tracker.get(task_id)
    if existing:
        handler._send_json({"error": f"任务 {task_id} 已存在"}, 409)
        return

    task = tracker.create(
        task_id=task_id,
        summary=summary,
        assignee=assignee,
        deliverable=deliverable,
        chain_hops=chain_hops,
    )
    handler._send_json({"status": "ok", "task": task}, 201)


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
    """POST /api/tasks/audit — 追加审计记录到任务"""
    body = handler._read_post_body()
    task_id = body.get("task_id", "")
    reviewer = body.get("reviewer", "")
    result = body.get("result", "")
    issues = body.get("issues", None)
    summary = body.get("summary", "")
    report_file = body.get("report_file", "")

    if not task_id:
        handler._send_json({"error": "缺少 task_id"}, 400)
        return
    if not reviewer:
        handler._send_json({"error": "缺少 reviewer"}, 400)
        return
    if result not in ("pass", "fail", "warn"):
        handler._send_json({"error": "result 必须是 pass/fail/warn"}, 400)
        return

    tracker = TaskTracker(handler.data_dir)
    task = tracker.add_audit(
        task_id=task_id,
        reviewer=reviewer,
        result=result,
        issues=issues,
        summary=summary,
        report_file=report_file,
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
    handler._send_json({"task": task})


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
        perm_data.update(body)
        json_write(handler.permission_file, perm_data)
        handler._send_json({"status": "ok"})
    else:
        data = json_read(handler.permission_file, {})
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
    hermes_profiles = {
        "lingzhao": "/mnt/e/hermes-data/.hermes/skills/.usage.json",
        "lingxi": "/mnt/e/hermes-data/.hermes/profiles/lingxi/skills/.usage.json",
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

    # 2. CLI 框架 skill 目录扫描（只有名称，没有使用次数）
    cli_skills = {
        "lingxiao": "/home/administrator/.codex/skills",
        "xiaoqi": "/mnt/e/ai_tools/openclaw_space/skills",
        "yige": "/mnt/e/ai_tools/openclaw_space/skills",
        "dali": "/mnt/e/ai_tools/opencode/.opencode/skills",
        "lingjin": "/mnt/e/hermes-data/.hermes/profiles/lingjin/skills",
    }
    for agent, skill_dir in cli_skills.items():
        if os.path.isdir(skill_dir):
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
