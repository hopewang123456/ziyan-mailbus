"""
ziyan-mailbus HTTP API — 任务/公告板/Skill 相关路由处理器

处理: /api/tasks, /api/bulletin, /api/bulletin/post, /api/bulletin/permit,
      /api/permission, /api/skill-usage, /api/skill-use
"""

import os
import json
from lib.utils import json_read, json_write, _now_iso
from lib.tracker import TaskTracker


def handle_tasks(handler):
    """GET /api/tasks — 获取任务追踪列表"""
    tracker = TaskTracker(handler.data_dir)
    tasks = tracker.list_all(handler.agents)
    handler._send_json({"tasks": tasks})


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
    """GET /api/skill-usage — 技能使用统计"""
    skill_file = os.path.join(handler.data_dir, "skill-usage.json")
    data = json_read(skill_file, {})
    handler._send_json(data)


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
