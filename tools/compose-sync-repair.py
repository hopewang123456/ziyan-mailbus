#!/usr/bin/env python3
"""同步 Compose Override — 从 transport registry 重新生成 docker-compose.override.yml。"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.adapters.config.compose_registry import sync_compose_override

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docker_dir = os.path.join(root, "docker-agents")
    if not os.path.isdir(docker_dir):
        print(f"ERROR: {docker_dir} not found")
        return 1

    print("Syncing compose override from transport registry...")
    store = os.environ.get("DATA_DIR") or os.environ.get("MAILBUS_DATA_DIR") or os.path.join(root, "store")
    store = os.path.abspath(store)
    print(f"  store: {store}")
    print(f"  docker_dir: {docker_dir}")

    try:
        sync_compose_override(docker_dir=docker_dir, data_dir=store)
        print("COMPOSE OVERRIDE SYNCED")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
