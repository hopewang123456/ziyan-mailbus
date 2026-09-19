"""E1 三段式「测试连接」 — probe → 角色发现预览 → 试发等 ack。

对标「像接 LLM 一样接 Agent」的测试按钮：
  1. probe   框架可达性（本机 PATH / WSL / docker 容器）+ 凭据状态
  2. discover 角色发现预览（discover_roles_for_instance，不落盘）
  3. smoke   试发一条 smoke 消息并等 ack（真验收；投递 + agent 回 ack）

三段全绿 = 接好了；任何一段红 = 明确缺口。CLI 与设置页共用本服务。
"""
from __future__ import annotations

import os
import time
from typing import Any

from lib.infra.utils import json_read


def _instance(data_dir: str, instance_id: str) -> dict[str, Any]:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    inst = (cfg.get("agent_instances") or {}).get(instance_id)
    if not isinstance(inst, dict):
        raise ValueError(f"unknown instance: {instance_id}")
    return inst


def _stage_probe(data_dir: str, inst: dict[str, Any]) -> dict[str, Any]:
    """段1：框架 CLI 可达性（按 run_target 选平台适配器）+ 凭据状态。"""
    from lib.adapters.ops.platform_probe import get_platform_probe

    atype = (inst.get("type") or "").strip()
    if atype in ("", "none"):
        return {"ok": True, "detail": "无框架（本地文件通信）", "platform": "file"}
    run_target = (inst.get("run_target") or "").strip() or None
    probe = get_platform_probe(run_target if run_target in ("win32", "wsl", "linux", "docker") else "")
    # probe 的 config 参数用于 docker 容器解析；实例角色未上架时退化为 CLI 探测
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = {
        rid: dict((cfg.get("agents") or {}).get(rid) or {})
        for rid in (inst.get("role_ids") or [])
    }
    result = probe.probe(atype, (inst.get("role_ids") or [""])[0] or atype)
    out: dict[str, Any] = {
        "ok": bool(result.ok),
        "detail": result.detail or ("not found" if not result.ok else "reachable"),
        "platform": result.platform,
    }

    # 凭据（可选信号，不单独红）：需要浏览器凭据的类型提示是否已存
    try:
        from lib.adapters.config.auth_policy import (
            agent_has_stored_browser_cred,
            agent_requires_browser_auth,
        )

        requires = agent_requires_browser_auth(atype, inst)
        stored = agent_has_stored_browser_cred(data_dir, str(inst.get("id") or ""), inst) if requires else None
        out["cred"] = {
            "required": requires,
            "stored": bool(stored) if requires else None,
        }
    except Exception:
        out["cred"] = {"required": None, "stored": None}
    return out


def _stage_discover(inst: dict[str, Any]) -> dict[str, Any]:
    """段2：角色发现预览 — 不写盘。"""
    from lib.adapters.config.instance_roles import discover_roles_for_instance

    atype = (inst.get("type") or "").strip()
    if atype in ("", "none"):
        return {"ok": True, "count": 0, "roles": [], "detail": "无框架 — 无需角色发现"}
    try:
        roles = discover_roles_for_instance(inst)
    except Exception as exc:
        return {"ok": False, "count": 0, "roles": [], "error": str(exc)[:200]}
    return {
        "ok": True,
        "count": len(roles),
        "roles": [
            {"id": r.get("id"), "display_name": r.get("display_name"), "source": r.get("source")}
            for r in roles
        ],
    }


def _loaded_roles(data_dir: str, instance_id: str) -> list[str]:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    return [
        rid
        for rid, ac in agents.items()
        if isinstance(ac, dict) and ac.get("instance_id") == instance_id and ac.get("enabled", True)
    ]


def _stage_smoke(
    data_dir: str,
    inst: dict[str, Any],
    *,
    target_role: str,
    ack_timeout_sec: int,
) -> dict[str, Any]:
    """段3：试发 smoke 消息并等 ack（真验收）。"""
    from lib.core.a2a.dispatch_integration import send_via_message_port

    iid = str(inst.get("id") or "")
    msg_id = f"smoke-{iid[:24]}-{int(time.time())}"
    prompt = (
        "这是 mailbus 连接测试（smoke）。"
        f"请在收到后按契约将 ack 写入 {os.path.join(data_dir, 'inbox', target_role, 'ack.json').replace(os.sep, '/')}，"
        "内容：{\"action\":\"ack\",\"msg_id\":\"" + msg_id + "\",\"agent\":\"" + target_role + "\"}。无需做其他事。"
    )
    t0 = time.monotonic()
    receipt = send_via_message_port(
        data_dir,
        to_agent=target_role,
        msg_id=msg_id,
        intent=prompt,
        channel="file_bus",
        wait=True,
        allow_no_spawn=False,
        wait_timeout_sec=int(ack_timeout_sec),
        notify=True,
    )
    elapsed = round(time.monotonic() - t0, 1)
    ok = bool(receipt.get("ok"))
    detail = str(receipt.get("detail") or "")
    if ok and "wait_ok" in detail:
        detail = "ack 已收到（真验收通过）"
    elif ok:
        detail = detail or "inbox_written"
    out: dict[str, Any] = {
        "ok": ok,
        "msg_id": msg_id,
        "target": target_role,
        "detail": detail,
        "elapsed_sec": elapsed,
    }
    if not ok:
        out["error"] = receipt.get("error_code") or "no_ack"
        out["hint"] = "消息已投递但未等到 ack：检查 agent CLI 是否能启动、凭据是否有效"
    return out


def run_connection_test(
    data_dir: str,
    instance_id: str,
    *,
    role_id: str = "",
    ack_timeout_sec: int = 90,
    auto_load_roles: bool = True,
) -> dict[str, Any]:
    """三段式测试连接。返回 {stages:{probe,discover,smoke}, ok, roles_loaded}。

    auto_load_roles：实例还没有已上架角色、而发现预览有角色时，自动上架
    （D1：三段全绿 → 角色自动上架）。smoke 优先发给指定 role_id，
    否则用首个已上架角色（没有则用发现预览第一个，上架后发送）。
    """
    inst = _instance(data_dir, instance_id)
    atype = (inst.get("type") or "").strip()

    stages: dict[str, Any] = {}
    stages["probe"] = _stage_probe(data_dir, inst)
    stages["discover"] = _stage_discover(inst)

    loaded = _loaded_roles(data_dir, instance_id)
    roles_loaded: list[str] = []
    target = role_id.strip()
    if auto_load_roles and not loaded and stages["discover"].get("count"):
        from lib.adapters.config.instance_roles import load_roles_for_instance

        try:
            result = load_roles_for_instance(data_dir, instance_id)
            roles_loaded = list(result.get("created") or [])
            loaded = _loaded_roles(data_dir, instance_id)
        except Exception as exc:
            stages["smoke"] = {
                "ok": False,
                "error": "load_roles_failed",
                "detail": str(exc)[:200],
            }
            return _finish(inst, atype, stages, roles_loaded)

    if not target:
        if loaded:
            target = loaded[0]
        else:
            discovered_ids = [r.get("id") for r in (stages["discover"].get("roles") or [])]
            target = discovered_ids[0] if discovered_ids else ""

    if not target:
        stages["smoke"] = {
            "ok": False,
            "error": "no_role",
            "detail": "发现预览与已上架角色均为空 — 先检查 install_path / Members path-map",
        }
    else:
        stages["smoke"] = _stage_smoke(
            data_dir, inst, target_role=target, ack_timeout_sec=ack_timeout_sec,
        )

    return _finish(inst, atype, stages, roles_loaded)


def _finish(
    inst: dict[str, Any],
    atype: str,
    stages: dict[str, Any],
    roles_loaded: list[str],
) -> dict[str, Any]:
    ok = all(bool(s.get("ok")) for s in stages.values())
    return {
        "instance_id": str(inst.get("id") or ""),
        "framework": atype,
        "run_target": inst.get("run_target") or "",
        "stages": stages,
        "roles_loaded": roles_loaded,
        "ok": ok,
    }


def format_connection_text(report: dict[str, Any]) -> str:
    """CLI 打印用 — 三段 ✓/✗ + 缺口清单。"""
    lines = [
        f"测试连接: {report.get('instance_id')} "
        f"({report.get('framework')} @ {report.get('run_target') or '-'})"
    ]
    icons = {"probe": "1 probe   ", "discover": "2 发现预览", "smoke": "3 试发ack "}
    gaps: list[str] = []
    for key, label in icons.items():
        st = (report.get("stages") or {}).get(key) or {}
        mark = "✓" if st.get("ok") else "✗"
        detail = st.get("detail") or st.get("error") or ""
        extra = ""
        if key == "discover" and st.get("count") is not None:
            extra = f" — {st.get('count')} 个角色"
        if key == "smoke" and st.get("target"):
            extra = f" → {st.get('target')} ({st.get('elapsed_sec')}s)"
        if key == "probe":
            cred = st.get("cred") or {}
            if cred.get("required") and not cred.get("stored"):
                extra = " — 凭据未存（网页入口需登录）"
        lines.append(f"  {mark} {label}{extra}" + (f" | {detail}" if detail and not st.get("ok") else ""))
        if not st.get("ok"):
            hint = st.get("hint") or ""
            gaps.append(f"{label}: {detail}" + (f"；{hint}" if hint else ""))
    if report.get("roles_loaded"):
        lines.append(f"  ↳ 已自动上架角色: {', '.join(report['roles_loaded'])}")
    if gaps:
        lines.append("缺口清单:")
        for g in gaps:
            lines.append(f"  - {g}")
    lines.append("结论: " + ("三段全绿 — 接好了" if report.get("ok") else "未接通（见上方缺口）"))
    return "\n".join(lines)
