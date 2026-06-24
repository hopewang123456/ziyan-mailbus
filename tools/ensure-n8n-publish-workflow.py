#!/usr/bin/env python3
"""确保 n8n mailbus-multi-publish workflow 已导入并 Activate。

最优策略：
  1. WSL Docker 内探测/重启 n8n（mail docker-compose.n8n.yml）
  2. REST 导入或更新 workflow
  3. Activate + 写 N8N_PUBLISH_WEBHOOK_URL（sync-n8n-url）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.n8n.url_resolve import find_working_n8n_base_url
from lib.utils import configure_stdio_utf8

configure_stdio_utf8()

WORKFLOW_PATH = os.path.join(ROOT, "external-tools", "n8n", "mailbus-multi-publish.workflow.json")
WORKFLOW_NAME = "mailbus-multi-publish"
COMPOSE = os.path.join(ROOT, "docker-agents", "docker-compose.n8n.yml")


def _wsl_bash(script: str, *, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        ["wsl", "-e", "bash", "-lc", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=ROOT,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def ensure_n8n_container(*, restart: bool = False) -> bool:
    """确保 mailbus n8n compose 栈运行且端口可访问。"""
    if restart:
        rc, out = _wsl_bash(
            f"cd /mnt/e/ai_tools/mail/docker-agents && docker compose -f docker-compose.n8n.yml up -d 2>&1",
            timeout=180,
        )
        if rc != 0 and "error" in out.lower():
            print(f"[ensure-n8n] compose up warning: {out[:400]}")

    base = None
    for attempt in range(18):
        base = find_working_n8n_base_url(retries=1, pause=0)
        if base:
            break
        # 也试 WSL 内 localhost
        rc, out = _wsl_bash(
            "curl -sf --connect-timeout 2 http://127.0.0.1:5678/ >/dev/null && echo ok || echo fail",
            timeout=15,
        )
        if "ok" in out:
            base = "http://127.0.0.1:5678"
            break
        time.sleep(3)

    if not base:
        print("[ensure-n8n] n8n 不可达。WSL: bash docker-agents/start-n8n.sh")
        return False
    print(f"[ensure-n8n] n8n reachable: {base}")
    return True


def _api_request(base: str, path: str, *, method: str = "GET", body: dict | None = None, timeout: float = 15) -> tuple[int, dict | str]:
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw


def _import_via_docker_exec() -> bool:
    """容器内 n8n CLI 导入（数组格式）。"""
    wsl_script = "/mnt/e/ai_tools/mail/docker-agents/ensure-n8n-workflow.sh"
    rc, out = _wsl_bash(f"bash {wsl_script}", timeout=120)
    print(out[:1200])
    return rc == 0


def _find_workflow_id(base: str) -> str | None:
    code, data = _api_request(base, "/api/v1/workflows")
    if code != 200 or not isinstance(data, dict):
        # 旧版 REST
        code, data = _api_request(base, "/rest/workflows")
    items = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
    if not isinstance(items, list):
        return None
    for wf in items:
        if (wf.get("name") or "") == WORKFLOW_NAME:
            return str(wf.get("id") or "")
    return None


def _activate_workflow(base: str, wf_id: str) -> bool:
    for path, body in (
        (f"/api/v1/workflows/{wf_id}/activate", None),
        (f"/api/v1/workflows/{wf_id}", {"active": True}),
        (f"/rest/workflows/{wf_id}", {"active": True}),
    ):
        method = "POST" if body is None else "PATCH"
        code, resp = _api_request(base, path, method=method, body=body)
        if code in (200, 201, 204):
            print(f"[ensure-n8n] activated workflow {wf_id} via {path}")
            return True
        if code == 401:
            break
    return False


def probe_webhook(base: str) -> bool:
    url = f"{base.rstrip('/')}/webhook/mailbus-multi-publish"
    payload = json.dumps({
        "task_id": "ensure-probe",
        "content_id": "ensure-probe",
        "platforms": ["douyin"],
        "assets": [],
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode()[:200]
        print(f"[ensure-n8n] webhook OK {resp.status}: {body[:120]}")
        return resp.status < 400
    except urllib.error.HTTPError as exc:
        print(f"[ensure-n8n] webhook HTTP {exc.code}: {exc.read().decode()[:120]}")
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[ensure-n8n] webhook fail: {exc}")
        return False


def sync_env_webhook(base: str) -> None:
    import importlib.util
    import re

    def set_key(path: str, key: str, value: str) -> bool:
        if not os.path.isfile(path):
            return False
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        pat = re.compile(rf"^\s*{re.escape(key)}=")
        found = False
        out: list[str] = []
        for line in lines:
            if pat.match(line):
                found = True
                out.append(f"{key}={value}\n")
            else:
                out.append(line)
        if not found:
            out.append(f"{key}={value}\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)
        return True

    webhook = f"{base.rstrip('/')}/webhook/mailbus-multi-publish"
    for rel in (".env", os.path.join("docker-agents", ".env")):
        path = os.path.join(ROOT, rel)
        if set_key(path, "N8N_PUBLISH_WEBHOOK_URL", webhook):
            print(f"[ensure-n8n] {rel} -> {webhook}")
    os.environ["N8N_PUBLISH_WEBHOOK_URL"] = webhook


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restart", action="store_true", help="docker compose up -d n8n")
    ap.add_argument("--skip-import", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(WORKFLOW_PATH):
        print(f"missing {WORKFLOW_PATH}", file=sys.stderr)
        return 1

    if not ensure_n8n_container(restart=args.restart):
        return 1

    base = find_working_n8n_base_url(retries=3, pause=2)
    if not base:
        rc, out = _wsl_bash("hostname -I | awk '{print $1}'", timeout=10)
        wsl_ip = (out or "").strip().split()[0] if out.strip() else ""
        if wsl_ip:
            candidate = f"http://{wsl_ip}:5678"
            try:
                urllib.request.urlopen(f"{candidate}/", timeout=5)
                base = candidate
            except (urllib.error.URLError, TimeoutError, OSError):
                pass

    if not base:
        return 1

    if not args.skip_import:
        if not _import_via_docker_exec():
            print("[ensure-n8n] ensure script failed, trying reset ...", file=sys.stderr)
            rc, out = _wsl_bash("bash /mnt/e/ai_tools/mail/docker-agents/reset-n8n-workflow.sh", timeout=180)
            print(out[:1200])
            if rc != 0:
                return 1
        time.sleep(2)

    wf_id = _find_workflow_id(base)
    if wf_id:
        _activate_workflow(base, wf_id)

    sync_env_webhook(base)

    ok = probe_webhook(base)
    if not ok:
        # 从 Windows 再试一次 resolved URL
        from lib.env_bootstrap import load_mailbus_env
        load_mailbus_env()
        url = os.environ.get("N8N_PUBLISH_WEBHOOK_URL", "")
        if url:
            from lib.drill.video_publish import probe_n8n_webhook
            probe = probe_n8n_webhook(url)
            ok = probe.get("ok", False)
            print(f"[ensure-n8n] probe via env: {probe}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
