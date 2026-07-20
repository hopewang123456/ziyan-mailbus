# -*- coding: utf-8 -*-
import json
from pathlib import Path

paths = [
    Path(r"E:/ai_tools/openclaw_space/data/.openclaw/openclaw.json"),
    Path(r"E:/ai_tools/openclaw_space/data/.openclaw-xiaoqi/openclaw.json"),
    Path(r"E:/ai_tools/openclaw_space/data/.openclaw-yige/openclaw.json"),
]
keys = ("skill", "workspace", "agent", "path", "dir", "root")
for p in paths:
    print("====", p)
    if not p.exists():
        print("MISSING")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print("top keys:", list(d.keys())[:30])

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if any(t in k.lower() for t in keys):
                    if isinstance(v, (str, int, bool)) or v is None:
                        print(f"  {path} = {v}")
                    elif isinstance(v, list) and len(v) < 20:
                        print(f"  {path} = {v}")
                    else:
                        print(f"  {path} = <{type(v).__name__}>")
                walk(v, path)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:50]):
                walk(v, f"{prefix}[{i}]")

    walk(d)
