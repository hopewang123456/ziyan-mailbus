"""Production Harness — 真实 spawn CLI + wait ack/step-result + 契约。"""
from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import os
import subprocess
import time
import uuid

from lib.composition import build_result_store
from lib.core.a2a.step_result_io import read_step_result_file
from lib.infra.utils import json_read, json_write
from . import AgentHarness, HarnessOutcome, HarnessSession
from .contract import HarnessContract, build_contract

_TERMINAL_STEP_STATUSES = frozenset({"done", "pass", "submitted", "ok", "failed", "error", "rejected"})


def _step_result_ready(data_dir: str, task_id: str, step_id: str) -> dict | None:
    result = read_step_result_file(data_dir, task_id, step_id)
    if not result:
        return None
    status = (result.get("status") or result.get("conclusion") or "").lower()
    if status in _TERMINAL_STEP_STATUSES:
        return result
    return None


def _msg_acked(data_dir: str, agent_id: str, msg_id: str) -> bool:
    if not msg_id:
        return False
    unacked = build_result_store(data_dir).list_unacked(agent_id, [msg_id])
    return msg_id not in unacked


def _poll_side_effects(data_dir: str) -> None:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    try:
        from lib.application.transport.delivery_normalizer import normalize_opencode_deliveries

        normalize_opencode_deliveries(data_dir, agents, config=cfg)
    except Exception:
        pass
    try:
        from lib.application.scan import scan_all

        scan_all(data_dir, agents)
    except Exception:
        pass


def _attach_contract_to_msgfile(data_dir: str, msg_id: str, contract: HarnessContract) -> None:
    if not data_dir or not msg_id:
        return
    path = os.path.join(data_dir, "msg-files", f"{msg_id}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    block = (
        "\n\n---\n## mailbus HarnessContract\n\n"
        "```json\n"
        + contract.to_json()
        + "\n```\n\n"
        + contract.summary_text
        + "\n"
    )
    if os.path.isfile(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(block)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {msg_id}\n{block}")
    # machine-readable sidecar
    json_write(
        os.path.join(data_dir, "msg-files", f"{msg_id}.contract.json"),
        contract.to_dict(),
    )


class ProductionHarness(AgentHarness):
    """Spawn via adapter CLI; wait for ack + D1 step-result; retry handled by caller."""

    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        data_dir = str(payload.get("data_dir") or "")
        task_id = str(payload.get("task_id") or "")
        step_id = str(payload.get("step_id") or "")
        msg_id = str(payload.get("msg_id") or "")
        if not msg_id and task_id and step_id:
            msg_id = f"msg-{task_id}-{step_id}"

        cfg = json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
        agents = cfg.get("agents") or {}
        agent_cfg = agents.get(agent_id) or payload.get("agent_cfg") or {}
        agent_types = cfg.get("agent_types") or {}
        framework = str(
            payload.get("framework")
            or agent_cfg.get("type")
            or agent_cfg.get("framework")
            or ""
        )

        contract = payload.get("contract")
        if isinstance(contract, dict):
            contract = HarnessContract(**{k: v for k, v in contract.items() if k in HarnessContract.__dataclass_fields__})
        elif not isinstance(contract, HarnessContract):
            contract = build_contract(
                agent_id=agent_id,
                msg_id=msg_id,
                task_id=task_id,
                step_id=step_id,
                data_dir=data_dir,
                framework=framework,
                archetype=str(agent_cfg.get("archetype") or ""),
                role_bounds_summary=str(payload.get("role_bounds_summary") or agent_cfg.get("role") or ""),
                domain_skill_ids=list(payload.get("domain_skill_ids") or []),
                rules_summary=str(payload.get("rules_summary") or ""),
                dispatcher_role_id=str(
                    (cfg.get("mailbus_dispatch") or {}).get("dispatcher_role_id")
                    or payload.get("dispatcher_role_id")
                    or ""
                ),
                timeout_seconds=int(payload.get("timeout_seconds") or 300),
                max_retries=int(payload.get("max_retries") or 3),
            )

        _attach_contract_to_msgfile(data_dir, msg_id, contract)

        prompt = str(payload.get("prompt") or payload.get("message") or "")
        if contract.summary_text and contract.summary_text not in prompt:
            prompt = (prompt + "\n\n" + contract.summary_text).strip()

        session = HarnessSession(
            session_id=f"prod-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            framework=framework,
            transport_channel=str(payload.get("transport_channel") or "file_bus"),
            data_dir=data_dir,
            task_id=task_id,
            step_id=step_id,
            msg_id=msg_id,
        )

        # Real spawn
        cli_pid = None
        try:
            from lib.composition import try_build_push_direct

            built = try_build_push_direct(
                agent_id,
                agent_cfg,
                agent_types,
                data_dir=data_dir,
                prompt=prompt,
                model_name=payload.get("model_name"),
                pipeline=bool(payload.get("pipeline")),
            )
            if built and built.get("argv"):
                proc = subprocess.Popen(
                    built["argv"],
                    cwd=built.get("cwd") or None,
                    env=built.get("env") or None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                cli_pid = proc.pid
                try:
                    from lib.application.push.pusher import _ACTIVE_CLI_PROCS

                    _ACTIVE_CLI_PROCS[agent_id] = proc
                except Exception:
                    pass
            elif payload.get("allow_no_spawn"):
                pass
            else:
                session.framework = framework or "pending_push"
        except Exception as exc:
            session.framework = f"spawn_error:{exc}"

        # stash pid on session via msg sidecar
        if data_dir and msg_id and cli_pid:
            json_write(
                os.path.join(data_dir, "msg-files", f"{msg_id}.spawn.json"),
                {"cli_pid": cli_pid, "session_id": session.session_id, "agent_id": agent_id},
            )
        return session

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        data_dir = session.data_dir
        task_id = session.task_id
        step_id = session.step_id
        if not data_dir:
            return HarnessOutcome(ok=False, error="production wait requires data_dir")

        # Notice-only: ack is enough when no step
        if not task_id or not step_id:
            deadline = now_ts() + timeout
            while now_ts() < deadline:
                if session.msg_id and _msg_acked(data_dir, session.agent_id, session.msg_id):
                    return HarnessOutcome(ok=True, ack_received=True)
                time.sleep(1)
            return HarnessOutcome(ok=False, error="timeout waiting for ack")

        deadline = now_ts() + timeout
        ack_received = False
        round_n = 0
        while now_ts() < deadline:
            round_n += 1
            if session.msg_id and not ack_received:
                ack_received = _msg_acked(data_dir, session.agent_id, session.msg_id)

            result = _step_result_ready(data_dir, task_id, step_id)
            if result:
                status = (result.get("status") or "").lower()
                ok = status not in ("failed", "error", "rejected")
                return HarnessOutcome(
                    ok=ok,
                    ack_received=ack_received or not session.msg_id,
                    step_result=result,
                    error=None if ok else str(result.get("summary") or status),
                )

            if round_n % 2 == 0:
                _poll_side_effects(data_dir)
            time.sleep(1)

        return HarnessOutcome(
            ok=False,
            ack_received=ack_received,
            error="timeout waiting for step-result",
        )
