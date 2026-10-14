"""协同编排：planned_chain 扩展（并行分支 + 汇合 gate）。

设计说明（P0-1 起步版，2026-09-10）：
- 本模块只负责「编排契约 → 线性执行计划」的**解析与展开**：把包含
  ``{"kind":"parallel_join", "parallel":[{role_type,...},...], "join":{role_type,gate}}``
  的规划项展开成一组**顺序执行的角色步骤**，并为每个步骤附上并行组元数据
  （``parallel_group`` / ``parallel_index`` / ``join_meta``），由链表示层保留，
  引擎多活跃步骤改造（下一迭代，见 mailbus-vision-gap-report §6 P0-1）据此
  真正并发派发与汇合；
- gate 取 ``auto``（全组完成即推进汇合）/ ``review``（汇合前人工评审闸门，
  引擎接入时复用 human-gate）；
- 解析失败抛 :class:`CollabPlanError`（带中文 message），由上层 API 转 400。
"""

from __future__ import annotations

from typing import Any, Dict, List

VALID_JOIN_GATES = ("auto", "review")
SEQUENTIAL_MARKER = "sequential"


class CollabPlanError(ValueError):
    def __init__(self, message: str, code: str = "collab_plan_invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


def _role_item(item: Dict[str, Any], ctx: str) -> Dict[str, Any]:
    rt = item.get("role_type")
    try:
        rt_int = int(rt)
    except (TypeError, ValueError):
        raise CollabPlanError(f"{ctx}：parallel 项缺少合法 role_type") from None
    if rt_int <= 0:
        raise CollabPlanError(f"{ctx}：parallel 项 role_type 非法（{rt!r}）")
    out: Dict[str, Any] = {"role_type": rt_int}
    if item.get("pin_agent"):
        out["pin_agent"] = item["pin_agent"]
    if item.get("reason"):
        out["reason"] = item["reason"]
    return out


def _expand_parallel_join(item: Dict[str, Any], group_id: str) -> List[Dict[str, Any]]:
    """把一项 parallel_join 展开为 [并行步骤..., 汇合步骤]（顺序表但带组标记）。"""
    parallel_raw = item.get("parallel")
    if not isinstance(parallel_raw, list) or len(parallel_raw) < 2:
        raise CollabPlanError("parallel_join 需要至少 2 个 parallel 项")

    join_cfg = item.get("join") or {}
    try:
        join_rt = int(join_cfg.get("role_type") or 0)
    except (TypeError, ValueError):
        join_rt = 0
    if join_rt <= 0:
        raise CollabPlanError("parallel_join 缺少 join.role_type（汇合岗位）")
    gate = str(join_cfg.get("gate") or "auto").lower()
    if gate not in VALID_JOIN_GATES:
        raise CollabPlanError(f"join.gate 仅支持 {'/'.join(VALID_JOIN_GATES)}，收到 {gate!r}")

    steps: List[Dict[str, Any]] = []
    for i, sub in enumerate(parallel_raw):
        role = _role_item(sub, f"parallel[{i}]")
        role["parallel_group"] = group_id
        role["parallel_index"] = i
        role["parallel_total"] = len(parallel_raw)
        role["collab_mode"] = "parallel"
        steps.append(role)
    steps.append({
        "role_type": join_rt,
        "collab_mode": "join",
        "join_parallel_group": group_id,
        "join_gate": gate,
        "join_total": len(parallel_raw),
    })
    return steps


def expand_planned_chain_for_collab(planned_chain: List[dict], body: dict) -> List[dict]:
    """展开带协作标注的规划项；普通项原样透传。

    输入项形态（由 planner 或调用方显式给出）：
    - 普通项：``{"role_type": int, "pin_agent"?: str, "reason"?: str}``
    - 并行项：``{"kind": "parallel_join", "parallel": [..role items..],
               "join": {"role_type": int, "gate": "auto"|"review"}}``
    返回：展开后的线性规划（含并行组/汇合元数据），交给 chain.py 建链。
    """
    if not planned_chain:
        return []
    out: List[Dict[str, Any]] = []
    group_seq = 0
    for idx, item in enumerate(planned_chain):
        kind = item.get("kind") or SEQUENTIAL_MARKER
        if kind == SEQUENTIAL_MARKER:
            out.append(dict(item))
            continue
        if kind == "parallel_join":
            group_seq += 1
            out.extend(_expand_parallel_join(item, f"g{group_seq}"))
            continue
        raise CollabPlanError(f"规划项[{idx}] 未知 kind={kind!r}（仅支持 sequential / parallel_join）")
    return out


def collab_meta(chain: List[dict]) -> Dict[str, Any]:
    """从链规划里提取协作元数据（引擎多活跃步骤改造的输入）。"""
    groups: Dict[str, Dict[str, Any]] = {}
    join_of: Dict[str, str] = {}
    for step in chain:
        if step.get("collab_mode") == "parallel":
            gid = step.get("parallel_group")
            if not gid:
                continue
            entry = groups.setdefault(gid, {"group_id": gid, "parallel": [], "join": None})
            entry["parallel"].append({
                "role_type": step.get("role_type"),
                "index": step.get("parallel_index"),
                "pin_agent": step.get("pin_agent"),
            })
        elif step.get("collab_mode") == "join":
            gid = step.get("join_parallel_group")
            if gid:
                join_of[gid] = step.get("step_id") or ""
                if gid in groups:
                    groups[gid]["join"] = {
                        "role_type": step.get("role_type"),
                        "gate": step.get("join_gate", "auto"),
                        "total": step.get("join_total"),
                    }
    return {"groups": groups, "join_step_of_group": join_of}
