#!/usr/bin/env python3
"""mailbox-daemon.py — Agent 侧邮箱守护进程 v0.5 (任务追踪+去重保护)"""
import os, sys, json, time, signal, logging, argparse, subprocess, tempfile, re
from datetime import datetime, timezone, timedelta
from lib.constants import DEFAULT_DATA_DIR as _DD, DEFAULT_LOG_DIR as _LD, DEFAULT_POLL_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL
from lib.models import Inbox

# ── 进程管理常量 ──
MAX_AGENT_RUNTIME = 1800  # 30 分钟超时，超时自动 kill

DEFAULT_DATA_DIR = _DD
POLL_INTERVAL = DEFAULT_POLL_INTERVAL
HEARTBEAT_INTERVAL = DEFAULT_HEARTBEAT_INTERVAL
LOG_DIR = _LD
TZ_CST = timezone(timedelta(hours=8))

def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def write_json(path, data):
    """原子写 JSON，使用临时文件避免竞态"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise

from lib.utils import _now_iso as now_iso

# ── 文件监听器 ──

class FileWatcher:
    def __init__(self, filepath, interval=POLL_INTERVAL):
        self.filepath = filepath
        self.interval = interval
        self._inotify = None
        self._last_mtime = 0
        self._init()
    def _init(self):
        try:
            from inotify_simple import INotify, flags
            self._inotify = INotify()
            self._inotify.add_watch(self.filepath, flags.CLOSE_WRITE | flags.MODIFY)
            logging.info("监听模式: inotify")
        except ImportError:
            try:
                self._last_mtime = os.path.getmtime(self.filepath)
            except OSError:
                pass
            logging.info(f"监听模式: poll ({self.interval}s)")
    def wait(self, timeout=None):
        if self._inotify:
            import select
            to = timeout or self.interval
            try:
                r, _, _ = select.select([self._inotify.fd], [], [], to)
                if r:
                    self._inotify.read(timeout=0)
                    return True
            except (OSError, ValueError):
                pass
            return False
        time.sleep(timeout or self.interval)
        try:
            cur = os.path.getmtime(self.filepath)
            if cur != self._last_mtime:
                self._last_mtime = cur
                return True
        except OSError:
            pass
        return False
    def close(self):
        if self._inotify:
            try:
                self._inotify.close()
            except Exception:
                pass

# ── 核心守护进程 ──

class MailboxDaemon:
    def __init__(self, agent_name, data_dir=DEFAULT_DATA_DIR):
        self.agent_name = agent_name
        self.data_dir = data_dir
        self.inbox_path = os.path.join(data_dir, "inbox", agent_name, "inbox.json")
        self.ack_path = os.path.join(data_dir, "inbox", agent_name, "ack.json")
        self.hb_path = os.path.join(data_dir, f"heartbeat.{agent_name}.json")
        self._running = True
        self._last_hb = 0
        self._last_archive = 0
        self._watcher = None
        # {pid: {msg_ids, senders, summary, proc, started_at}}
        self._running_procs = {}
        # 内存级去重：正在处理的消息 ID 集合（防止重复 poll）
        self._processing_ids = set()
        self._setup_logging()

    def _setup_logging(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f"daemon-{self.agent_name}.log")
        logging.basicConfig(
            level=logging.INFO,
            format=f"%(asctime)s [%(levelname)s] [{self.agent_name}] %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
        )
        self.log = logging.getLogger(self.agent_name)

    # ── 消息解析（统一使用邮件格式） ──

    def _parse_message(self, msg, inbox=None) -> dict:
        _mf = (lambda m, f, d='': inbox.msg_field(m, f, d)) if inbox else (
            lambda m, f, d='': m.get(f, d) if isinstance(m, dict) else getattr(m, f, d))
        content = _mf(msg, 'content', '')
        return {
            'id': _mf(msg, 'id', ''),
            'from': _mf(msg, 'from', ''),
            'to': _mf(msg, 'to', ''),
            'cc': [],
            'priority': _mf(msg, 'priority', 'normal'),
            'type': _mf(msg, 'type', 'notice'),
            'version': '1.0',
            'body': {'content': content, 'raw_type': _mf(msg, 'type', 'notice')},
            'preview': (content[:80] if isinstance(content, str) else str(content)[:80]).replace('\n', ' '),
            'created_at': _mf(msg, 'created_at', ''),
            'thread_id': '',
            'reply_to': '',
        }

    # ── 工具方法 ──

    @staticmethod
    def build_message(
        msg_type: str,
        to: str,
        body: dict,
        *,
        from_agent: str = 'mailbus',
        priority: str = 'normal',
        thread_id: str = '',
        reply_to: str = '',
        cc: list = None,
        payload_version: str = '1.0',
    ) -> dict:
        """
        构建符合 mailbus schema 的结构化消息。
        msg_type: design_review | task_status | status_ack | code_review
        """
        import random
        ts = now_iso()
        msg_id = f"{msg_type}-{datetime.now(TZ_CST).strftime('%Y%m%d')}-{random.randint(100000, 999999)}"
        return {
            "mailbus": {
                "version": "1.0",
                "msg_id": msg_id,
                "envelope": {
                    "from": from_agent,
                    "to": to,
                    "cc": cc or [],
                    "priority": priority,
                    "created_at": ts,
                    "thread_id": thread_id,
                    "reply_to": reply_to,
                },
            },
            "payload": {
                "type": msg_type,
                "version": payload_version,
                "body": body,
            },
        }

    # ── Checkpoint 持久化 ──

    CHECKPOINT_FILE = "checkpoint.json"  # 存放在 data_dir 下

    def _save_checkpoint(self):
        """将当前运行中的任务状态写入 checkpoint，供崩溃恢复"""
        procs_data = []
        for pid, info in self._running_procs.items():
            proc = info["proc"]
            ret = proc.poll()
            if ret is not None:
                continue  # 已完成的进程不保存
            procs_data.append({
                "pid": pid,
                "msg_ids": info.get("msg_ids", []),
                "senders": info.get("senders", {}),
                "summary": info.get("summary", ""),
                "cmd": info.get("cmd", ""),
                "started_at": info.get("started_at", 0),
            })
        if procs_data:
            ckpt = {
                "agent": self.agent_name,
                "timestamp": now_iso(),
                "running_procs": procs_data,
                "processing_ids": list(self._processing_ids),
                "retry_map": getattr(self, '_retry_map', {}),
            }
            write_json(os.path.join(self.data_dir, self.CHECKPOINT_FILE), ckpt)
            self.log.debug(f"checkpoint 已保存: {len(procs_data)} 个运行中任务")

    def _load_checkpoint(self):
        """从 checkpoint 恢复运行中任务的状态追踪"""
        ckpt_path = os.path.join(self.data_dir, self.CHECKPOINT_FILE)
        ckpt = read_json(ckpt_path)
        if not ckpt:
            return
        self.log.info(f"发现 checkpoint: agent={ckpt.get('agent')}, "
                      f"运行中任务={len(ckpt.get('running_procs', []))}")
        # 恢复 processing_ids 和 retry_map
        for mid in ckpt.get("processing_ids", []):
            self._processing_ids.add(mid)
        self._retry_map = ckpt.get("retry_map", {})
        # 恢复任务状态（进程已死，标记为需要重试）
        for pd in ckpt.get("running_procs", []):
            for mid in pd.get("msg_ids", []):
                self.log.warning(f"  ⚠️ checkpoint 恢复: 消息 {mid} 上次运行被中断，标记待重试")
                # 通知发件人任务被中断
                sender = pd.get("senders", {}).get(mid, "unknown")
                self._send_completion_notice(
                    mid, sender, "中断",
                    "Daemon 重启恢复: 上次 session 被信号终止，请重新派发"
                )
                self._mark_done(mid, "daemon 重启恢复: 被中断")
        # 清理 checkpoint 文件（避免重复恢复）
        try:
            os.remove(ckpt_path)
        except OSError:
            pass
        self.log.info("checkpoint 恢复完成，历史运行中任务已标记中断")

    # ── Graceful Shutdown ──

    def _handle_shutdown(self, signum, frame):
        """优雅关闭：先等待子进程，再退出"""
        sig_name = self._signal_name(signum) if signum <= 128 else self._signal_name(signum + 128) or f"SIGNAL({signum})"
        self.log.warning(f"收到关闭信号 {sig_name}({signum})，开始优雅关闭...")

        # 保存 checkpoint
        self._save_checkpoint()

        # 标记停止，主循环会退出
        self._running = False

        # 给子进程最多 10 秒完成
        deadline = time.time() + 10
        for pid, info in list(self._running_procs.items()):
            proc = info["proc"]
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                proc.wait(timeout=remaining)
                self.log.info(f"  子进程 (PID: {pid}) 已正常退出")
            except subprocess.TimeoutExpired:
                self.log.warning(f"  子进程 (PID: {pid}) 超时未退出，发送 SIGTERM")
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass

        self.log.info("优雅关闭完成")

    def start(self):
        self.log.info(f"Mailbox Daemon v0.5 启动 (任务追踪+去重保护+checkpoint) — agent={self.agent_name}")
        self.log.info(f"  inbox: {self.inbox_path}")
        self.log.info(f"  ack:   {self.ack_path}")
        if not os.path.exists(self.inbox_path):
            self.log.warning("inbox 尚不存在, 等待创建...")
        self._watcher = FileWatcher(self.inbox_path)

        # ── Signal 处理：优雅关闭 ──
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        # 忽略 SIGPIPE（防止写管道时意外退出）
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        # ── 从 checkpoint 恢复 ──
        self._load_checkpoint()

        # ── 清理上一轮孤儿进程 ──
        self._cleanup_orphans()
        # 清理上一轮的临时脚本
        for f in os.listdir(LOG_DIR):
            if f.startswith(f"run-{self.agent_name}-") and f.endswith(".sh"):
                os.remove(os.path.join(LOG_DIR, f))
        self._process_inbox()
        try:
            while self._running:
                try:
                    if self._watcher.wait(timeout=5):
                        self._process_inbox()
                    self._reap_processes()
                    self._heartbeat_tick()
                    self._archive_tick()
                    # 每 60 秒保存一次 checkpoint
                    if int(time.time()) % 60 < 5:
                        self._save_checkpoint()
                except Exception as e:
                    self.log.error(f"循环异常: {e}", exc_info=True)
        finally:
            self._save_checkpoint()  # 退出前保存最后一次 checkpoint
            self._watcher.close()
            self.log.info("Mailbox Daemon 已停止")

    # ── 收信处理 ──

    def _process_inbox(self):
        raw_inbox = read_json(self.inbox_path)
        if not raw_inbox:
            return
        inbox = Inbox.from_dict(raw_inbox)
        # 读取已 ack 的消息 ID 集合, 避免重复处理
        acked_ids = set()
        ack_data = read_json(self.ack_path, [])
        ack_entries = [ack_data] if isinstance(ack_data, dict) else (ack_data or [])
        for e in ack_entries:
            eid = e.get("msg_id") if isinstance(e, dict) else getattr(e, 'msg_id', '')
            if (e.get("action") if isinstance(e, dict) else getattr(e, 'action', '')) == "ack":
                acked_ids.add(eid)
        pending_raw = [
            m for m in inbox.messages
            if inbox.msg_field(m, 'id', '') not in acked_ids
            and inbox.msg_field(m, 'id', '') not in self._processing_ids
            and (
                (inbox.msg_field(m, 'status', '') in ("new", "pending"))
                or
                (inbox.msg_field(m, 'status', '') == "acknowledged"
                 and inbox.msg_field(m, 'state', '') != "done")
            )
        ]
        if not pending_raw:
            return
        self.log.info(f"发现 {len(pending_raw)} 条待处理消息 (含崩溃恢复)")

        # ── 合并处理（延迟 ack 策略）：先收集，agent 成功唤醒后才 ack ──
        # ⚠️ 关键设计：_auto_ack 写入 ack.json 后，消息 ID 进入「已处理」黑名单
        #    如果 agent 崩溃/session 过期，下次启动时该消息会被永久跳过。
        #    因此：只有确认 agent 已成功唤醒后，才调用 _auto_ack。
        #    不需要唤醒的消息（report/system）可以直接 ack。
        agent_entries = []  # [{msg_id, sender, preview, parsed, raw_msg}, ...]

        for msg in pending_raw:
            parsed = self._parse_message(msg, inbox)
            msg_id = parsed['id']
            msg_type = parsed['type']
            priority = parsed['priority']
            from_ = parsed['from']
            preview = parsed['preview']
            body = parsed['body']

            self.log.info(f"  [{msg_type}] {msg_id} 来自 {from_}: {preview}")

            # Step 1: status_ack 单独处理（不涉及 agent 消息内容，直接处理）
            if msg_type == 'status_ack':
                self._handle_status_ack(parsed)
                self._auto_ack(msg_id)
                self._mark_done(msg_id, "status_ack 处理完毕")
                continue

            # Step 2: 完成回执风暴检测（agent 的自动回复，无需再次唤醒）
            body_text = inbox.msg_field(body, 'content', '')
            if not body_text:
                body_text = str(body) if body else ''
            if body_text.startswith("✅ 任务完成回执"):
                self.log.info(f"  完成回执，无需再唤醒 agent，标记 done")
                self._auto_ack(msg_id)
                self._mark_done(msg_id, "完成回执，不递归")
                continue

            # Step 3: 判断是否需要唤醒 agent
            if self._needs_agent(msg_type, priority, parsed, from_=from_):
                agent_entries.append({
                    "msg_id": msg_id,
                    "sender": from_,
                    "preview": preview,
                    "parsed": parsed,
                    "raw_msg": msg,  # 保留原始消息全文，用于构建回复指令
                })
                # 🚫 不 auto_ack！等 agent 成功唤醒后再 ack，防止 session 过期丢消息
            else:
                self.log.info(f"  无需唤醒 (type={msg_type}), 直接 ack+done")
                self._auto_ack(msg_id)
                self._mark_done(msg_id, "无需处理")

        # Step 4: 合并唤醒 — 一次 spawn agent 处理所有消息
        if agent_entries:
            ok = self._trigger_agent_batch(agent_entries)
            if ok:
                # ✅ agent 已成功 spawn，现在安全了 — 写入 ack.json，防止下次重复触发
                for e in agent_entries:
                    self._auto_ack(e["msg_id"])
                self.log.info(f"  ✅ agent 唤醒成功, {len(agent_entries)} 条消息已 ack")
            else:
                # ❌ spawn 失败，不移除 processing_ids，下次 poll 重新发现/重试
                self.log.warning(f"  ⚠️ agent 唤醒失败, {len(agent_entries)} 条消息保留 pending 供下次重试")

    def _handle_status_ack(self, parsed: dict):
        """处理 status_ack 类型消息：记录 ack 状态到对应消息"""
        body = parsed['body']
        ack_for = body.get('ack_for_msg_id', '')
        ack_status = body.get('ack_status', 'received')
        notes = body.get('notes', '')
        self.log.info(f"  收到回执: {ack_for} → {ack_status}{f' ({notes})' if notes else ''}")

        inbox_dir = os.path.join(self.data_dir, "inbox")
        updated = False
        if os.path.isdir(inbox_dir):
            for agent_dir in os.listdir(inbox_dir):
                inbox_file = os.path.join(inbox_dir, agent_dir, "inbox.json")
                raw = read_json(inbox_file)
                if not raw:
                    continue
                obj = Inbox.from_dict(raw)
                for m in obj.messages:
                    if obj.msg_field(m, 'id', '') == ack_for:
                        m['ack_status'] = ack_status
                        if notes:
                            m['ack_notes'] = notes
                        m['ack_received_at'] = now_iso()
                        write_json(inbox_file, obj.to_dict())
                        updated = True
                        break
        if not updated:
            self.log.debug(f"  未找到原始消息 {ack_for}（可能已归档）")

        self._mark_done(parsed['id'], f"status_ack 处理完毕: {ack_for} → {ack_status}")

    def _needs_agent(self, msg_type, priority, parsed=None, from_=None):
        # urgent 优先级必唤醒
        if priority == "urgent":
            return True

        # 🔑 核心修复: 任何来自其他 agent 的消息（有发件人）必唤醒
        # 防止「缓存的信件无人读」——以前的逻辑只认特定type，导致 notice/forward 被静默吃掉
        if from_ and from_ not in ("mailbus", "system", ""):
            return True

        # schema 结构化类型分流
        if msg_type in ('design_review', 'task_status', 'code_review'):
            return True

        # status_ack 不唤醒（已在上层单独处理）
        if msg_type == 'status_ack':
            return False

        # 兼容旧格式
        if msg_type in ("task", "task_reply", "discuss", "notice", "forward"):
            return True
        # report/system 不唤醒（系统自动产生）
        if msg_type in ("report", "system"):
            return False
        # 兜底：新格式未知类型唤醒（保守策略：宁多不少）
        if parsed and parsed['version'] != '1.0':
            return True
        return True

    # ── 任务追踪 ──

    def _track_task(self, msg_id, summary, sender):
        """创建或更新任务追踪记录"""
        try:
            from lib.tracker import TaskTracker
            tracker = TaskTracker(self.data_dir)
            task = tracker.get(msg_id)
            if not task:
                tracker.create(
                    task_id=msg_id,
                    summary=summary[:200],
                    assignee=self.agent_name,
                    chain_hops=[{"agent": sender, "action": "发起任务"}],
                )
                self.log.info(f"  任务已创建: {msg_id}")
            tracker.update_status(msg_id, "running")
            tracker.add_hop(msg_id, self.agent_name, "开始处理")
        except Exception as e:
            self.log.warning(f"  任务追踪异常: {e}")

    def _complete_task(self, msg_id, status, detail=None):
        """标记任务完成"""
        try:
            from lib.tracker import TaskTracker
            tracker = TaskTracker(self.data_dir)
            task = tracker.get(msg_id)
            if task:
                ts = "success" if status == "完成" else "failed"
                tracker.update_status(msg_id, ts)
                tracker.add_hop(msg_id, self.agent_name, f"处理完成: {status}")
                if detail:
                    tracker.update_status(msg_id, ts, {"detail": detail[:200]})
        except Exception as e:
            self.log.warning(f"  任务完成追踪异常: {e}")

    # ── Ack ──

    def _auto_ack(self, msg_id):
        ts = now_iso()
        ack = read_json(self.ack_path, [])
        ack_list = [ack] if isinstance(ack, dict) else (ack or [])
        if any(e.get("msg_id") == msg_id and e.get("action") == "ack" for e in ack_list):
            return
        ack_list.append({"action": "ack", "msg_id": msg_id,
                         "agent": self.agent_name, "timestamp": ts})
        write_json(self.ack_path, ack_list)
        raw = read_json(self.inbox_path)
        if raw:
            inbox = Inbox.from_dict(raw)
            if inbox.set_msg_status(msg_id, "acknowledged", acknowledged_at=ts):
                inbox.has_unread = inbox.has_unread_messages()
                write_json(self.inbox_path, inbox.to_dict())

    def _mark_done(self, msg_id, note=""):
        raw = read_json(self.inbox_path)
        if not raw:
            return
        inbox = Inbox.from_dict(raw)
        found = False
        extra = {"state": "done", "done_at": now_iso()}
        if note:
            extra["done_note"] = note
        for m in inbox.messages:
            if inbox.msg_field(m, 'id', '') == msg_id:
                for k, v in extra.items():
                    inbox.set_msg_field(m, k, v)
                found = True
                break
        if found:
            inbox.has_unread = inbox.has_unread_messages()
            write_json(self.inbox_path, inbox.to_dict())

    # ── CLI 唤醒 + 完成追踪 ──

    def _trigger_agent_batch(self, entries):
        """批量唤醒：合并多条消息为一次 agent 调用
        
        返回: True=agent 已成功 spawn (可安全 ack)
              False=spawn 失败 (不要 ack，让下次重试)
        """
        if not entries:
            return False

        # 构建合并数据
        all_msg_ids = []
        all_senders = {}
        for e in entries:
            self._track_task(e["msg_id"], e["preview"], e["sender"])
            all_msg_ids.append(e["msg_id"])
            all_senders[e["msg_id"]] = e["sender"]
            # 加入处理中集合，防重复 poll
            self._processing_ids.add(e["msg_id"])

        if len(entries) == 1:
            e = entries[0]
            summary = e["preview"]
        else:
            self.log.info(f"  合并唤醒 agent: {len(entries)} 条消息（来自 {len(set(e['sender'] for e in entries))} 个发件人）")
            summary = self._build_combined_message(entries)

        config = read_json(os.path.join(self.data_dir, "config.json"), {})
        agent_cfg = config.get("agents", {}).get(self.agent_name, {})
        atype = agent_cfg.get("type", "none")
        tmpl = config.get("agent_types", {}).get(atype, {}).get("push", "")
        if not tmpl:
            self.log.warning("未找到 CLI 模板, 跳过唤醒 → 保留 pending 供下次重试")
            # 不移除 processing_ids，让下次循环重新发现
            return False

        cmd = self._build_agent_cmd(tmpl, agent_cfg, config, summary)
        self.log.info(f"  CLI: {cmd[:150]}...（{len(entries)} 条消息）")
        result = self._spawn_agent_process(cmd, all_msg_ids, all_senders, summary)
        return result  # True=已spawn, False=失败

    def _build_combined_message(self, entries):
        """为多条消息构建合并摘要，每条包含内容 + 回复指令"""
        msg_blocks = []
        for i, e in enumerate(entries, 1):
            sender = e["sender"]
            raw = e["raw_msg"]
            # raw 可能是 Message 对象（dataclass）或 dict，统一用 safe_get 兼容
            content = raw.content if hasattr(raw, 'content') else raw.get("content", "")
            msg_type = raw.type if hasattr(raw, 'type') else raw.get("type", "notice")
            priority = raw.priority if hasattr(raw, 'priority') else raw.get("priority", "normal")
            reply_path = f"{self.data_dir}/inbox/{sender}/inbox.json"
            reply_msg_id = f"reply-{e['msg_id']}"

            block = (
                f"╔══ 消息 {i} ═══════════════════════════╗\n"
                f"  类型: {msg_type}\n"
                f"  来自: {sender}\n"
                f"  消息ID: {e['msg_id']}\n"
                f"  优先级: {priority}\n"
                f"  内容: {content[:500]}\n"
                f"╚════════════════════════════════════╝\n"
                f"\n"
                f"▶ 回复给 {sender}\n"
                f"  写文件到: {reply_path}\n"
                f"  在 messages 数组末尾追加一条，设 has_unread=true：\n"
                f"  ```json\n"
                f"  {{\"id\":\"{reply_msg_id}\",\"from\":\"{self.agent_name}\",\"to\":\"{sender}\",\"type\":\"reply\",\"priority\":\"normal\",\"status\":\"pending\",\"content\":\"<你的回复>\",\"created_at\":\"<ISO时间>\"}}\n"
                f"  ```\n"
            )
            msg_blocks.append(block)

        return (
            f"你有 {len(entries)} 条待处理消息，来自不同的发件人。\n"
            f"请逐条处理，每条消息的回复请对应发给各自的发件人。\n"
            f"\n"
            f"{'─' * 50}\n"
            f"\n"
            f"{chr(10).join(msg_blocks)}"
        )

    def _build_agent_cmd(self, tmpl, agent_cfg, config, summary_text):
        """构建 agent CLI 命令（模板替换）"""
        cmd = tmpl.replace("PROFILE", agent_cfg.get("profile", "") or self.agent_name)
        cmd = cmd.replace("AGENT", agent_cfg.get("agent", "") or self.agent_name)
        models_map = config.get("agent_types", {}).get("models", {})
        agent_models = agent_cfg.get("models", [])
        if agent_models and agent_models[0] in models_map:
            mf = models_map[agent_models[0]].get(agent_cfg.get("type", "none"), "")
            if mf:
                cmd = cmd.replace("MODEL", mf)
                cmd = cmd.replace("--model MODEL", f"--model {mf}")
                cmd = cmd.replace("-m MODEL", f"-m {mf}")
            else:
                for p in ["--model MODEL", "-m MODEL", "MODEL"]:
                    cmd = cmd.replace(p, "")
        provider = agent_cfg.get("provider", "")
        if provider:
            cmd = cmd.replace("PROVIDER", provider)
        else:
            cmd = cmd.replace("--provider PROVIDER", "").replace("PROVIDER", "")
        cmd = cmd.replace("MSG", f"你有新的任务消息: {summary_text}")
        cmd = " ".join(cmd.split())
        return cmd

    def _spawn_agent_process(self, cmd, msg_ids, senders, summary_text):
        """spawn agent 子进程，记录到 _running_procs
        
        返回: True=进程已spawn, False=spawn失败
        """
        env = os.environ.copy()
        home = os.path.expanduser("~")
        extra_paths = [
            "/usr/local/bin", "/usr/bin", "/bin",
            f"{home}/.local/bin",
            f"{home}/.npm-global/bin",
            "/mnt/e/hermes-data/.hermes/hermes-agent/venv/bin",
            "/mnt/e/ai_tools/opencode",
        ]
        existing_path = env.get("PATH", "")
        env["PATH"] = ":".join(p for p in extra_paths if os.path.isdir(p)) + ":" + existing_path

        for ep in [f"{home}/.hermes/.env",
                   os.path.join(os.path.dirname(self.data_dir), "..", ".env")]:
            if os.path.exists(ep):
                with open(ep) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            env[k.strip()] = v.strip().strip("'\"")
                break

        script_content = "#!/bin/bash\n" + cmd
        script_path = os.path.join(LOG_DIR, f"run-{self.agent_name}-{int(time.time())}.sh")
        with open(script_path, "w") as f:
            f.write(script_content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(script_path, 0o755)
        runner = f"bash {script_path}"

        try:
            proc = subprocess.Popen(runner, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, start_new_session=True,
                                    env=env, close_fds=True)
            self._running_procs[proc.pid] = {
                "msg_ids": msg_ids,        # 改为列表，支持多条
                "senders": senders,         # {msg_id: sender}
                "summary": summary_text,
                "proc": proc,
                "started_at": time.time(),
                "cmd": cmd,                # 保存完整命令，供信号退出重试使用
            }
            self.log.info(f"  agent 已唤醒 (PID: {proc.pid}, 消息数: {len(msg_ids)})")
            return True
        except Exception as e:
            self.log.error(f"  唤醒失败: {e}")
            # 所有消息都发失败回执 + 移出处理中集合
            for mid in msg_ids:
                s = senders.get(mid, "unknown")
                self._send_completion_notice(mid, s, "失败", f"Agent 唤醒失败: {e}")
                self._processing_ids.discard(mid)
            return False

    def _trigger_agent(self, msg_id, sender, summary):
        """单条消息唤醒（原有逻辑，委托给 batch 方法）"""
        self._trigger_agent_batch([{
            "msg_id": msg_id,
            "sender": sender,
            "preview": summary,
            "parsed": {},
            "raw_msg": {"content": summary, "type": "task", "priority": "normal"},
        }])

    # ── 进程收割 + 完成回执 ──

    @staticmethod
    def _cleanup_orphans():
        """启动时清理上一轮 daemon 留下的孤儿进程"""
        import subprocess, re
        try:
            # 查找由 mailbox-daemon 唤醒、但父进程已不存在的 opencode/hermes 进程
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split("\n"):
                if "你有新的任务消息:" in line:
                    parts = line.strip().split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            os.kill(int(pid), signal.SIGKILL)
                            logging.info(f"  孤儿进程已清理 (PID: {pid})")
                        except (OSError, ValueError):
                            pass
        except Exception:
            pass

    def _signal_name(self, retcode: int) -> str:
        """将退出码转换为信号名称（如 137 → 'SIGKILL', 139 → 'SIGSEGV'）"""
        if retcode < 0:
            sig_num = -retcode
        elif retcode >= 128:
            sig_num = retcode - 128
        else:
            return ""
        import signal as _sig
        name_map = {getattr(_sig, n): n for n in dir(_sig) if n.startswith('SIG') and not n.startswith('SIG_')}
        return name_map.get(sig_num, f"信号({sig_num})")

    def _reap_processes(self):
        """检查已完成的 agent 进程, 发回执（支持 msg_ids 批量）；超时进程自动 kill；信号退出自动重试"""
        now = time.time()
        finished = []
        # 重试追踪：{mid: retry_count}
        retry_map = getattr(self, '_retry_map', {})
        for pid, info in list(self._running_procs.items()):
            proc = info["proc"]
            ret = proc.poll()
            elapsed = now - info["started_at"]
            msg_ids = info.get("msg_ids") or [info.get("msg_id")]
            senders = info.get("senders") or {info.get("msg_id", ""): info.get("sender", "")}

            # ── 超时保护：运行超过 MAX_AGENT_RUNTIME 的进程强制 kill ──
            if ret is None and elapsed > MAX_AGENT_RUNTIME:
                sig_name = "SIGKILL(超时)"
                self.log.warning(f"  agent 超时 ({elapsed:.0f}s > {MAX_AGENT_RUNTIME}s), 强制终止 (PID: {pid})")
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
                ret = -9
                elapsed = now - info["started_at"]

            if ret is not None:
                finished.append(pid)
                sig_name = self._signal_name(ret)
                sig_detail = f" → 信号终止: {sig_name}" if sig_name else ""

                # ── 信号退出检测与自动重试 ──
                is_signal_exit = bool(sig_name) or ret != 0
                do_retry = False
                if is_signal_exit and ret != 0:
                    # 检查是否已重试过
                    all_retried = all(
                        retry_map.get(mid, 0) < 3 for mid in msg_ids
                    )
                    if all_retried and elapsed < MAX_AGENT_RUNTIME * 0.5:
                        # 记录重试
                        for mid in msg_ids:
                            retry_map[mid] = retry_map.get(mid, 0) + 1
                            self.log.warning(f"  ⚠️ 消息 {mid}: 信号退出(ret={ret}{sig_detail}), 发起第 {retry_map[mid]} 次重试")
                        do_retry = True

                if do_retry:
                    # 重新 spawn 进程
                    self._spawn_agent_process(
                        info.get("cmd", ""),
                        msg_ids,
                        senders,
                        info.get("summary", ""),
                    )
                    continue

                # ── 正常完成 → 发回执 ──
                self.log.info(f"  agent 进程完成 (PID: {pid}, 耗时: {elapsed:.0f}s, 返回码: {ret}{sig_detail})")
                # 收集 stdout（过滤 ANSI 转义 + [thinking] 痕迹，截短防 token 浪费）
                stdout = ""
                try:
                    out, _ = proc.communicate(timeout=5)
                    raw = out.decode("utf-8", errors="replace")
                    raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
                    lines = [l for l in raw.split("\n") if "[thinking]" not in l and "[/thinking]" not in l]
                    stdout = "\n".join(lines).strip()[:100]
                except Exception:
                    pass

                if sig_name:
                    status = f"信号终止(code={ret}, {sig_name})"
                else:
                    status = "完成" if ret == 0 else f"异常退出(code={ret})"

                # 给每条原始消息发回执 + mark_done + 更新追踪
                for mid in msg_ids:
                    sender = senders.get(mid, "unknown")
                    self._send_completion_notice(mid, sender, status, stdout or None)
                    self._mark_done(mid, f"agent 已处理({status})")
                    self._complete_task(mid, status, stdout)
                    # 从处理中集合移除
                    self._processing_ids.discard(mid)
                    retry_map.pop(mid, None)

        for pid in finished:
            del self._running_procs[pid]

        self._retry_map = retry_map

    def _send_completion_notice(self, original_msg_id, sender, status, detail=None):
        """任务完成后, 写一条回执到发件人的 inbox"""
        if not sender or sender in ("mailbus", "broadcast", "system", "manual", ""):
            self.log.debug(f"无需回执 (sender={sender})")
            return
        ts = now_iso()
        notice = {
            "id": f"done-{original_msg_id}-{int(time.time())}",
            "from": self.agent_name,
            "to": sender,
            "type": "reply",
            "priority": "normal",
            "status": "pending",
            "content": (
                f"✅ 任务完成回执\n"
                f"原始消息: {original_msg_id}\n"
                f"处理 agent: {self.agent_name}\n"
                f"状态: {status}\n"
                + (f"\n输出摘要:\n{detail[:100]}" if detail else "")
            ),
            "created_at": ts,
        }
        sender_inbox = os.path.join(self.data_dir, "inbox", sender, "inbox.json")
        inbox = read_json(sender_inbox, {"agent": sender, "has_unread": False, "messages": []})
        inbox["messages"].append(notice)
        inbox["has_unread"] = True
        write_json(sender_inbox, inbox)
        self.log.info(f"  回执已发送至 {sender} (原始消息: {original_msg_id})")

    # ── 心跳 ──

    def _heartbeat_tick(self):
        now = time.time()
        if now - self._last_hb < HEARTBEAT_INTERVAL:
            return
        self._last_hb = now
        ts = datetime.now(timezone.utc).isoformat()
        hb = {
            "agent": self.agent_name,
            "status": "online",
            "daemon": True,
            "last_seen": ts,
            "pid": os.getpid(),
            "running_tasks": len(self._running_procs),
        }
        write_json(self.hb_path, hb)
        self.log.debug(f"心跳已更新 (进行中任务: {len(self._running_procs)})")

    # ── 归档 ──

    ARCHIVE_INTERVAL = 600  # 每 10 分钟归档一次

    def _archive_tick(self):
        now = time.time()
        if now - self._last_archive < self.ARCHIVE_INTERVAL:
            return
        self._last_archive = now
        try:
            from lib.archiver import archive_agent
            cfg = read_json(os.path.join(self.data_dir, "config.json"), {})
            archive_days = cfg.get("archive_days", 7)
            max_msgs = cfg.get("archive_max_messages", 300)
            count = archive_agent(self.data_dir, self.agent_name, archive_days, max_msgs)
            if count > 0:
                self.log.info(f"归档完成: 已归档 {count} 条消息")
        except Exception as e:
            self.log.debug(f"归档检查: {e}")


# ── CLI ──

def main():
    global LOG_DIR
    parser = argparse.ArgumentParser(description="Mailbox Daemon — Agent 侧邮箱守护进程")
    parser.add_argument("--agent", required=True, help="Agent 名称")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="mailbus store 目录")
    parser.add_argument("--daemon", action="store_true", help="后台运行")
    parser.add_argument("--log-dir", default=None, help="日志目录（默认: lib/constants.py 的 DEFAULT_LOG_DIR）")
    args = parser.parse_args()
    if args.log_dir:
        LOG_DIR = args.log_dir
    if args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"Mailbox Daemon 已启动 (PID: {pid})")
            sys.exit(0)
    MailboxDaemon(agent_name=args.agent, data_dir=args.data_dir).start()


if __name__ == "__main__":
    main()
