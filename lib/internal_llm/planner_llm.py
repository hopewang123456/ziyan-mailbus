"""Tier-1 LLM Planner — custom/unknown task_type fallback。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ..locale.role_labels import role_type_candidates, valid_role_types
from ..router.planner import PlanError, _apply_constraints, _trim_tier_s_bugfix
from ..utils import json_read
from .budget import check_budget, record_call
from .client import LLMError, complete
from .config_resolve import resolve_llm_config
from .rag.context import fetch_rag_context


def load_llm_config(data_dir: str) -> dict:
    cfg_path = os.path.join(data_dir, "config.json")
    root = json_read(cfg_path, {})
    return resolve_llm_config(root.get("mailbus_internal_llm") or {})


def _validate_output(out: dict, data_dir: str, cfg: dict, citations: list | None = None) -> dict:
    guard = cfg.get("guardrails") or {}
    valid_rt = valid_role_types(data_dir)
    chain = out.get("planned_chain") or []
    if not chain:
        raise PlanError("plan_failed", "empty planned_chain from llm")

    for item in chain:
        rt = int(item["role_type"])
        if rt not in valid_rt:
            if guard.get("reject_unknown_role_types", True):
                raise PlanError("schema_invalid", f"invalid role_type={rt}")
        item.setdefault("reason", (item.get("reason") or "llm planned")[:200])
        if guard.get("reject_unknown_agents", True):
            aid = item.get("agent_id") or item.get("assignee")
            if aid:
                cands = role_type_candidates(rt, data_dir)
                if cands and aid not in cands:
                    raise PlanError(
                        "schema_invalid",
                        f"agent_id={aid} not in role_type={rt} candidates {cands}",
                    )

    if guard.get("require_rag_citations") and not out.get("rag_citations"):
        raise PlanError("schema_invalid", "missing rag_citations")

    allowed_sources = {c.get("source_id") for c in (citations or []) if c.get("source_id")}
    if allowed_sources:
        for cite in out.get("rag_citations") or []:
            sid = cite.get("source_id")
            if sid and sid not in allowed_sources:
                raise PlanError("schema_invalid", f"rag citation source_id not in retrieval: {sid}")

    meta = out.setdefault("plan_meta", {})
    meta["method"] = "internal_llm"
    meta.setdefault("confidence", 0.7)
    if meta.get("provider_used") not in ("local", "remote", "rules"):
        meta["provider_used"] = meta.get("provider_used") or "local"

    return out


def plan_with_llm(envelope: dict, *, data_dir: str = "", config: dict | None = None) -> dict:
    cfg = config or load_llm_config(data_dir)
    if not cfg.get("enabled"):
        raise PlanError("plan_failed", "internal_llm disabled")

    triggers = cfg.get("triggers") or {}
    if not triggers.get("plan_task", True):
        raise PlanError("plan_failed", "triggers.plan_task disabled")

    task_id = envelope.get("task_id") or ""
    err = check_budget(data_dir, task_id, cfg)
    if err:
        raise PlanError("plan_failed", err)

    intent = envelope.get("intent") or ""
    tier = envelope.get("tier") or "M"
    task_type = (envelope.get("task_type") or "custom").lower()
    constraints = envelope.get("constraints") or {}

    citations, rag_block = fetch_rag_context(data_dir, cfg, intent, top_k=8, style="plan")

    system = (
        "You are mailbus Tier-1 task planner. Output ONLY valid JSON matching:\n"
        '{"planned_chain":[{"role_type":int,"reason":str}...],'
        '"plan_meta":{"method":"internal_llm","task_type_guess":str,'
        '"confidence":0-1,"provider_used":"local|remote","model":str},'
        '"rag_citations":[{"source_id":str,"excerpt":str}]}\n'
        "Use role_type integers from RAG context. Max 12 steps."
    )
    user = (
        f"intent: {intent}\n"
        f"tier: {tier}\n"
        f"task_type: {task_type}\n"
        f"constraints: {constraints}\n\n"
        f"RAG:\n{rag_block}"
    )

    try:
        parsed, used = complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            cfg,
        )
        record_call(data_dir, task_id, failed=False)
    except LLMError as exc:
        record_call(data_dir, task_id, failed=True)
        raise PlanError("plan_failed", str(exc)) from exc

    if not parsed.get("rag_citations") and citations:
        parsed["rag_citations"] = [
            {"source_id": c["source_id"], "excerpt": c["excerpt"][:300]}
            for c in citations[:3]
        ]

    out = _validate_output(parsed, data_dir, cfg, citations)

    meta = out["plan_meta"]
    meta["provider_used"] = used
    meta.setdefault("task_type_guess", task_type)
    meta.setdefault("model", meta.get("model") or "internal_llm")

    chain = [int(x["role_type"]) for x in out["planned_chain"]]
    chain = _apply_constraints(chain, constraints)
    chain = _trim_tier_s_bugfix(chain, tier, meta.get("task_type_guess") or task_type)
    valid_rt = valid_role_types(data_dir)
    for rt in chain:
        if rt not in valid_rt:
            raise PlanError("schema_invalid", f"invalid role_type={rt}")

    out["planned_chain"] = [
        {"role_type": rt, "reason": out["planned_chain"][i].get("reason", "llm")[:200]}
        for i, rt in enumerate(chain)
    ]
    meta["skipped_role_types"] = sorted(valid_rt - set(chain))
    return out


def dry_run(envelope: dict, *, data_dir: str, prefer: str = "") -> dict:
    """调试 Planner，使用 config 中配置的 provider（测试可传 prefer=stub）。"""
    cfg = load_llm_config(data_dir)
    if prefer:
        cfg = {**cfg, "provider_priority": [prefer] + [p for p in (cfg.get("provider_priority") or []) if p != prefer]}
    return plan_with_llm(envelope, data_dir=data_dir, config=cfg)
