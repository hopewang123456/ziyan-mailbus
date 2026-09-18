"""mailbus HTTP API — agent step-result 提交（工单执行回执）。

POST /api/agents/<agent_id>/step-result
body: {"task_id": "...", "step_id": "s1", "conclusion": "done", "summary": "...", "artifacts": ["..."]}
"""

from __future__ import annotations

_DONE_CONCLUSIONS = frozenset({
    "done", "pass", "approved", "fail", "dispatched", "rejected",
    "need_research", "blocked", "warning",
})


def handle_agent_step_result(handler, agent_id: str):
    body = handler._read_post_body()
    task_id = str(body.get("task_id") or "").strip()
    step_id = str(body.get("step_id") or "").strip()
    conclusion = str(body.get("conclusion") or "done").strip().lower() or "done"
    summary = str(body.get("summary") or body.get("text") or "")
    artifacts = body.get("artifacts") or []

    if not task_id or not step_id:
        handler._send_json(
            {"status": "error", "error": "missing_fields",
             "message": "task_id 和 step_id 必填"}, 400)
        return
    if conclusion not in _DONE_CONCLUSIONS:
        handler._send_json(
            {"status": "error", "error": "invalid_conclusion",
             "message": f"conclusion 可选值: {', '.join(sorted(_DONE_CONCLUSIONS))}"}, 400)
        return

    # 仅允许字母数字与 -_.，防路径逃逸
    for part in (task_id, step_id):
        if not all(c.isalnum() or c in "-_." for c in part) or part.startswith("."):
            handler._send_json(
                {"status": "error", "error": "invalid_id",
                 "message": "task_id/step_id 含非法字符"}, 400)
            return

    from lib.core.a2a.step_result_io import write_step_result_file

    positive = conclusion in ("done", "pass", "approved")
    result = {
        "status": "completed" if positive else "error",
        "conclusion": conclusion,
        "summary": summary,
        "agent": agent_id,
    }
    if artifacts:
        result["artifacts"] = [str(a) for a in artifacts][:20]
    path = write_step_result_file(
        handler.data_dir, task_id, step_id, result, agent=agent_id)

    handler._send_json({
        "status": "ok",
        "result_path": path,
        "note": "结果已落盘；调度器 scan（或 mailbus scan）将推进工单 FSM",
    }, 200)
