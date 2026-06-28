#!/usr/bin/env python3
"""Internal LLM 部署检查与初始化。

用法:
  python tools/tools/ops/setup-internal-llm.py --data-dir store
  python tools/tools/ops/setup-internal-llm.py --pull-model --rebuild-rag --dry-run-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import fcntl  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["fcntl"] = MagicMock()

import contextlib
import lib.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.internal_llm.ollama_ensure import ensure_from_config
from lib.internal_llm.planner_llm import dry_run, load_llm_config
from lib.internal_llm.probe import probe_all, probe_provider
from lib.internal_llm.rag.index import index_info, rebuild_index


def _ollama_bin() -> str:
    return os.environ.get("OLLAMA_BIN", "ollama")


def pull_model(model: str) -> bool:
    print(f"pulling ollama model: {model}")
    try:
        subprocess.run([_ollama_bin(), "pull", model], check=True, timeout=600)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"pull failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="mailbus internal LLM setup")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--ensure-ollama", action="store_true", help="start host Ollama + pull model if missing")
    ap.add_argument("--pull-model", action="store_true", help="ollama pull configured local model")
    ap.add_argument("--rebuild-rag", action="store_true", help="rebuild RAG sqlite index")
    ap.add_argument("--rebuild-rag-if-empty", action="store_true", help="rebuild RAG when chunk count is 0")
    ap.add_argument("--dry-run-test", action="store_true", help="run planner dry-run")
    ap.add_argument("--json", action="store_true", help="output health as JSON only")
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    cfg = load_llm_config(data_dir)

    if not cfg:
        print("mailbus_internal_llm not configured in config.json", file=sys.stderr)
        return 1

    if args.ensure_ollama:
        ensured = ensure_from_config(data_dir)
        if not ensured.get("skipped") and not ensured.get("ok"):
            print(f"ensure-ollama failed: {ensured.get('error')}", file=sys.stderr)
            return 1

    health = probe_all(data_dir)
    if args.json and not any((args.pull_model, args.rebuild_rag, args.rebuild_rag_if_empty, args.dry_run_test)):
        print(json.dumps(health, ensure_ascii=False, indent=2))
        return 0 if health.get("ready") else 2

    print("=== mailbus Internal LLM Setup ===")
    print(f"enabled: {cfg.get('enabled')}")
    print(f"priority: {cfg.get('provider_priority')} (local 优先 → remote fallback)")
    for name in cfg.get("provider_priority") or []:
        pc = (cfg.get("providers") or {}).get(name) or {}
        if pc.get("base_url"):
            print(f"  [{name}] {pc.get('kind')} @ {pc.get('base_url')} model={pc.get('model')}")
    print("")
    for p in health.get("providers") or []:
        flag = "OK" if p.get("ok") else "FAIL"
        extra = ""
        if p.get("kind") == "ollama" and p.get("ok") and not p.get("model_available"):
            extra = " (model not pulled)"
        print(f"  [{flag}] {p.get('name')}: {p.get('kind')} {extra}{(' — ' + p.get('error')) if p.get('error') else ''}")

    rag = index_info(data_dir, cfg) if (cfg.get("rag") or {}).get("enabled", True) else {}
    if rag:
        print(f"RAG: {rag.get('chunks', 0)} chunks @ {rag.get('path', '?')}")

    if args.pull_model:
        local = (cfg.get("providers") or {}).get("local") or {}
        model = local.get("model")
        if local.get("kind") == "ollama" and model:
            if not pull_model(model):
                return 1
            health = probe_all(data_dir)
        else:
            print("skip pull: local provider is not ollama")

    rag_cfg = cfg.get("rag") or {}
    rag_on_start = bool((rag_cfg.get("index") or {}).get("rebuild_on_start"))
    need_rag = args.rebuild_rag or (
        args.rebuild_rag_if_empty and cfg.get("enabled") and (rag or {}).get("chunks", 0) == 0
    ) or (rag_on_start and cfg.get("enabled"))

    if need_rag:
        if not cfg.get("enabled"):
            print("skip RAG: internal_llm disabled")
        else:
            n = rebuild_index(data_dir, cfg)
            print(f"RAG rebuilt: {n} chunks")
            rag = index_info(data_dir, cfg)

    if args.dry_run_test:
        if not cfg.get("enabled"):
            print("skip dry-run: internal_llm disabled")
        elif not health.get("ready"):
            print("skip dry-run: no healthy provider", file=sys.stderr)
            return 2
        else:
            out = dry_run({
                "protocol_version": "mailbus-a2a/1",
                "task_id": "setup-dry-run",
                "intent": "评估 Redis 缓存方案是否适合 mailbus 会话层",
                "initiator": "human",
                "mode": "auto",
                "tier": "M",
                "task_type": "custom",
            }, data_dir=data_dir)
            chain = [x.get("role_type") for x in (out.get("planned_chain") or [])]
            print(f"dry-run OK: chain={chain} provider={out.get('plan_meta', {}).get('provider_used')}")

    if not health.get("ready"):
        print("\n部署未完成。建议:", file=sys.stderr)
        local = (cfg.get("providers") or {}).get("local") or {}
        if local.get("kind") == "ollama":
            print(f"  1. 宿主机启动官方 Ollama（托盘或 ollama serve）", file=sys.stderr)
            print(f"  2. 拉模型: ollama pull {local.get('model')}", file=sys.stderr)
            print(f"  3. Docker 内已设 MAILBUS_OLLAMA_BASE_URL={local.get('base_url')}", file=sys.stderr)
            print(f"  4. 重跑: python tools/tools/ops/setup-internal-llm.py --pull-model --rebuild-rag --dry-run-test", file=sys.stderr)
        remote = (cfg.get("providers") or {}).get("remote") or {}
        env_key = remote.get("api_key_env") or "MAILBUS_INTERNAL_LLM_API_KEY"
        print(f"  5. remote fallback: 设置 {env_key}（见 store/config/internal-llm.env.example）", file=sys.stderr)
        return 2

    print(f"\nInternal LLM ready (active={health.get('active_provider')}, fallback_mode={health.get('fallback_mode')}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
