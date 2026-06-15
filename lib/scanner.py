"""
ziyan-mailbus scanner

扫描所有 agent 的 inbox，检测未读消息，构建推送队列（加急/普通）。
"""

import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

from .models import Message, MsgStatus, Priority, Inbox
from .utils import json_read, json_write, resolve_paths, _now_iso
from .constants import DEFAULT_ACK_TIMEOUT
from .self_heal import agent_cli_active


def get_msg_state(msg):
    """统一读取消息状态：先读 state，回退读 status"""
    state = msg.get('state', '') if isinstance(msg, dict) else getattr(msg, 'state', '')
    if not state:
        state = msg.get('status', '') if isinstance(msg, dict) else getattr(msg, 'status', '')
    return state


def _get_running_pipeline_task_ids(data_dir: str, agent_name: str) -> set:
    """当前 agent 负责的 running pipeline 任务 ID"""
    try:
        from .tracker import TaskTracker
        ids = set()
        for t in TaskTracker(data_dir).list_all():
            if t.get("status") != "running":
                continue
            chain = t.get("chain") or []
            if not chain:
                continue
            cur = chain[-1]
            if cur.get("to_person") == agent_name and cur.get("status") == "running":
                tid = t.get("task_id") or t.get("id")
                if tid:
                    ids.add(tid)
        return ids
    except Exception:
        return set()


def _msg_matches_pipeline_task(content: str, pipeline_ids: set) -> bool:
    if not content or not pipeline_ids:
        return False
    for tid in pipeline_ids:
        if tid in content and ("【" in content or tid.startswith("mailbus-") or tid.startswith("msg-")):
            return True
    return False


def _message_queue_priority(msg, pipeline_ids: set, data_dir: str = ""):
    """队列排序：running pipeline 任务 > 可执行 task > 其他"""
    content = msg.content if hasattr(msg, "content") else ""
    mtype = msg.type if hasattr(msg, "type") else "notice"
    action = msg.action if hasattr(msg, "action") else {}
    execute = action.get("execute", mtype == "task") if action else (mtype == "task")
    is_pipeline = _msg_matches_pipeline_task(content or "", pipeline_ids)
    is_task = mtype == "task"
    round2_defer = False
    if is_task and data_dir and any(k in (content or "") for k in ("Round2", "round-2-backlog", "iteration-r2")):
        gate = json_read(os.path.join(data_dir, "iterations", "round-1-gate.json"), {})
        if not gate.get("round2_unlocked"):
            round2_defer = True
    if is_pipeline:
        tier = 0
    elif round2_defer:
        tier = 8
    elif is_task and execute:
        tier = 1
    elif is_task:
        tier = 2
    elif "inbox_overflow" in (content or "") or "催办提醒" in (content or ""):
        tier = 9
    else:
        tier = 3
    created = msg.created_at if hasattr(msg, "created_at") else ""
    return (tier, created or "")


def recover_inbox_stale_states(data_dir: str, agents: dict) -> dict:
    """
    回收僵尸 pushed/processing 状态，避免 notice 占满推送槽、task 卡在 processing 无法重推。
    在 build_queues 之前调用。
    """
    from datetime import timezone
    from .tracker import TaskTracker, _parse_iso_dt

    paths = resolve_paths(data_dir)
    now = __import__("datetime").datetime.now(timezone.utc)
    stats = {}

    pipeline_by_agent = {}
    for t in TaskTracker(data_dir).list_all():
        if t.get("status") != "running":
            continue
        chain = t.get("chain") or []
        if not chain:
            continue
        cur = chain[-1]
        if cur.get("status") == "running":
            person = cur.get("to_person", "")
            tid = t.get("task_id", "")
            if person and tid:
                pipeline_by_agent.setdefault(person, set()).add(tid)

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        pipeline_ids = pipeline_by_agent.get(name, set())
        recovered = 0

        for m_raw in inbox.messages:
            mid = inbox.msg_field(m_raw, "id", "")
            state = get_msg_state(m_raw)
            mtype = inbox.msg_field(m_raw, "type", "")
            content = inbox.msg_field(m_raw, "content", "")
            action = inbox.msg_field(m_raw, "action", {}) or {}
            execute = action.get("execute", mtype == "task")
            status_field = m_raw.get("status") if isinstance(m_raw, dict) else getattr(m_raw, "status", "")

            received_at = inbox.msg_field(m_raw, "received_at", "") or inbox.msg_field(m_raw, "acknowledged_at", "")
            created_at = inbox.msg_field(m_raw, "created_at", "")
            ref_time = received_at or created_at
            age_min = 0.0
            if ref_time:
                dt = _parse_iso_dt(ref_time)
                age_min = (now - dt.astimezone(timezone.utc)).total_seconds() / 60.0

            is_pipeline_task = _msg_matches_pipeline_task(content, pipeline_ids)

            # done_at 已写但 state 仍为 processing（auto_ack 覆盖）
            if state == MsgStatus.PROCESSING and inbox.msg_field(m_raw, "done_at", ""):
                inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE)
                recovered += 1
                continue

            # 团队规范 notice：不占用 pipeline 推送槽
            if pipeline_ids and state == MsgStatus.PENDING and mtype == "notice":
                if any(x in content for x in ("团队规范已更新", "team-secrets-policy", "execution-order.md")):
                    ts = _now_iso()
                    inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
                    recovered += 1
                    continue

            # agent 有 running pipeline 时，丢弃 inbox_overflow / 催办 notice（避免抢占推送槽）
            if pipeline_ids and state == MsgStatus.PENDING and mtype == "notice":
                if "inbox_overflow" in content or "催办提醒" in content or mid.startswith("tracker-remind"):
                    ts = _now_iso()
                    inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
                    recovered += 1
                    continue

            # status/state 不同步或 pushed 超时
            if status_field == MsgStatus.PUSHED and state == MsgStatus.PENDING:
                if age_min > 30:
                    inbox.set_msg_status(mid, MsgStatus.PENDING, state=MsgStatus.PENDING, pushed_count=0)
                else:
                    inbox.set_msg_status(mid, MsgStatus.PUSHED, state=MsgStatus.PUSHED)
                recovered += 1
                continue

            if state == MsgStatus.PUSHED and age_min > 30:
                inbox.set_msg_status(mid, MsgStatus.PENDING, state=MsgStatus.PENDING, pushed_count=0)
                recovered += 1
                continue

            if state == MsgStatus.PUSHED and not agent_cli_active(name, agents) and age_min > 2:
                inbox.set_msg_status(mid, MsgStatus.PENDING, state=MsgStatus.PENDING, pushed_count=0)
                recovered += 1
                continue

            # notice / 催办 / 团队规范：auto_ack 后无需 agent 执行，快速标记 done
            if state == MsgStatus.PROCESSING:
                if mtype == "notice" and (
                    not execute
                    or any(x in content for x in ("团队规范已更新", "team-secrets-policy"))
                ):
                    if age_min > 3:
                        ts = _now_iso()
                        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
                        recovered += 1
                    continue
                if mid.startswith("tracker-remind") or "催办提醒" in content:
                    if age_min > 3:
                        ts = _now_iso()
                        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
                        recovered += 1
                    continue

                # 可执行 task 卡在 processing
                if execute and mtype == "task":
                    primary_tid = _get_primary_pipeline_task_id(data_dir)
                    is_primary = bool(primary_tid and primary_tid in content)
                    result_missing = is_primary and not os.path.exists(
                        os.path.join(data_dir, "msg-results", f"{primary_tid}.json")
                    )
                    # 无 CLI 进程 = 僵尸 ACK，2 分钟后释放推送槽
                    cli_dead = not agent_cli_active(name, agents)
                    if cli_dead and age_min > 2:
                        inbox.set_msg_status(
                            mid, MsgStatus.PENDING, state=MsgStatus.PENDING,
                            acknowledged_at=None, received_at=None, pushed_count=0,
                        )
                        recovered += 1
                        continue
                    threshold = 5 if (is_pipeline_task and result_missing) else (15 if is_pipeline_task else 45)
                    if age_min > threshold:
                        inbox.set_msg_status(
                            mid, MsgStatus.PENDING, state=MsgStatus.PENDING,
                            acknowledged_at=None, received_at=None, pushed_count=0,
                        )
                        recovered += 1

        if recovered:
            json_write(inbox_file, inbox.to_dict())
            stats[name] = recovered

    return stats


def _get_primary_pipeline_task_id(data_dir: str) -> str:
    """Round1 主任务 ID（iteration-state.json），用于多 pipeline 并行时插队"""
    state_path = os.path.join(data_dir, "iterations", "iteration-state.json")
    state = json_read(state_path, {})
    return state.get("primary_task_id", "") or ""


def _pick_pipeline_head(msgs: list, primary_tid: str):
    """多个 running pipeline 消息时，主任务优先"""
    def key(m):
        content = m.content if hasattr(m, "content") else ""
        is_primary = bool(primary_tid and primary_tid in (content or ""))
        return (0 if is_primary else 1, m.created_at if hasattr(m, "created_at") else "")
    return sorted(msgs, key=key)[0]


def _scan_one_agent(data_dir: str, name: str, inbox_base: str) -> Optional[Tuple[str, list, list]]:
    """
    扫描单个 agent 的 inbox。
    
    返回: (agent_name, urgent_messages, normal_messages) 或 None（无待处理消息）
    """
    inbox_path = f"{inbox_base}/{name}/inbox.json"
    if not os.path.exists(inbox_path):
        return None
    
    inbox_data = json_read(inbox_path, {})
    if not inbox_data:
        return None
    
    inbox = Inbox.from_dict(inbox_data)
    
    # 检测该 agent 是否有回复消息（来自 agent 自己的回复）
    replied_ids = set()
    for m_raw in inbox.messages:
        msg_type = inbox.msg_field(m_raw, 'type', '')
        msg_from = inbox.msg_field(m_raw, 'from', '')
        msg_id = inbox.msg_field(m_raw, 'id', '')
        original_msg_id = inbox.msg_field(m_raw, 'original_msg_id', '') or msg_id
        
        if msg_type in ("reply", "forward") and msg_from == name:
            replied_ids.add(original_msg_id)
            if msg_id != original_msg_id:
                replied_ids.add(msg_id)
    
    if replied_ids:
        from datetime import datetime
        ts = datetime.now().isoformat()
        for m_raw in inbox.messages:
            mid = inbox.msg_field(m_raw, 'id', '')
            if mid in replied_ids:
                mstate = get_msg_state(m_raw)
                if mstate in (MsgStatus.PENDING, MsgStatus.PUSHED, MsgStatus.PROCESSING):
                    inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, acknowledged_at=ts)
                    mtype = inbox.msg_field(m_raw, 'type', '')
                    cur_state = inbox.msg_field(m_raw, 'state', '')
                    if not cur_state or cur_state == MsgStatus.PROCESSING:
                        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED,
                                             state=MsgStatus.DONE, done_at=ts)
        json_write(inbox_path, inbox.to_dict())
    
    urgent_msgs = []
    normal_msgs = []
    has_pending = False
    
    for m_raw in inbox.messages:
        msg = Message.from_dict(m_raw) if isinstance(m_raw, dict) else m_raw
        mstate = get_msg_state(m_raw)
        if mstate == MsgStatus.PENDING:
            has_pending = True
            if msg.priority == Priority.URGENT:
                urgent_msgs.append(msg)
            else:
                normal_msgs.append(msg)

    # running pipeline 任务 > 可执行 task > notice，避免催办 notice 占满推送槽
    pipeline_ids = _get_running_pipeline_task_ids(data_dir, name)
    if normal_msgs:
        normal_msgs = sorted(normal_msgs, key=lambda m: _message_queue_priority(m, pipeline_ids, data_dir))
    if urgent_msgs:
        urgent_msgs = sorted(urgent_msgs, key=lambda m: _message_queue_priority(m, pipeline_ids, data_dir))

    if has_pending:
        return (name, urgent_msgs, normal_msgs)
    return None


def scan_all(data_dir: str, agents: dict, max_workers: int = 4) -> List[Tuple[str, list, list]]:
    """
    并行扫描所有 agent 的 inbox。
    
    参数:
        data_dir: 数据目录
        agents: agent 配置字典
        max_workers: 最大并行线程数（默认 4）
    
    返回: [(agent_name, urgent_messages, normal_messages), ...]
    按加急在前、普通在后排序。
    """
    paths = resolve_paths(data_dir)
    inbox_base = paths['inbox']
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_one_agent, data_dir, name, inbox_base): name
            for name in agents
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception:
                pass  # 单个 agent 扫描失败不影响其他
    
    # 排序：有加急的 agent 排前面
    results.sort(key=lambda x: -len(x[1]))
    return results


def run_housekeeping(data_dir: str, agents: dict):
    """
    执行邮件系统的运维任务（非扫描核心职责）。
    由 bus.py 的 scan 命令在 build_queues 之后主动调用。

    包括：
    - 超时催办检测
    - skill 使用记录消费
    - agent 离线检测
    - 自动归档
    - 索引更新
    """
    paths = resolve_paths(data_dir)

    # 自愈：回复回收、tracker/inbox 对齐、历史审计归档
    try:
        from .self_heal import run_self_heal
        from .audit_dispatch import consume_audit_results
        healed = run_self_heal(data_dir, agents, phase="full")
        if healed:
            parts = ", ".join(f"{k}={v}" for k, v in healed.items())
            print(f"  🔧 自愈: {parts}")
        n = consume_audit_results(data_dir)
        if n:
            print(f"  🔍 审计入库: {n} 条")
    except Exception as exc:
        print(f"  [scanner] self_heal 异常: {exc}")

    # 超时检测：检查所有 agent 的 inbox，超时未处理的消息自动催办
    _check_timeouts(data_dir, agents, paths['inbox'], paths)

    # Tracker 催办检测：检查 tracker 中 running 任务是否需要催办
    try:
        from .tracker import TaskTracker
        from .constants import DEFAULT_REMINDER_MINUTES, DEFAULT_MAX_REMINDERS
        config_path = os.path.join(data_dir, "config.json")
        config_data = json_read(config_path, {})
        reminder_minutes = config_data.get("reminder_minutes", DEFAULT_REMINDER_MINUTES)
        max_reminders = config_data.get("max_reminders", DEFAULT_MAX_REMINDERS)
        tracker = TaskTracker(data_dir)
        reopened = tracker.reopen_stale_timeouts(agents, data_dir)
        if reopened:
            print(f"  ♻️ 恢复误标 timeout 的 pipeline 任务: {reopened} 条")
        escalated = tracker.check_reminders(
            agents, data_dir=data_dir,
            reminder_minutes=reminder_minutes,
            max_reminders=max_reminders,
        )
        if escalated:
            for e in escalated:
                print(f"  ⏰ 催办: {e['agent']} — {e['summary'][:40]}")
                # 写催办通知到目标 inbox
                escalate_file = f"{paths['inbox']}/{e['agent']}/inbox.json"
                if os.path.exists(os.path.dirname(escalate_file)):
                    e_data = json_read(escalate_file, {})
                    e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=e['agent'])
                    import time as _time
                    remind_msg = {
                        "id": f"tracker-remind-{int(_time.time())}",
                        "from": "mailbus",
                        "to": e['agent'],
                        "type": "notice",
                        "priority": "urgent",
                        "state": "pending",
                        "content": f"⏰ 催办提醒：任务「{e['summary']}」已超过催办时间，请尽快处理（第{e['reminded_count']}次催办）",
                        "created_at": _now_iso(),
                    }
                    e_inbox.messages.append(remind_msg)
                    e_inbox.has_unread = True
                    json_write(escalate_file, e_inbox.to_dict())
    except Exception as exc:
        print(f"  [scanner] tracker 催办异常: {exc}")

    # 技能使用记录消费：扫描 skill-usage-pending 目录，归入 skill-usage.json
    _consume_skill_usage(data_dir)

    # agent 离线检测：检查所有 agent 心跳，离线超过 3 次 ping 的发送通知
    _check_offline_agents(data_dir, agents, paths)

    # 自动归档：从 config 读取天数（默认3天）和 inbox 最大消息数
    try:
        from .archiver import archive_all
        config_path = os.path.join(data_dir, "config.json")
        config_data = json_read(config_path, {})
        archive_days = config_data.get("archive_days", 7)
        max_messages = config_data.get("archive_max_messages", 300)
        archived = archive_all(data_dir, agents, archive_days=archive_days, max_messages=max_messages)
        if archived:
            for name, count in archived.items():
                print(f"  📦 {name}: {count} 条已归档")
    except Exception:
        pass

    # 自动索引：扫描所有 inbox 更新搜索索引
    try:
        from .search import scan_and_index
        scan_and_index(data_dir, agents)
    except Exception:
        pass

    # 规则文件变更检测：检查 store/rules/ 下文件是否被修改，变更时广播通知
    try:
        _check_rule_changes(data_dir, agents, paths)
    except Exception:
        pass

    # 审计：派发待审计任务给灵鉴（自愈已 auto_close 历史噪音）
    try:
        from .audit_dispatch import dispatch_pending_audits
        dispatch_pending_audits(data_dir, agents, paths)
    except Exception as exc:
        print(f"  [scanner] audit dispatch 异常: {exc}")

    # Pipeline 自动流转：检测 msg-results 并推进任务链
    try:
        from .pipeline_trigger import trigger as pipeline_trigger
        pipeline_trigger(data_dir, agents, paths)
    except Exception as exc:
        print(f"  [scanner] pipeline trigger 异常: {exc}")

    # 迭代 Round1 诊断（每轮 scan 刷新；不自动生成 Round2）
    try:
        from .iteration_engine import run_round1, evaluate_round1_gate
        summary = run_round1(data_dir, agents).get("summary", {})
        gate = evaluate_round1_gate(data_dir, agents)
        if not gate.get("round2_unlocked"):
            print(f"  🔁 Round1 进行中: 主任务={gate.get('primary_status')} "
                  f"待审计={gate.get('pending_audit_total')} "
                  f"blockers={len(gate.get('blockers', []))}")
        else:
            print(f"  ✅ Round1 已通过，可 bus iteration --round 2")
    except Exception as exc:
        print(f"  [scanner] iteration round1 异常: {exc}")


def _consume_skill_usage(data_dir: str):
    """扫描 skill-usage-pending/ 目录，消费待处理的 skill 使用记录"""
    pending_dir = os.path.join(data_dir, "skill-usage-pending")
    target_file = os.path.join(data_dir, "skill-usage.json")
    if not os.path.isdir(pending_dir):
        return
    
    consumed = 0
    target_data = json_read(target_file, {})
    
    for fname in os.listdir(pending_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath) as f:
                record = json.load(f)
            skill = record.get("skill", "")
            agent = record.get("agent", "")
            ts = record.get("timestamp", "")
            if not skill or not agent:
                continue
            
            if skill not in target_data:
                target_data[skill] = {}
            if agent not in target_data[skill]:
                target_data[skill][agent] = {"use_count": 0, "view_count": 0, "last_used": ""}
            target_data[skill][agent]["use_count"] = target_data[skill][agent].get("use_count", 0) + 1
            if ts:
                target_data[skill][agent]["last_used"] = ts
            
            os.remove(fpath)
            consumed += 1
        except Exception:
            pass
    
    if consumed > 0:
        json_write(target_file, target_data)


def _check_timeouts(data_dir: str, agents: dict, inbox_base: str, paths: dict):
    """扫描所有 inbox，检测超时未处理的消息并催办"""
    from datetime import datetime, timezone, timedelta

    EXEC_TIMEOUT_MINUTES = 30  # 任务执行超时：ACK 后 30 分钟未 done 则催办
    
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        if not os.path.exists(inbox_file):
            continue
        
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        
        inbox = Inbox.from_dict(inbox_data)
        now = datetime.now(timezone.utc)
        reminded = []
        
        for m_raw in inbox.messages:
            if isinstance(m_raw, dict):
                # 兼容旧消息：缺失 to/from_ 字段时用默认值
                if "to" not in m_raw:
                    m_raw["to"] = name
                if "from_" not in m_raw and "from" not in m_raw:
                    m_raw["from_"] = name
                msg = Message.from_dict(m_raw)
            else:
                msg = m_raw
            
            mstate = get_msg_state(m_raw)
            
            # ── 1. ACK 超时检测：pending/pushed 消息超过 timeout 分钟未 ack ──
            timeout_min = msg.timeout_minutes or DEFAULT_ACK_TIMEOUT
            if timeout_min > 0 and mstate not in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.REJECTED):
                if msg.state not in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.REJECTED):
                    created = None
                    if msg.received_at:
                        try:
                            created = datetime.fromisoformat(msg.received_at)
                        except (ValueError, TypeError):
                            pass
                    if not created and msg.created_at:
                        try:
                            created = datetime.fromisoformat(msg.created_at)
                        except (ValueError, TypeError):
                            pass
                    
                    if created:
                        elapsed_min = (now - created).total_seconds() / 60
                        if elapsed_min >= timeout_min:
                            # 发 ACK 超时催办
                            escalate = msg.escalate_to or msg.from_
                            if escalate and escalate not in ("mailbus", "broadcast", ""):
                                escalate_file = f"{paths['inbox']}/{escalate}/inbox.json"
                                if os.path.exists(os.path.dirname(escalate_file)):
                                    try:
                                        e_data = json_read(escalate_file, {})
                                        e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=escalate)
                                        import time as _time
                                        now_ts = int(_time.time())
                                        remind_count = (inbox.msg_field(m_raw, 'reminded_count', 0) or 0) + 1
                                        remind_msg = {
                                            "id": f"remind-{now_ts}-{name}",
                                            "from": "mailbus",
                                            "to": escalate,
                                            "type": "notice",
                                            "priority": "urgent",
                                            "state": MsgStatus.PENDING,
                                            "content": f"⚠️ 超时提醒（第{remind_count}次）：{name} 有一条消息已超过 {int(timeout_min)} 分钟未处理。\n消息ID: {msg.id}\n来自: {msg.from_}\n内容: {inbox.msg_field(m_raw, 'content', '')[:80]}\n{'❤️ 已3次催办无响应，消息将自动标记为 failed' if remind_count >= 3 else '请关注处理。'}",
                                            "created_at": datetime.now(timezone.utc).isoformat(),
                                        }
                                        e_inbox.messages.append(remind_msg)
                                        e_inbox.has_unread = True
                                        json_write(escalate_file, e_inbox.to_dict())
                                        
                                        # 更新原消息的催办记录
                                        inbox.set_msg_status(msg.id, inbox.msg_field(m_raw, 'state', ''),
                                                             reminded_count=remind_count,
                                                             last_reminded_at=datetime.now(timezone.utc).isoformat())
                                        
                                        # 3 次催办后自动标记为 failed
                                        if remind_count >= 3:
                                            inbox.set_msg_status(msg.id, MsgStatus.FAILED,
                                                                 state=MsgStatus.CLOSED,
                                                                 done_at=datetime.now(timezone.utc).isoformat(),
                                                                 done_note="3次催办无响应，自动关闭")
                                        
                                        # 原消息重推（如果是 pending/pushed 状态）
                                        if mstate in (MsgStatus.PENDING, MsgStatus.PUSHED, MsgStatus.ACKNOWLEDGED):
                                            inbox.set_msg_status(msg.id, MsgStatus.RESENDING)
                                        
                                        reminded.append(name)
                                    except Exception:
                                        pass
            
            # ── 2. 执行超时检测：ACK（received/acknowledged）后 30 分钟未 done ──
            msg_content = inbox.msg_field(m_raw, 'content', '')
            msg_type = inbox.msg_field(m_raw, 'type', '')
            if mstate in (MsgStatus.ACKNOWLEDGED, MsgStatus.RECEIVED) and msg_type in ("task", "task_reply"):
                if mstate != MsgStatus.DONE and msg.state not in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.REJECTED):
                    ack_time = None
                    if msg.received_at:
                        try:
                            ack_time = datetime.fromisoformat(msg.received_at)
                        except (ValueError, TypeError):
                            pass
                    if not ack_time and msg.acknowledged_at:
                        try:
                            ack_time = datetime.fromisoformat(msg.acknowledged_at)
                        except (ValueError, TypeError):
                            pass
                    
                    if ack_time:
                        elapsed_min = (now - ack_time).total_seconds() / 60
                        if elapsed_min >= EXEC_TIMEOUT_MINUTES:
                            # 检查是否已催办过执行超时（至少隔 15 分钟再催）
                            exec_remind_count = inbox.msg_field(m_raw, 'exec_reminded_count', 0) or 0
                            last_exec_reminded = inbox.msg_field(m_raw, 'last_exec_reminded_at', '')
                            skip = False
                            if exec_remind_count > 0 and last_exec_reminded:
                                try:
                                    last_er = datetime.fromisoformat(last_exec_reminded)
                                    if (now - last_er).total_seconds() / 60 < 15:
                                        skip = True
                                except (ValueError, TypeError):
                                    pass
                            
                            if not skip:
                                exec_remind_count += 1
                                escalate = msg.escalate_to or msg.from_
                                if escalate and escalate not in ("mailbus", "broadcast", ""):
                                    escalate_file = f"{paths['inbox']}/{escalate}/inbox.json"
                                    if os.path.exists(os.path.dirname(escalate_file)):
                                        try:
                                            e_data = json_read(escalate_file, {})
                                            e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=escalate)
                                            import time as _time
                                            now_ts = int(_time.time())
                                            remind_msg = {
                                                "id": f"exec-remind-{now_ts}-{name}",
                                                "from": "mailbus",
                                                "to": escalate,
                                                "type": "notice",
                                                "priority": "urgent",
                                                "state": MsgStatus.PENDING,
                                                "content": f"⚠️ 执行超时提醒（第{exec_remind_count}次）：{name} 已 ACK 任务超过 {EXEC_TIMEOUT_MINUTES} 分钟，尚未完成。\n"
                                                           f"消息ID: {msg.id}\n来自: {msg.from_}\n类型: {msg_type}\n"
                                                           f"内容: {msg_content[:80]}",
                                                "created_at": datetime.now(timezone.utc).isoformat(),
                                            }
                                            e_inbox.messages.append(remind_msg)
                                            e_inbox.has_unread = True
                                            json_write(escalate_file, e_inbox.to_dict())
                                            
                                            # 更新原消息的执行超时催办记录
                                            inbox.set_msg_field(m_raw, 'exec_reminded_count', exec_remind_count)
                                            inbox.set_msg_field(m_raw, 'last_exec_reminded_at', datetime.now(timezone.utc).isoformat())
                                            
                                            reminded.append(name)
                                        except Exception:
                                            pass
        
        if reminded:
            json_write(inbox_file, inbox.to_dict())


def push_to_queue(data_dir: str, agent_name: str, messages: list, is_urgent: bool):
    """
    将待推送消息写入队列文件。
    队列文件格式: queue/urgent/<agent_name>.json 或 queue/normal/<agent_name>.json
    """
    paths = resolve_paths(data_dir)
    queue_dir = paths["queue_urgent"] if is_urgent else paths["queue_normal"]
    queue_file = f"{queue_dir}/{agent_name}.json"
    
    msg_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m for m in messages]
    json_write(queue_file, msg_dicts)


def _has_pushed_message(inbox) -> bool:
    """检查 inbox 中是否已有 pushed 状态的消息（串行约束）"""
    for m in inbox.messages:
        state = get_msg_state(m)
        if state == MsgStatus.PUSHED:
            return True
    return False


def _agent_has_active_work(inbox, data_dir: str, agent_name: str) -> bool:
    """
    agent 是否已有进行中的可执行任务（pushed/processing 且尚无 msg-results）。
    防止 scan 连续 spawn 多个 Hermes chat 进程。
    """
    pipeline_ids = _get_running_pipeline_task_ids(data_dir, agent_name)
    for m_raw in inbox.messages:
        state = get_msg_state(m_raw)
        if state == MsgStatus.PUSHED:
            return True
        if state != MsgStatus.PROCESSING:
            continue
        if inbox.msg_field(m_raw, "done_at", "") or inbox.msg_field(m_raw, "done_note", ""):
            continue
        mtype = m_raw.get("type") if isinstance(m_raw, dict) else getattr(m_raw, "type", "")
        action = m_raw.get("action") if isinstance(m_raw, dict) else getattr(m_raw, "action", {})
        execute = (action or {}).get("execute", mtype == "task")
        if mtype != "task" or not execute:
            continue
        content = m_raw.get("content") if isinstance(m_raw, dict) else getattr(m_raw, "content", "")
        for tid in pipeline_ids:
            if tid in (content or ""):
                result_path = os.path.join(data_dir, "msg-results", f"{tid}.json")
                if not os.path.exists(result_path):
                    return True
        return True
    return False


def build_queues(data_dir: str, agents: dict) -> Tuple[dict, dict]:
    """
    完整流程：scan 全员的 inbox → 构建加急队列和普通队列。
    
    串行约束（P2）：一个 agent 最多同时只有 1 条 pushed 消息，
    有 pushed 消息时不再推送新的 pending 消息。
    
    返回: (urgent_queue, normal_queue)
    每项: {agent_name: [Message, ...]}
    """
    recovered = recover_inbox_stale_states(data_dir, agents)
    if recovered:
        for agent, count in recovered.items():
            print(f"  ♻️ {agent}: 回收 {count} 条僵尸消息")

    urgent_queue = {}
    normal_queue = {}
    paths = resolve_paths(data_dir)
    
    scanned = scan_all(data_dir, agents)
    
    for name, urgent_msgs, normal_msgs in scanned:
        # ── P0: running pipeline 任务强制插队，不被 urgent notice 淹没 ──
        pipeline_ids = _get_running_pipeline_task_ids(data_dir, name)
        pipeline_msgs = [
            m for m in urgent_msgs + normal_msgs
            if m.type == "task" and _msg_matches_pipeline_task(m.content or "", pipeline_ids)
        ]
        if pipeline_msgs:
            primary_tid = _get_primary_pipeline_task_id(data_dir)
            head = [_pick_pipeline_head(pipeline_msgs, primary_tid)]
            urgent_queue[name] = head
            push_to_queue(data_dir, name, head, is_urgent=True)
            continue

        # ── P2 串行约束：检查该 agent 是否已有 pushed 消息 ──
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if inbox_data:
            inbox = Inbox.from_dict(inbox_data) if "agent" in inbox_data else None
            if inbox and _agent_has_active_work(inbox, data_dir, name):
                continue  # 已有 Hermes 在处理 pipeline/task，不并发推新消息
            if inbox and _has_pushed_message(inbox):
                continue  # 有正在推送中的消息，暂不推新的
        
        # 每次最多推 1 条（加急优先）
        if urgent_msgs:
            head = [urgent_msgs[0]]
            urgent_queue[name] = head
            push_to_queue(data_dir, name, head, is_urgent=True)
        elif normal_msgs:
            head = [normal_msgs[0]]
            normal_queue[name] = head
            push_to_queue(data_dir, name, head, is_urgent=False)
    
    return urgent_queue, normal_queue


def _get_acked_ids(inbox_data: dict) -> set:
    """
    从 inbox 数据中提取已 ack 的消息 ID 集合。
    用于幂等去重。
    """
    inbox = Inbox.from_dict(inbox_data) if "agent" in inbox_data else None
    if not inbox:
        acked = set()
        for m in inbox_data.get("messages", []):
            mid = m.get("id") if isinstance(m, dict) else getattr(m, 'id', '')
            if get_msg_state(m) == MsgStatus.ACKNOWLEDGED:
                acked.add(mid)
        return acked
    return {inbox.msg_field(m, 'id', '') for m in inbox.messages
            if get_msg_state(m) == MsgStatus.ACKNOWLEDGED}


def mark_as_pushed(data_dir: str, agent_name: str, msg_ids: list):
    """
    将 agent 的 inbox 中的 pending 消息标记为 pushed。
    """
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return
    
    inbox = Inbox.from_dict(inbox_data)
    changed = False
    
    for mid in msg_ids:
        if inbox.set_msg_status(mid, MsgStatus.PUSHED, state=MsgStatus.PUSHED):
            changed = True
    
    if changed:
        json_write(inbox_file, inbox.to_dict())


def update_message_status(data_dir: str, agent_name: str, msg_id: str, new_status: str):
    """
    更新 inbox 中单条消息的状态。

    状态机: pending → pushed → acknowledged → processing → done
    """
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    
    inbox = Inbox.from_dict(inbox_data)
    extra = {}
    if new_status == MsgStatus.ACKNOWLEDGED:
        extra["acknowledged_at"] = _now_iso()
        extra["state"] = MsgStatus.PROCESSING  # P4: acknowledged → processing（非 received）
        extra["received_at"] = _now_iso()
    
    found = inbox.set_msg_status(msg_id, new_status, **extra)
    
    if found:
        json_write(inbox_file, inbox.to_dict())
    
    return found


def _check_rule_changes(data_dir: str, agents: dict, paths: dict):
    """检测 store/rules/ 下规则文件的变更，变更时广播通知所有 agent
    
    使用 .rule-state.json 记录上次检测时规则文件的 mtime 和大小。
    如果检测到变更，向所有 agent 的 inbox 写入规则更新通知。
    """
    rules_dir = os.path.join(data_dir, "rules")
    if not os.path.isdir(rules_dir):
        return
    
    state_file = os.path.join(data_dir, ".rule-state.json")
    state = json_read(state_file, {})
    now_state = {}
    changed_files = []
    
    # 扫描当前规则文件状态
    try:
        for fname in sorted(os.listdir(rules_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(rules_dir, fname)
            try:
                stat = os.stat(fpath)
                now_state[fname] = {"mtime": stat.st_mtime, "size": stat.st_size}
                prev = state.get(fname)
                if prev and (prev.get("mtime", 0) != stat.st_mtime or prev.get("size", 0) != stat.st_size):
                    changed_files.append(fname)
            except OSError:
                pass
    except Exception:
        return
    
    if not changed_files:
        # 无变更，更新状态文件并返回
        json_write(state_file, now_state)
        return
    
    # 有规则变更 → 发广播通知
    import time as _time
    ts = _now_iso()
    now_ts = int(_time.time())
    
    for fname in changed_files:
        print(f"  📢 规则变更检测: {fname}")
        # 向每个 agent 的 inbox 写入规则更新通知
        for agent_name in agents:
            inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
            if not os.path.exists(os.path.dirname(inbox_file)):
                continue
            try:
                inbox_data = json_read(inbox_file, {})
                inbox = Inbox.from_dict(inbox_data) if inbox_data else Inbox(agent=agent_name)
                notify_msg = {
                    "id": f"rule-change-{fname.replace('.md','')}-{now_ts}",
                    "from": "mailbus",
                    "to": agent_name,
                    "type": "notice",
                    "priority": "normal",
                    "state": MsgStatus.PENDING,
                    "content": f"📢 规则更新通知：{fname} 已被修改，请重新阅读。\n"
                               f"路径: {os.path.join(rules_dir, fname)}",
                    "created_at": ts,
                }
                inbox.messages.append(notify_msg)
                inbox.has_unread = True
                json_write(inbox_file, inbox.to_dict())
            except Exception:
                pass
    
    # 更新状态文件
    json_write(state_file, now_state)


def _check_offline_agents(data_dir: str, agents: dict, paths: dict):
    """检测离线 agent，给对应发件人发通知"""
    from datetime import datetime, timezone, timedelta
    
    hb_file = f"{data_dir}/heartbeat.json"
    hb_data = json_read(hb_file, {})
    agent_statuses = hb_data.get("agents", {})
    now = datetime.now(timezone.utc)
    
    for name in agents:
        status_info = agent_statuses.get(name, {})
        if status_info.get("status") == "offline":
            missed = status_info.get("missed_pings", 0)
            if missed >= 3:
                # 检查是否已经发过离线通知
                notified_file = f"{data_dir}/notified_offline.json"
                notified = json_read(notified_file, {})
                last_notified = notified.get(name, "")
                if last_notified:
                    try:
                        last = datetime.fromisoformat(last_notified)
                        if (now - last).total_seconds() < 3600:  # 1小时内不再重复通知
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # 发通知给发件人
                escalate_to = "lingzhao"  # 默认通知灵昭
                escalate_file = f"{paths['inbox']}/{escalate_to}/inbox.json"
                if os.path.exists(os.path.dirname(escalate_file)):
                    try:
                        e_data = json_read(escalate_file, {})
                        e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=escalate_to)
                        import time as _time
                        warn_msg = {
                            "id": f"offline-{int(_time.time())}-{name}",
                            "from": "mailbus",
                            "to": escalate_to,
                            "type": "notice",
                            "priority": "urgent",
                            "state": MsgStatus.PENDING,
                            "content": f"⚠️ Agent 离线通知：{name} 已离线，连续 {missed} 次心跳未响应。",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                        e_inbox.messages.append(warn_msg)
                        e_inbox.has_unread = True
                        json_write(escalate_file, e_inbox.to_dict())

                        # 即时推送离线通知
                        try:
                            from .pusher import push_messages, resolve_cli
                            from ..heartbeat import load_config as _hb_config
                            cfg = _hb_config(data_dir) or {}
                            agent_types = cfg.get("agent_types", {})
                            agent_cfg = agents.get(escalate_to, {})
                            cli_cmd = resolve_cli(agent_cfg, agent_types)
                            if cli_cmd:
                                push_messages(data_dir, escalate_to, [warn_msg],
                                              cli_cmd=[cli_cmd], auto_ack=True, max_retries=1)
                        except Exception:
                            pass
                        
                        # 更新已通知记录
                        notified[name] = datetime.now(timezone.utc).isoformat()
                        json_write(notified_file, notified)
                    except Exception:
                        pass
