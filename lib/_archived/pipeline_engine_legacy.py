"""历史 PipelineEngine — 未被生产路径引用，保留供参考。

替代方案：lib/task_fsm.py + lib/pipeline_trigger.py
设计文档：store/rules/task-fsm.md
"""

from typing import Optional
from datetime import datetime, timezone, timedelta
from ..utils import _now_iso

ROLE_TIMEOUT = {
    "开发工程师": 30,
    "审查官": 15,
    "测试工程师": 30,
    "验收员": 10,
    "调度员": 10,
    "安全审计师": 30,
    "技术研究员": 60,
    "巡检官": 15,
    "运营": 30,
    "方案设计师": 30,
}


class PipelineEngine:
    """管道引擎 —— 管理任务链自动流转（legacy）。"""

    def check(self, task: dict) -> dict:
        chain = task.get("chain", [])
        if not chain:
            return {"remind": False, "step": None, "reason": "无任务链"}
        current = chain[-1]
        status = current.get("status", "")
        if status not in ("running", "processing", "acknowledged"):
            return {"remind": False, "step": current, "reason": f"状态={status}，无需催办"}
        started = current.get("started_at", "")
        if not started:
            return {"remind": False, "step": current, "reason": "无开始时间"}
        try:
            start_time = datetime.fromisoformat(started)
            now = datetime.now(timezone(timedelta(hours=8)))
            elapsed = (now - start_time).total_seconds() / 60
        except (ValueError, TypeError):
            return {"remind": False, "step": current, "reason": "时间解析失败"}
        role = current.get("to_role", "")
        timeout_min = ROLE_TIMEOUT.get(role, 15)
        if elapsed >= timeout_min:
            return {
                "remind": True,
                "step": current,
                "to_person": current.get("to_person", ""),
                "to_role": role,
                "elapsed_min": round(elapsed, 1),
                "timeout_min": timeout_min,
                "reason": f"{role} 已执行 {elapsed:.0f} 分钟，超过 SLA {timeout_min} 分钟",
            }
        return {"remind": False, "step": current, "reason": f"正在处理中（{elapsed:.0f}/{timeout_min} 分钟）"}

    def advance(self, task: dict, report: dict) -> dict:
        from ..role_flow import get_next_role, pick_person_for_role
        chain = task.get("chain", [])
        if not chain:
            return {"ok": False, "error": "无任务链"}
        current = chain[-1]
        current_role = current.get("to_role", "")
        conclusion = report.get("conclusion", "")
        next_role = get_next_role(current_role, conclusion)
        if next_role is None:
            current["status"] = "completed"
            current["completed_at"] = _now_iso()
            current["report"] = report
            return {"ok": True, "next_role": None, "next_person": None}
        next_person = pick_person_for_role(next_role)
        current["status"] = "completed"
        current["completed_at"] = _now_iso()
        current["report"] = report
        chain.append({
            "step": len(chain) + 1,
            "from_role": current_role,
            "from_person": current.get("to_person", ""),
            "to_role": next_role,
            "to_person": next_person,
            "action": f"等待{next_role}处理",
            "status": "running",
            "started_at": _now_iso(),
            "completed_at": None,
            "report": None,
        })
        return {"ok": True, "next_role": next_role, "next_person": next_person}

    def run(self, task: dict, report: dict = None) -> dict:
        check_result = self.check(task)
        if check_result.get("remind"):
            return check_result
        if report:
            return self.advance(task, report)
        return {
            "ok": True,
            "status": "running",
            "step": check_result.get("step"),
            "reason": check_result.get("reason", "正常运行中"),
        }
