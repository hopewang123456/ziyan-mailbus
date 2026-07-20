#!/usr/bin/env python3
"""Expose Windows Ollama (127.0.0.1:11434) on WSL 0.0.0.0:11434 for Docker mailbus.

Docker-in-WSL cannot reach Windows localhost directly. This proxy forwards HTTP
to Windows via curl.exe, which can access the host Ollama API.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CURL = os.environ.get("OLLAMA_WSL_PROXY_CURL", "/mnt/c/Windows/System32/curl.exe")
TARGET = os.environ.get("OLLAMA_WSL_PROXY_TARGET", "http://127.0.0.1:11434")
TIMEOUT = os.environ.get("OLLAMA_WSL_PROXY_TIMEOUT", "120")
SKIP_HEADERS = frozenset({"host", "content-length", "connection", "keep-alive", "transfer-encoding"})


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
        cmd = [CURL, "-sS", "--max-time", TIMEOUT, "-w", "\n%{http_code}", "-X", method]
        for key, val in self.headers.items():
            if key.lower() in SKIP_HEADERS:
                continue
            cmd += ["-H", f"{key}: {val}"]
        cmd.append(f"{TARGET}{self.path}")
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
    ap = argparse.ArgumentParser(description="WSL Ollama proxy for Docker mailbus")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=11434)
    args = ap.parse_args()
    if not os.path.isfile(CURL):
        print(f"curl.exe not found: {CURL}", file=sys.stderr)
        return 2
    ok, _ = subprocess.run(
        [CURL, "-sf", "--max-time", "5", f"{TARGET}/api/tags"],
        capture_output=True,
        check=False,
    ).returncode, None
    if ok != 0:
        print(f"Windows Ollama unreachable at {TARGET}", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer((args.host, args.port), OllamaProxyHandler)
    print(f"[ollama-wsl-proxy] listening {args.host}:{args.port} -> {TARGET}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
