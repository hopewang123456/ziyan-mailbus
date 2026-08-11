#!/usr/bin/env python3
"""Expose Windows Ollama on WSL for Docker mailbus.

Listen defaults come from config/services/ollama.json (wsl.proxy).
Forwards HTTP to Windows via curl.exe (host Ollama API).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CURL = os.environ.get("OLLAMA_WSL_PROXY_CURL", "/mnt/c/Windows/System32/curl.exe")
TIMEOUT = os.environ.get("OLLAMA_WSL_PROXY_TIMEOUT", "120")
SKIP_HEADERS = frozenset(
    {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "proxy-connection"}
)
TARGET = os.environ.get("OLLAMA_WSL_PROXY_TARGET", "http://127.0.0.1:11434")


def _default_listen_and_target() -> tuple[str, int, str]:
    """Prefer config/services/ollama.json; fall back to env / hardcoded."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from lib.adapters.ops.service_registry import ollama_proxy_listen

        return ollama_proxy_listen()
    except Exception:
        host = "0.0.0.0"
        port = int(os.environ.get("OLLAMA_WSL_PROXY_PORT", "11435"))
        target = os.environ.get("OLLAMA_WSL_PROXY_TARGET", "http://127.0.0.1:11434").rstrip("/")
        return host, port, target


class OllamaProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def do_DELETE(self) -> None:
        self._proxy("DELETE")

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        target = os.environ.get("OLLAMA_WSL_PROXY_TARGET", TARGET).rstrip("/")
        cmd = [
            CURL,
            "-sS",
            "--noproxy",
            "*",
            "--max-time",
            TIMEOUT,
            "-w",
            "\n%{http_code}",
            "-X",
            method,
        ]
        for key, val in self.headers.items():
            if key.lower() in SKIP_HEADERS:
                continue
            cmd += ["-H", f"{key}: {val}"]
        if body:
            cmd += ["--data-binary", "@-"]
        cmd.append(f"{target}{self.path}")
        try:
            proc = subprocess.run(
                cmd,
                input=body if body else None,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            self.send_error(502, f"curl exec failed: {exc}")
            return
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b"curl failed").strip()
            self.send_error(502, err.decode("utf-8", "replace")[:500])
            return
        raw = proc.stdout
        if b"\n" not in raw:
            self.send_error(502, "invalid curl response")
            return
        payload, status_line = raw.rsplit(b"\n", 1)
        try:
            status = int(status_line.decode().strip() or "502")
        except ValueError:
            self.send_error(502, "invalid status from curl")
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[ollama-wsl-proxy] " + (fmt % args) + "\n")


def main() -> int:
    listen_host, listen_port, target = _default_listen_and_target()
    target = os.environ.get("OLLAMA_WSL_PROXY_TARGET", target).rstrip("/")
    ap = argparse.ArgumentParser(description="WSL Ollama proxy for Docker mailbus")
    ap.add_argument("--host", default=listen_host)
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OLLAMA_WSL_PROXY_PORT", listen_port)),
    )
    args = ap.parse_args()
    if not os.path.isfile(CURL):
        print(f"curl.exe not found: {CURL}", file=sys.stderr)
        return 2
    ok = subprocess.run(
        [CURL, "-sf", "--noproxy", "*", "--max-time", "5", f"{target}/api/tags"],
        capture_output=True,
        check=False,
    ).returncode
    if ok != 0:
        print(f"Windows Ollama unreachable at {target}", file=sys.stderr)
        return 1
    os.environ["OLLAMA_WSL_PROXY_TARGET"] = target
    server = ThreadingHTTPServer((args.host, args.port), OllamaProxyHandler)
    print(f"[ollama-wsl-proxy] listening {args.host}:{args.port} -> {target}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
