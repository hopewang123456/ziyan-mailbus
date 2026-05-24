#!/usr/bin/env python3
"""mailbox-daemon.py — Agent 侧邮箱守护进程 v0.4 (风险修复)"""
import os, sys, json, time, signal, logging, argparse, subprocess, tempfile
from datetime import datetime, timezone, timedelta

DEFAULT_DATA_DIR = "/mnt/e/ai_tools/mail/store"
POLL_INTERVAL = 5
HEARTBEAT_INTERVAL = 60
LOG_DIR = "/mnt/e/ai_tools/mail/logs"
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

def now_iso():
    return datetime.now(TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+0800")

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
        self._watcher = None
        # {pid: {msg_id, sender, summary, proc, started_at}}
        self._running_procs = {}
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

    # ── 消息解析（兼容新旧格式） ──

    def _parse_message(self, msg: dict) -> dict:
        """
        统一解析新旧格式消息，返回规范化字典。
        新格式: {mailbus: {msg_id, envelope: {from, to, cc, priority, ...}}, payload: {type, version, body}}
        旧格式: {id, from, to, type, content, ...}
        """
        if 'mailbus' in msg and isinstance(msg['mailbus'], dict):
            return self._parse_envelope(msg)
        return self._parse_legacy(msg)

    def _parse_envelope(self, msg: dict) -> dict:
        mb = msg['mailbus']
        env = mb.get('envelope', {})
        payload = msg.get('payload', {})
        body = payload.get('body', {})
        # 提取预览文本（从 body 中智能提取）
        preview = self._extract_preview(payload.get('type', 'notice'), body)
        return {
            'id': mb.get('msg_id', ''),
            'from': env.get('from', ''),
            'to': env.get('to', ''),
            'cc': env.get('cc', []),
            'priority': env.get('priority', 'normal'),
            'type': payload.get('type', 'notice'),
            'version': payload.get('version', '1.0'),
            'body': body,
            'preview': preview,
            'created_at': env.get('created_at', ''),
            'thread_id': env.get('thread_id', ''),
            'reply_to': env.get('reply_to', ''),
        }

    def _parse_legacy(self, msg: dict) -> dict:
        content = msg.get('content', '')
        return {
            'id': msg.get('id', ''),
            'from': msg.get('from', ''),
            'to': msg.get('to', ''),
            'cc': [],
            'priority': msg.get('priority', 'normal'),
            'type': msg.get('type', 'notice'),
            'version': '1.0',
            'body': {'content': content, 'raw_type': msg.get('type', 'notice')},
            'preview': (content[:80] if isinstance(content, str) else str(content)[:80]).replace('\n', ' '),
            'created_at': msg.get('created_at', ''),
            'thread_id': '',
            'reply_to': '',
        }

    @staticmethod
    def _extract_preview(payload_type: str, body: dict) -> str:
        """根据 payload 类型从 body 提取有意义的预览文本"""
        if payload_type == 'design_review':
            t = body.get('title', '')
            s = body.get('status', '')
            return f"[设计评审] {t} (状态: {s})"[:120]
        elif payload_type == 'task_status':
            t = body.get('title', '')
            s = body.get('status', '')
            a = body.get('assignee', '?')
            return f"[任务] {t} → {a} (状态: {s})"[:120]
        elif payload_type == 'code_review':
            pu = body.get('pr_url', '')
            f = body.get('change_summary', {}).get('files_changed', '?')
            return f"[Code Review] PR: {pu} ({f} 文件变更)"[:120]
        elif payload_type == 'status_ack':
            ack_for = body.get('ack_for_msg_id', '')
            ack_st = body.get('ack_status', '')
            return f"[回执] 确认 {ack_for}: {ack_st}"[:120]
        # 兜底：从 body 取内容或返回空
        if isinstance(body, dict):
            return str(body.get('content', str(body)))[:80].replace('\n', ' ')
        return str(body)[:80].replace('\n', ' ')

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
        self.log.info(f"Mailbox Daemon v0.4 启动 (风险修复: write_json容错 + reply去唤醒) — agent={self.agent_name}")
        self.log.info(f"  inbox: {self.inbox_path}")
        self.log.info(f"  ack:   {self.ack_path}")
        if not os.path.exists(self.inbox_path):
            self.log.warning("inbox 尚不存在, 等待创建...")
        self._watcher = FileWatcher(self.inbox_path)
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, '_running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, '_running', False))
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
                except Exception as e:
                    self.log.error(f"循环异常: {e}", exc_info=True)
        finally:
            self._watcher.close()
            self.log.info("Mailbox Daemon 已停止")

    # ── 收信处理 ──

    def _process_inbox(self):
        inbox = read_json(self.inbox_path)
        if not inbox:
            return
        # 读取已 ack 的消息 ID 集合, 避免重复处理
        acked_ids = set()
        ack_data = read_json(self.ack_path, [])
        if isinstance(ack_data, dict):
            ack_data = [ack_data]
        for e in ack_data:
            if isinstance(e, dict) and e.get("action") == "ack":
                acked_ids.add(e.get("msg_id"))
        pending = [
            m for m in inbox.get("messages", [])
            if isinstance(m, dict)
            and m.get("status") == "pending"
            and m.get("id") not in acked_ids
        ]
        if not pending:
            return
        self.log.info(f"发现 {len(pending)} 条待处理消息")
        for msg in pending:
            self._handle_message(msg)

    def _handle_message(self, msg):
        # 统一解析（兼容新旧格式）
        parsed = self._parse_message(msg)
        msg_id = parsed['id']
        msg_type = parsed['type']
        priority = parsed['priority']
        from_ = parsed['from']
        preview = parsed['preview']
        body = parsed['body']
        self.log.info(f"  [{msg_type}] {msg_id} 来自 {from_}: {preview}")

        # Step 1: 自动 ack（告诉 mailbus "收到了, 正在处理"）
        self._auto_ack(msg_id)
        self.log.info(f"  已 ack")

        # Step 2: 处理 status_ack（回执确认，不唤醒 agent）
        if msg_type == 'status_ack':
            self._handle_status_ack(parsed)
            return

        # Step 3: 检测完成回执风暴 — 不触发 agent 递归
        body_text = ''
        if isinstance(body, dict):
            body_text = body.get('content', '') or str(body)
        elif isinstance(body, str):
            body_text = body
        if isinstance(body_text, str) and body_text.startswith("✅ 任务完成回执"):
            self.log.info(f"  完成回执，无需再唤醒 agent，标记 done")
            self._mark_done(msg_id, "完成回执，不递归")
            return

        # Step 4: 分流处理
        if self._needs_agent(msg_type, priority, parsed, from_=from_):
            self.log.info(f"  唤醒 agent (type={msg_type})")
            self._trigger_agent(msg_id, from_, preview)
        else:
            self.log.info(f"  无需唤醒 (type={msg_type})")
            self._mark_done(msg_id, "无需处理")

    def _handle_status_ack(self, parsed: dict):
        """处理 status_ack 类型消息：记录 ack 状态到对应消息"""
        body = parsed['body']
        ack_for = body.get('ack_for_msg_id', '')
        ack_status = body.get('ack_status', 'received')
        notes = body.get('notes', '')
        self.log.info(f"  收到回执: {ack_for} → {ack_status}{f' ({notes})' if notes else ''}")

        # 遍历所有 inbox 文件，找到原始消息并更新 ack 状态
        inbox_dir = os.path.join(self.data_dir, "inbox")
        updated = False
        if os.path.isdir(inbox_dir):
            for agent_dir in os.listdir(inbox_dir):
                inbox_file = os.path.join(inbox_dir, agent_dir, "inbox.json")
                inbox = read_json(inbox_file)
                if not inbox:
                    continue
                changed = False
                for m in inbox.get("messages", []):
                    if m.get("id") == ack_for:
                        m["ack_status"] = ack_status
                        if notes:
                            m["ack_notes"] = notes
                        m["ack_received_at"] = now_iso()
                        changed = True
                        updated = True
                        break
                if changed:
                    write_json(inbox_file, inbox)
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

    # ── Ack ──

    def _auto_ack(self, msg_id):
        ts = now_iso()
        ack = read_json(self.ack_path, [])
        if isinstance(ack, dict):
            ack = [ack]
        if any(e.get("msg_id") == msg_id and e.get("action") == "ack" for e in ack):
            return
        ack.append({"action": "ack", "msg_id": msg_id,
                     "agent": self.agent_name, "timestamp": ts})
        write_json(self.ack_path, ack)
        # 同步更新 inbox 中该消息的状态, 避免重复处理
        inbox = read_json(self.inbox_path)
        if inbox:
            for m in inbox.get("messages", []):
                if m.get("id") == msg_id and m.get("status") == "pending":
                    m["status"] = "acknowledged"
                    m["acknowledged_at"] = ts
                    inbox["has_unread"] = any(
                        mm.get("status") not in ("acknowledged", "archived")
                        for mm in inbox.get("messages", []))
                    write_json(self.inbox_path, inbox)
                    break

    def _mark_done(self, msg_id, note=""):
        """在 inbox 中将消息标记为 done"""
        inbox = read_json(self.inbox_path)
        if not inbox:
            return
        for m in inbox.get("messages", []):
            if m.get("id") == msg_id:
                m["state"] = "done"
                m["done_at"] = now_iso()
                if note:
                    m["done_note"] = note
                inbox["has_unread"] = any(
                    mm.get("status") not in ("acknowledged", "archived")
                    for mm in inbox.get("messages", []))
                write_json(self.inbox_path, inbox)
                break

    # ── CLI 唤醒 + 完成追踪 ──

    def _trigger_agent(self, msg_id, sender, summary):
        config = read_json(os.path.join(self.data_dir, "config.json"), {})
        agent_cfg = config.get("agents", {}).get(self.agent_name, {})
        atype = agent_cfg.get("type", "none")
        tmpl = config.get("agent_types", {}).get(atype, {}).get("push", "")
        if not tmpl:
            self.log.warning("未找到 CLI 模板, 跳过唤醒")
            self._mark_done(msg_id, "CLI 模板未配置")
            return

        cmd = tmpl.replace("PROFILE", agent_cfg.get("profile", "") or self.agent_name)
        cmd = cmd.replace("AGENT", agent_cfg.get("agent", "") or self.agent_name)
        models_map = config.get("agent_types", {}).get("models", {})
        agent_models = agent_cfg.get("models", [])
        if agent_models and agent_models[0] in models_map:
            mf = models_map[agent_models[0]].get(atype, "")
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
        cmd = cmd.replace("MSG", f"你有新的任务消息: {summary}")
        cmd = " ".join(cmd.split())
        self.log.info(f"  CLI: {cmd[:150]}...")

        # 构建环境变量 — 确保所有 CLI 在 PATH 中
        env = os.environ.copy()
        home = os.path.expanduser("~")
        extra_paths = [
            "/usr/local/bin", "/usr/bin", "/bin",
            f"{home}/.local/bin",
            f"{home}/.npm-global/bin",
            "/mnt/e/hermes-data/.hermes/hermes-agent/venv/bin",  # hermes
            "/mnt/e/ai_tools/opencode",                          # opencode
        ]
        existing_path = env.get("PATH", "")
        env["PATH"] = ":".join(p for p in extra_paths if os.path.isdir(p)) + ":" + existing_path

        # 从 .env 补充 API Key 等
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

        # 写临时脚本, 用 bash 执行（避免引号嵌套问题）
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
                "msg_id": msg_id,
                "sender": sender,
                "summary": summary,
                "proc": proc,
                "started_at": time.time(),
            }
            self.log.info(f"  agent 已唤醒 (PID: {proc.pid})")
        except Exception as e:
            self.log.error(f"  唤醒失败: {e}")
            self._send_completion_notice(msg_id, sender, "失败", f"Agent 唤醒失败: {e}")

    # ── 进程收割 + 完成回执 ──

    def _reap_processes(self):
        """检查已完成的 agent 进程, 发回执"""
        finished = []
        for pid, info in self._running_procs.items():
            proc = info["proc"]
            ret = proc.poll()
            if ret is not None:
                finished.append(pid)
                elapsed = time.time() - info["started_at"]
                self.log.info(f"  agent 进程完成 (PID: {pid}, 耗时: {elapsed:.0f}s, 返回码: {ret})")
                # 收集 stdout
                stdout = ""
                try:
                    out, _ = proc.communicate(timeout=5)
                    stdout = out.decode("utf-8", errors="replace").strip()[:500]
                except Exception:
                    pass
                # 发完成回执给原始发件人
                status = "完成" if ret == 0 else f"异常退出(code={ret})"
                self._send_completion_notice(
                    info["msg_id"], info["sender"],
                    status, stdout or None
                )
                self._mark_done(info["msg_id"], f"agent 已处理({status})")
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
                + (f"\n输出摘要:\n{detail[:300]}" if detail else "")
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


# ── CLI ──

def main():
    global LOG_DIR
    parser = argparse.ArgumentParser(description="Mailbox Daemon — Agent 侧邮箱守护进程")
    parser.add_argument("--agent", required=True, help="Agent 名称")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="mailbus store 目录")
    parser.add_argument("--daemon", action="store_true", help="后台运行")
    parser.add_argument("--log-dir", default="/mnt/e/ai_tools/mail/logs", help="日志目录")
    args = parser.parse_args()
    LOG_DIR = args.log_dir
    if args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"Mailbox Daemon 已启动 (PID: {pid})")
            sys.exit(0)
    MailboxDaemon(agent_name=args.agent, data_dir=args.data_dir).start()


if __name__ == "__main__":
    main()
