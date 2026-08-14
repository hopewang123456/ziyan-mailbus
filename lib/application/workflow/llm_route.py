"""llm_adaptive — route_next_step（Tier-1）。"""

from __future__ import annotations

from lib.composition import complete_llm as complete, get_locale, llm_error_type
from lib.application.internal_llm.token_budget import check_budget, record_call
from lib.application.internal_llm.planner import load_llm_config
from lib.application.internal_llm.context import fetch_rag_context
from lib.application.orchestration.router.planner import PlanError

LLMError = llm_error_type()


def route_next_step(task: dict, *, data_dir: str) -> dict:
    """返回 a2a-route-next 形状；失败抛 PlanError。"""
    cfg = load_llm_config(data_dir)
    if not cfg.get("enabled"):
        raise PlanError("plan_failed", "internal_llm disabled")

    task_id = task.get("task_id") or task.get("id") or ""
    err = check_budget(data_dir, task_id, cfg)
    if err:
        raise PlanError("plan_failed", err)

    intent = task.get("intent") or task.get("summary") or ""
    citations, rag_block = fetch_rag_context(data_dir, cfg, intent, top_k=6, style="route")

    system = (
        "You are mailbus workflow router. Output ONLY JSON:\n"
        '{"task_id":str,"suggested_step":{"node_type":"agent","role_type":int,'
        '"agent_id":str,"rationale_short":str},"rationale":str,'
        '"confidence":0-1,"rag_citations":[str],'
        '"plan_meta":{"method":"internal_llm","model":str,"workflow_id":"llm_adaptive"}}'
    )
    user = f"task_id={task_id}\nintent={intent}\nlast_step_done=true\nRAG:\n{rag_block}"

    try:
        parsed, _used = complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            cfg,
        )
        record_call(data_dir, task_id, failed=False)
    except LLMError as exc:
        record_call(data_dir, task_id, failed=True)
        raise PlanError("plan_failed", str(exc)) from exc

    parsed.setdefault("task_id", task_id)
    step = parsed.setdefault("suggested_step", {})
    guard = cfg.get("guardrails") or {}
    if step.get("node_type") == "agent":
        rt = int(step.get("role_type") or 0)
        valid_rt = get_locale(data_dir).valid_role_types()
        if rt not in valid_rt:
            raise PlanError("schema_invalid", f"invalid role_type={rt}")
        aid = step.get("agent_id")
        if aid and guard.get("reject_unknown_agents", True):
            cands = get_locale(data_dir).role_type_candidates(rt)
            if cands and aid not in cands:
                raise PlanError("schema_invalid", f"agent_id={aid} not in role_type={rt} candidates")
        if not step.get("agent_id"):
            cands = get_locale(data_dir).role_type_candidates(rt)
            if cands:
                step["agent_id"] = cands[0]
    meta = parsed.setdefault("plan_meta", {})
    meta["method"] = "internal_llm"
    meta["workflow_id"] = "llm_adaptive"
    if not parsed.get("rag_citations") and citations:
        parsed["rag_citations"] = [c["source_id"] for c in citations[:3]]
    return parsed
