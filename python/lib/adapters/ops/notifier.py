"""M1 W1 外呼通知渠道：告警触达层（跨平台，零第三方依赖）。

背景：Wave 0-5 的告警只落 alerts.json + 管理员 inbox（「展示层有、触达层没有」，
2026-09 停摆 5 天无人知的根因之一）。本模块补上主动找到人的那一跳。

四渠道（config.json `notify.channels` 列表按序分发）：
- desktop：Windows 气泡通知（PowerShell NotifyIcon）/ Linux notify-send；
  无桌面环境（容器 / 无 DISPLAY）自动降级为 skipped。
- webhook：通用 JSON POST，内置 telegram / dingtalk / wecom / generic payload。
- smtp：邮件（MIMEText + TLS/SSL）。
- file：追加写 store 内 markdown 摘要（默认按日分文件）。

level 语义：critical / warn = 实时告警；digest = 每日摘要。
单渠道失败只计入返回值，不中断其他渠道。
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import smtplib
import subprocess
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from lib.infra.clock import now_dt
from lib.infra.utils import json_read

VALID_LEVELS = ("critical", "warn", "digest")

DEFAULT_DIGEST_DIR = "notify"


def notify_config(data_dir: str) -> dict:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    n = (cfg or {}).get("notify") or {}
    return n if isinstance(n, dict) else {}


def send_notification(data_dir: str, title: str, body: str, level: str = "warn") -> dict:
    """按 config.notify.channels 分发通知，返回 {channel_type: {ok, ...}}。"""
    level = level if level in VALID_LEVELS else "warn"
    results: dict = {}
    ncfg = notify_config(data_dir)
    if not ncfg.get("enabled", True):
        return {"skipped": {"ok": True, "reason": "notify disabled"}}
    channels = ncfg.get("channels") or []
    if not channels:
        return {"skipped": {"ok": True, "reason": "no notify channels configured"}}
    for idx, ch in enumerate(channels):
        ctype = str(ch.get("type") or "").strip()
        if ch.get("enabled") is False:
            results[f"{ctype}#{idx}"] = {"ok": True, "skipped": "channel disabled"}
            continue
        levels = ch.get("levels")
        # 默认：digest 渠道收 digest；实时渠道收 critical/warn
        if not levels:
            levels = ["digest"] if ctype in ("smtp", "file") else ["critical", "warn"]
        if level not in levels:
            results[f"{ctype}#{idx}"] = {"ok": True, "skipped": f"level {level} not in {levels}"}
            continue
        try:
            if ctype == "desktop":
                r = _send_desktop(title, body)
            elif ctype == "webhook":
                r = _send_webhook(ch, title, body, level)
            elif ctype == "smtp":
                r = _send_smtp(ch, title, body)
            elif ctype == "file":
                r = _send_file(ch, data_dir, title, body)
            else:
                r = {"ok": False, "error": f"unknown channel type: {ctype}"}
        except Exception as exc:  # 单渠道失败不得影响其他渠道
            r = {"ok": False, "error": str(exc)}
        results[f"{ctype}#{idx}"] = r
    return results


# ---------------------------------------------------------------- desktop

_PS_BALLOON = """Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.Visible = $true
$n.ShowBalloonTip(10000, '{title}', '{body}', [System.Windows.Forms.ToolTipIcon]::Warning)
Start-Sleep -Seconds 6
$n.Dispose()
"""


def _ps_quote(s: str) -> str:
    return s.replace("'", "''").replace("\r", " ").replace("\n", " ")


def _send_desktop(title: str, body: str) -> dict:
    if os.name == "nt" or os.environ.get("OS", "").lower().startswith("windows"):
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            return {"ok": False, "error": "powershell not found"}
        script = _PS_BALLOON.format(title=_ps_quote(title), body=_ps_quote(body))
        # fire-and-forget：气泡有自己的生命周期，不阻塞调用方（scan/scheduler）
        subprocess.Popen(
            [ps, "-NoProfile", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": True, "detail": "windows balloon"}
    # Linux / WSL：notify-send + DISPLAY
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return {"ok": False, "error": "no desktop session (DISPLAY unset)"}
    bin_path = shutil.which("notify-send")
    if not bin_path:
        return {"ok": False, "error": "notify-send not installed"}
    subprocess.run(
        [bin_path, "-u", "critical", "-t", "10000", title, body],
        timeout=10, check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "detail": "notify-send"}


# ---------------------------------------------------------------- webhook

def _post_json(url: str, payload: dict, timeout: int = 10) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return {"ok": 200 <= resp.status < 300, "status": resp.status}


def _dingtalk_signed_url(url: str, secret: str) -> str:
    ts = str(int(now_dt().timestamp() * 1000))
    digest = hmac.new(
        secret.encode("utf-8"), f"{ts}\n{secret}".encode("utf-8"), hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}timestamp={ts}&sign={sign}"


def _send_webhook(cfg: dict, title: str, body: str, level: str) -> dict:
    provider = str(cfg.get("provider") or "generic").strip().lower()
    url = str(cfg.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "webhook url missing"}
    text = f"【mailbus {level.upper()}】{title}\n{body}"
    if provider == "telegram":
        chat_id = str(cfg.get("chat_id") or "").strip()
        if not chat_id:
            return {"ok": False, "error": "telegram chat_id missing"}
        return _post_json(url, {"chat_id": chat_id, "text": text})
    if provider == "dingtalk":
        if cfg.get("secret"):
            url = _dingtalk_signed_url(url, str(cfg["secret"]))
        return _post_json(
            url, {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{body}"}},
        )
    if provider == "wecom":
        return _post_json(
            url, {"msgtype": "markdown", "markdown": {"content": text}},
        )
    return _post_json(
        url, {"source": "mailbus", "level": level, "title": title, "body": body},
    )


# ---------------------------------------------------------------- smtp

def _send_smtp(cfg: dict, title: str, body: str) -> dict:
    host = str(cfg.get("host") or "").strip()
    if not host:
        return {"ok": False, "error": "smtp host missing"}
    port = int(cfg.get("port") or 465)
    to_addrs = cfg.get("to") or []
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    if not to_addrs:
        return {"ok": False, "error": "smtp to missing"}
    sender = str(cfg.get("from") or cfg.get("username") or "mailbus@localhost")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = formataddr((str(Header("mailbus", "utf-8")), sender))
    msg["To"] = ", ".join(to_addrs)

    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    try:
        if cfg.get("username") and cfg.get("password"):
            if port != 465 and cfg.get("starttls", True):
                client.starttls()
            client.login(str(cfg["username"]), str(cfg["password"]))
        client.sendmail(sender, to_addrs, msg.as_string())
    finally:
        client.quit()
    return {"ok": True, "detail": f"mail to {len(to_addrs)}"}


# ---------------------------------------------------------------- file

def _send_file(cfg: dict, data_dir: str, title: str, body: str) -> dict:
    path = str(cfg.get("path") or "").strip()
    if not path:
        day = now_dt().strftime("%Y-%m-%d")
        path = os.path.join(DEFAULT_DIGEST_DIR, f"digest-{day}.md")
    if not os.path.isabs(path):
        path = os.path.join(data_dir, path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ts = now_dt().strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {ts} {title}\n\n{body}\n")
    return {"ok": True, "detail": path}
