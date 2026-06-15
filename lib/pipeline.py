"""ziyan-mailbus 管道引擎

提供 PipelineEngine 类用于任务链自动流转、超时检测、状态推进。"""

from typing import Optional
from datetime import datetime, timezone, timedelta
from .models import MsgStatus
from .utils import _now_iso


# 各角色 SLA 超时标准（分钟）
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
    """管道引擎 —— 管理任务链自动流转。"""

    def check(self, task: dict) -> dict:
        """检查任务链的当前步骤，返回催办建议。
        
        Args:
            task: 任务字典，含 chain 列表
            
        Returns:
            {"remind": bool, "step": dict or None, "reason": str}
        """
        chain = task.get("chain", [])
        if not chain:
            return {"remind": False, "step": None, "reason": "无任务链"}
        
        current = chain[-1]  # 当前步骤
        status = current.get("status", "")
        
        if status not in ("running", "processing", "acknowledged"):
            return {"remind": False, "step": current, "reason": f"状态={status}，无需催办"}
        
        # 计算已耗时
        started = current.get("started_at", current.get("started_at", ""))
        if not started:
            return {"remind": False, "step": current, "reason": "无开始时间"}
        
        try:
            start_time = datetime.fromisoformat(started)
            now = datetime.now(timezone(timedelta(hours=8)))
            elapsed = (now - start_time).total_seconds() / 60
        except (ValueError, TypeError):
            return {"remind": False, "step": current, "reason": "时间解析失败"}
        
        # 获取该角色的 SLA 超时标准
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
                "reason": f"{role} ({current.get('to_person','?')}) 已执行 {elapsed:.0f} 分钟，超过 SLA {timeout_min} 分钟"
            }
        
        return {"remind": False, "step": current, "reason": f"正在处理中（{elapsed:.0f}/{timeout_min} 分钟）"}
    
    def advance(self, task: dict, report: dict) -> dict:
        """推进任务链到下一步。
        
        根据当前角色的结论（report.conclusion）自动决定下一步角色（to_role）。
        
        Args:
            task: 任务字典
            report: 当前步骤完成的报告（含 conclusion 字段）
            
        Returns:
            {"ok": bool, "next_role": str or None, "next_person": str or None, "error": str}
        """
        from .role_flow import get_next_role, pick_person_for_role
        
        chain = task.get("chain", [])
        if not chain:
            return {"ok": False, "error": "无任务链"}
        
        current = chain[-1]
        current_role = current.get("to_role", "")
        conclusion = report.get("conclusion", "")
        
        # 根据角色+结论获取下一步角色
        next_role = get_next_role(current_role, conclusion)
        if next_role is None:
            # 没有下一步 = 任务完成
            current["status"] = "completed"
            current["completed_at"] = _now_iso()
            current["report"] = report
            return {"ok": True, "next_role": None, "next_person": None}
        
        # 分配具体执行人
        next_person = pick_person_for_role(next_role)
        
        # 标记当前步骤完成
        current["status"] = "completed"
        current["completed_at"] = _now_iso()
        current["report"] = report
        
        # 创建下一步
        next_step = {
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
        }
        chain.append(next_step)
        
        return {"ok": True, "next_role": next_role, "next_person": next_person}

    def run(self, task: dict, report: dict = None) -> dict:
        """运行管道引擎：检查当前步骤状态，并在提供报告时推进任务链。

        整合 check() 和 advance() 两个方法：
        1. 先检查当前步骤是否需要催办（超时提醒）
        2. 如果提供了 report，则调用 advance() 推进到下一步
        3. 返回管道执行结果

        Args:
            task: 任务字典，含 chain 列表
            report: 当前步骤完成的报告（可选）。含 conclusion 字段时触发 advance。

        Returns:
            dict:
                - 催办场景: {"remind": True, "step": ..., "reason": ..., ...}
                - 推进场景: {"ok": True, "next_role": ..., "next_person": ...}
                - 仅检查场景: {"ok": True, "status": "running", "step": ..., "reason": ...}
        """
        # 1. 检查当前步骤是否需要催办
        check_result = self.check(task)
        if check_result.get("remind"):
            return check_result

        # 2. 如果有 report，推进任务链到下一步
        if report:
            advance_result = self.advance(task, report)
            return advance_result

        # 3. 无 report，仅返回当前运行状态
        return {
            "ok": True,
            "status": "running",
            "step": check_result.get("step"),
            "reason": check_result.get("reason", "正常运行中"),
        }
