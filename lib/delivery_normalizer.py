"""Delivery Normalizer — OpenCode 三源（patches + replies + format-patch）→ msg-results。

FSM / pipeline_trigger 只读 msg-results；本模块在 scan housekeeping 与读结果前归一化。
"""

from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import MAILBUS_ROOT
from .pipeline_task import extract_task_id, get_running_pipeline_task
from .task_fsm import get_active_step, step_result_path, write_step_result
from .utils import _now_iso, json_read, json_write

_PATCH_RE = re.compile(r"\.patch$", re.I)


def _delivery_cfg(config: Optional[dict]) -> dict:
    if not config:
        return {}
    fd = config.get("framework_delivery") or {}
    oc = fd.get("opencode") or config.get("opencode_delivery") or {}
    return oc if isinstance(oc, dict) else {}


def load_delivery_config(config: Optional[dict] = None) -> dict:
    """合并 store config 与 mail/config/frameworks/opencode/delivery.json。"""
    cfg = dict(_delivery_cfg(config))
    so_t = MAILBUS_ROOT / "config" / "frameworks" / "opencode" / "delivery.json"
    if so_t.is_file() and not cfg:
        cfg = json_read(str(so_t), {})
    cfg.setdefault("enabled", True)
    cfg.setdefault("sources", ["replies", "patches"])
    cfg.setdefault("require_patch_for_done", False)
    cfg.setdefault("agent_types", ["opencode"])
    return cfg


def _opencode_agents(agents: dict, cfg: dict) -> List[str]:
    types = set(cfg.get("agent_types") or ["opencode"])
    out = []
    for aid, acfg in (agents or {}).items():
        if (acfg or {}).get("type") in types:
            out.append(aid)
    return out


def _resolve_task_context(
    data_dir: str,
    agent: str,
    msg_id: str,
    content_hint: str = "",
) -> Tuple[Optional[str], Optional[dict], Optional[dict]]:
    """返回 (task_id, task, active_step)。"""
    tid = extract_task_id(content_hint or "")
    if not tid and msg_id:
        from .utils import resolve_paths

        inbox_file = os.path.join(resolve_paths(data_dir)["inbox"], agent, "inbox.json")
        inbox = json_read(inbox_file, {})
        for m in inbox.get("messages") or []:
            if m.get("id") == msg_id:
                tid = m.get("task_id") or extract_task_id(m.get("content") or "")
                break
    if not tid:
        return None, None, None
    task = get_running_pipeline_task(data_dir, tid)
    if not task:
        return tid, None, None
    step = get_active_step(task)
    if step:
        sa = step.get("to_agent") or step.get("to_person")
        if sa and sa != agent:
            return tid, task, None
    return tid, task, step


def _result_exists(data_dir: str, task_id: str, step: Optional[dict], msg_id: str) -> bool:
    if step:
        p = step_result_path(data_dir, task_id, step.get("step_id") or "s1")
        if os.path.isfile(p):
            return True
    legacy = os.path.join(data_dir, "msg-results", f"{msg_id}.json")
    return os.path.isfile(legacy)


def _build_result_payload(
    *,
    agent: str,
    msg_id: str,
    task_id: Optional[str],
    step: Optional[dict],
    reply_text: str,
    patch_path: str = "",
    source: str,
) -> dict:
    conclusion = "done"
    low = (reply_text or "").lower()
    if "failed" in low or "失败" in (reply_text or ""):
        conclusion = "fail"
    payload: dict[str, Any] = {
        "agent": agent,
        "msg_id": msg_id,
        "conclusion": conclusion,
        "summary": (reply_text or "")[:500] or f"normalized from {source}",
        "timestamp": _now_iso(),
        "source": source,
        "normalized": True,
    }
    if patch_path:
        payload["patch"] = patch_path
    if task_id:
        payload["task_id"] = task_id
    if step:
        payload["step_id"] = step.get("step_id")
        payload["pipeline_step"] = step.get("step")
        payload["role_type"] = step.get("role_type")
    return payload


def _write_normalized_result(
    data_dir: str,
    payload: dict,
    task_id: Optional[str],
    step: Optional[dict],
    msg_id: str,
) -> str:
    if task_id and step:
        path = write_step_result(
            data_dir, task_id, step, payload, immediate_advance=False,
        )
        return path
    os.makedirs(os.path.join(data_dir, "msg-results"), exist_ok=True)
    out = os.path.join(data_dir, "msg-results", f"{msg_id or task_id}.json")
    json_write(out, payload)
    return out


def normalize_from_reply_record(
    data_dir: str,
    agent: str,
    reply_data: dict,
    *,
    config: Optional[dict] = None,
) -> int:
    """单条 replies/{agent}.json → msg-results。返回写入数。"""
    cfg = load_delivery_config(config)
    if not cfg.get("enabled", True):
        return 0

    msg_ids: List[str] = list(reply_data.get("msg_ids") or [])
    if not msg_ids and reply_data.get("msg_id"):
        msg_ids = [reply_data["msg_id"]]
    if not msg_ids:
        return 0

    reply_text = str(reply_data.get("reply") or reply_data.get("content") or "")
    patch_path = str(reply_data.get("patch") or "")
    written = 0

    for mid in msg_ids:
        tid, task, step = _resolve_task_context(data_dir, agent, mid, reply_text)
        if _result_exists(data_dir, tid or "", step, mid):
            continue
        if cfg.get("require_patch_for_done") and not patch_path:
            if not glob.glob(os.path.join(data_dir, "patches", "*.patch")):
                continue
        payload = _build_result_payload(
            agent=agent,
            msg_id=mid,
            task_id=tid,
            step=step,
            reply_text=reply_text,
            patch_path=patch_path,
            source="delivery-normalizer:replies",
        )
        _write_normalized_result(data_dir, payload, tid, step, mid)
        written += 1
    return written


def normalize_from_patches(
    data_dir: str,
    agents: dict,
    *,
    config: Optional[dict] = None,
    seen_msg_ids: Optional[Set[str]] = None,
) -> int:
    """扫描 store/patches/*.patch，与 replies 中 patch 字段或 msg_id 关联。"""
    cfg = load_delivery_config(config)
    if not cfg.get("enabled", True) or "patches" not in (cfg.get("sources") or []):
        return 0

    patches_dir = os.path.join(data_dir, "patches")
    if not os.path.isdir(patches_dir):
        return 0

    written = 0
    seen = seen_msg_ids or set()
    oc_agents = _opencode_agents(agents, cfg)
    default_agent = oc_agents[0] if oc_agents else "dali"

    for patch_file in sorted(glob.glob(os.path.join(patches_dir, "*.patch"))):
        base = os.path.basename(patch_file)
        stem = base.rsplit(".", 1)[0]
        candidate_ids: List[str] = [stem] if stem.startswith("msg-") else []
        linked_agent = default_agent

        for agent in oc_agents:
            reply_path = os.path.join(data_dir, "replies", f"{agent}.json")
            reply_data = json_read(reply_path, {})
            patch_ref = str(reply_data.get("patch") or "")
            if reply_data and patch_ref and (patch_file in patch_ref or base in patch_ref):
                linked_agent = agent
                for mid in reply_data.get("msg_ids") or []:
                    if mid not in candidate_ids:
                        candidate_ids.append(mid)

        for mid in candidate_ids:
            if mid in seen:
                continue
            tid, task, step = _resolve_task_context(data_dir, linked_agent, mid)
            if _result_exists(data_dir, tid or "", step, mid):
                seen.add(mid)
                continue
            payload = _build_result_payload(
                agent=linked_agent,
                msg_id=mid,
                task_id=tid,
                step=step,
                reply_text=f"patch: {base}",
                patch_path=patch_file,
                source="delivery-normalizer:patches",
            )
            _write_normalized_result(data_dir, payload, tid, step, mid)
            seen.add(mid)
            written += 1
            break
    return written


def normalize_opencode_deliveries(
    data_dir: str,
    agents: dict,
    *,
    config: Optional[dict] = None,
) -> dict:
    """OpenCode 三源归一化入口。返回 {replies, patches, total}。"""
    if config is None:
        config = json_read(os.path.join(data_dir, "config.json"), {})

    cfg = load_delivery_config(config)
    if not cfg.get("enabled", True):
        return {"replies": 0, "patches": 0, "total": 0}

    replies_n = 0
    seen: Set[str] = set()
    replies_dir = os.path.join(data_dir, "replies")
    if os.path.isdir(replies_dir) and "replies" in (cfg.get("sources") or []):
        for agent in _opencode_agents(agents, cfg):
            path = os.path.join(replies_dir, f"{agent}.json")
            data = json_read(path, {})
            if not data:
                continue
            n = normalize_from_reply_record(data_dir, agent, data, config=config)
            replies_n += n
            for mid in data.get("msg_ids") or []:
                seen.add(mid)

    patches_n = normalize_from_patches(
        data_dir, agents, config=config, seen_msg_ids=seen,
    )
    total = replies_n + patches_n
    return {"replies": replies_n, "patches": patches_n, "total": total}
