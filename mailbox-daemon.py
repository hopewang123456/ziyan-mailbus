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

    def start(self):
        self.log.info(f"Mailbox Daemon v0.5 启动 (任务追踪+去重保护) — agent={self.agent_name}")
        self.log.info(f"  inbox: {self.inbox_path}")
        self.log.info(f"  ack:   {self.ack_path}")
        if not os.path.exists(self.inbox_path):
            self.log.warning("inbox 尚不存在, 等待创建...")
        self._watcher = FileWatcher(self.inbox_path)
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, '_running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, '_running', False))
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
                except Exception as e:
                    self.log.error(f"循环异常: {e}", exc_info=True)
        finally:
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

        # ── 合并处理：先 ack 所有消息，再按需一次唤醒 agent ──
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

            # Step 1: auto ack（每条都 ack）
            self._auto_ack(msg_id)
            self.log.info(f"  已 ack")

            # Step 2: status_ack 单独处理
            if msg_type == 'status_ack':
                self._handle_status_ack(parsed)
                self._mark_done(msg_id, "status_ack 处理完毕")
                continue

            # Step 3: 完成回执风暴检测
            body_text = inbox.msg_field(body, 'content', '')
            if not body_text:
                body_text = str(body) if body else ''
            if body_text.startswith("✅ 任务完成回执"):
                self.log.info(f"  完成回执，无需再唤醒 agent，标记 done")
                self._mark_done(msg_id, "完成回执，不递归")
                continue

            # Step 4: 判断是否需要唤醒 agent
            if self._needs_agent(msg_type, priority, parsed, from_=from_):
                agent_entries.append({
                    "msg_id": msg_id,
                    "sender": from_,
                    "preview": preview,
                    "parsed": parsed,
                    "raw_msg": msg,  # 保留原始消息全文，用于构建回复指令
                })
            else:
                self.log.info(f"  无需唤醒 (type={msg_type})")
                self._mark_done(msg_id, "无需处理")

        # Step 5: 合并唤醒 — 一次 spawn agent 处理所有消息
        if agent_entries:
            self._trigger_agent_batch(agent_entries)

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
        # urgent 优先级别必唤醒
        if priority == "urgent":
            return True

        # 重要发件人（灵昭/子言）的消息必唤醒，不被 type 限制
        if from_ in ("lingzhao", "ziyan", "lingxi"):
            return True

        # schema 结构化类型分流
        if msg_type in ('design_review', 'task_status', 'code_review'):
            return True

        # status_ack 不唤醒（已在上层单独处理）
        if msg_type == 'status_ack':
            return False

        # 兼容旧格式
        if msg_type in ("task", "task_reply", "discuss"):
            return True
        if msg_type in ("notice", "report", "system", "forward"):
            return False
        # 兜底：新格式未知类型不唤醒，旧格式未知类型唤醒
        if parsed and parsed['version'] != '1.0':
            return False
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
        """批量唤醒：合并多条消息为一次 agent 调用"""
        if not entries:
            return

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
            # 单条消息：直接用 preview 做摘要（不走 _trigger_agent 避免递归）
            e = entries[0]
            summary = e["preview"]
        else:
            # 多条消息：构建合并摘要
            self.log.info(f"  合并唤醒 agent: {len(entries)} 条消息（来自 {len(set(e['sender'] for e in entries))} 个发件人）")
            summary = self._build_combined_message(entries)

        config = read_json(os.path.join(self.data_dir, "config.json"), {})
        agent_cfg = config.get("agents", {}).get(self.agent_name, {})
        atype = agent_cfg.get("type", "none")
        tmpl = config.get("agent_types", {}).get(atype, {}).get("push", "")
        if not tmpl:
            self.log.warning("未找到 CLI 模板, 跳过唤醒")
            for mid in all_msg_ids:
                self._mark_done(mid, "CLI 模板未配置")
            return

        cmd = self._build_agent_cmd(tmpl, agent_cfg, config, summary)
        self.log.info(f"  CLI: {cmd[:150]}...（{len(entries)} 条消息）")
        self._spawn_agent_process(cmd, all_msg_ids, all_senders, summary)

    def _build_combined_message(self, entries):
        """为多条消息构建合并摘要，每条包含内容 + 回复指令"""
        msg_blocks = []
        for i, e in enumerate(entries, 1):
            sender = e["sender"]
            raw = e["raw_msg"]
            content = raw.get("content", "")
            msg_type = raw.get("type", "notice")
            priority = raw.get("priority", "normal")
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
        """spawn agent 子进程，记录到 _running_procs"""
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
            }
            self.log.info(f"  agent 已唤醒 (PID: {proc.pid}, 消息数: {len(msg_ids)})")
        except Exception as e:
            self.log.error(f"  唤醒失败: {e}")
            # 所有消息都发失败回执 + 移出处理中集合
            for mid in msg_ids:
                s = senders.get(mid, "unknown")
                self._send_completion_notice(mid, s, "失败", f"Agent 唤醒失败: {e}")
                self._processing_ids.discard(mid)

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

    def _reap_processes(self):
        """检查已完成的 agent 进程, 发回执（支持 msg_ids 批量）；超时进程自动 kill"""
        now = time.time()
        finished = []
        for pid, info in list(self._running_procs.items()):
            proc = info["proc"]
            ret = proc.poll()
            elapsed = now - info["started_at"]

            # ── 超时保护：运行超过 MAX_AGENT_RUNTIME 的进程强制 kill ──
            if ret is None and elapsed > MAX_AGENT_RUNTIME:
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
                self.log.info(f"  agent 进程完成 (PID: {pid}, 耗时: {elapsed:.0f}s, 返回码: {ret})")
                # 收集 stdout（过滤 ANSI 转义 + [thinking] 痕迹，截短防 token 浪费）
                stdout = ""
                try:
                    import re
                    out, _ = proc.communicate(timeout=5)
                    raw = out.decode("utf-8", errors="replace")
                    raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
                    lines = [l for l in raw.split("\n") if "[thinking]" not in l and "[/thinking]" not in l]
                    stdout = "\n".join(lines).strip()[:100]
                except Exception:
                    pass
                status = "完成" if ret == 0 else f"异常退出(code={ret})"

                # 兼容新旧格式：msg_ids（列表）或 msg_id（字符串）
                msg_ids = info.get("msg_ids") or [info.get("msg_id")]
                senders = info.get("senders") or {info.get("msg_id", ""): info.get("sender", "")}

                # 给每条原始消息发回执 + mark_done + 更新追踪
                for mid in msg_ids:
                    sender = senders.get(mid, "unknown")
                    self._send_completion_notice(mid, sender, status, stdout or None)
                    self._mark_done(mid, f"agent 已处理({status})")
                    self._complete_task(mid, status, stdout)
                    # 从处理中集合移除，允许崩溃恢复重新处理
                    self._processing_ids.discard(mid)
        for pid in finished:
            del self._running_procs[pid]

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
