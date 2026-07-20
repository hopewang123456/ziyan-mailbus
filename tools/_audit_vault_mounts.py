# -*- coding: utf-8 -*-
"""Audit all agent skill/memory mounts + OpenClaw container visibility."""
from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path

VAULT = Path(r"E:/Obsidian/Vaults")
AGENT = VAULT / "Agent"


def is_reparse(p: Path) -> bool:
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
        return attrs != -1 and bool(attrs & 0x400)
    except Exception:
        return False


def skill_count(p: Path) -> int:
    if not p.exists():
        return -1
    return sum(1 for _ in p.rglob("SKILL.md"))


def expand(p: str | None) -> str | None:
    if not p or p in ("null", "~", ""):
        return None
    p = os.path.expandvars(p.strip().strip('"').replace("/", "\\"))
    if p.startswith("~"):
        p = str(Path.home() / p[2:].lstrip("\\/"))
    return p


def parse_manifest(text: str) -> dict:
    out = {
        "id": None,
        "skills_path": None,
        "mem_path": None,
        "skills_home": None,
        "mem_home": None,
        "strategy": None,
    }
    section = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            section = line.rstrip()[:-1].strip()
            continue
        if line.startswith("id:"):
            out["id"] = line.split(":", 1)[1].strip().strip('"')
        if section == "skills" and line.strip().startswith("path:"):
            out["skills_path"] = line.split(":", 1)[1].strip().strip('"')
        if section == "memory" and line.strip().startswith("path:"):
            v = line.split(":", 1)[1].strip().strip('"')
            out["mem_path"] = None if v in ("null", "~", "") else v
        if section == "mount":
            key = line.strip().split(":", 1)[0]
            val = line.split(":", 1)[1].strip().strip('"') if ":" in line else ""
            if key == "agent_skills_home":
                out["skills_home"] = val
            elif key == "agent_memory_home":
                out["mem_home"] = None if val in ("null", "~", "") else val
            elif key == "strategy":
                out["strategy"] = val
    return out


def check_link(home: str | None, rel: str | None, label: str) -> tuple[str, str]:
    if not home or not rel:
        return "N/A", ""
    home_p = Path(expand(home) or "")
    want = (VAULT / rel.replace("/", "\\")).resolve()
    if not home_p.exists():
        return "FAIL-MISSING", str(home_p)
    if not is_reparse(home_p):
        return "FAIL-REALDIR", f"{home_p} count={skill_count(home_p)}"
    got = home_p.resolve()
    n = skill_count(home_p)
    nv = skill_count(want)
    if got != want:
        return "FAIL-TARGET", f"got={got} want={want} n={n}/{nv}"
    return "OK", f"SKILL.md={n} vault={nv}" if label == "skills" else f"-> {want}"


def main() -> int:
    print("=== MANIFEST AGENTS ===")
    fails = 0
    for d in sorted((AGENT / "configs").iterdir()):
        mf = d / "manifest.yaml"
        if not mf.exists():
            continue
        a = parse_manifest(mf.read_text(encoding="utf-8"))
        if a["strategy"] == "symlink":
            print(f"SKIP-WSL     {a['id']:16} (symlink strategy)")
            continue
        sk, sd = check_link(a["skills_home"], a["skills_path"], "skills")
        print(f"{sk:12} {a['id']:16} skills  {sd}")
        if sk.startswith("FAIL"):
            fails += 1
        if a["mem_home"] and a["mem_path"]:
            mk, md = check_link(a["mem_home"], a["mem_path"], "memory")
            print(f"{mk:12} {a['id']:16} memory  {md}")
            if mk.startswith("FAIL"):
                fails += 1

    print("\n=== HERMES PROFILES (skills) ===")
    hermes = Path(r"E:/hermes-data/.hermes/profiles")
    if hermes.exists():
        for p in sorted(hermes.iterdir()):
            if not p.is_dir():
                continue
            sk = p / "skills"
            if not sk.exists():
                print(f"FAIL-MISSING {p.name:16} skills")
                fails += 1
                continue
            if not is_reparse(sk):
                print(f"FAIL-REALDIR {p.name:16} skills count={skill_count(sk)}")
                fails += 1
                continue
            print(f"OK           {p.name:16} skills -> {sk.resolve()} SKILL.md={skill_count(sk)}")

    print("\n=== OPENCLAW HOST vs VAULT ===")
    vault_oc = AGENT / "skills/library/openclaw"
    for label, path in [
        ("vault", vault_oc),
        ("qclaw", Path.home() / ".qclaw/skills"),
        ("space", Path(r"E:/ai_tools/openclaw_space/skills")),
    ]:
        print(f"{label:8} reparse={is_reparse(path)} resolve={path.resolve() if path.exists() else None} SKILL.md={skill_count(path)}")

    print("\n=== OPENCLAW DOCKER ===")
    try:
        r = subprocess.run(
            [
                "wsl",
                "bash",
                "-c",
                "docker exec docker-agents-openclaw-1 sh -c '"
                "echo ws_link=$(readlink /workspace/skills 2>/dev/null); "
                "echo ws_count=$(find /workspace/skills -name SKILL.md 2>/dev/null | wc -l); "
                "echo mnt_count=$(find /mnt/e/Obsidian/Vaults/Agent/skills/library/openclaw -name SKILL.md 2>/dev/null | wc -l); "
                "echo ws_ls=$(ls /workspace/skills 2>&1 | head -5 | tr \"\\n\" \";\"); "
                "echo mnt_ls=$(ls /mnt/e/Obsidian/Vaults/Agent/skills/library/openclaw 2>&1 | head -5 | tr \"\\n\" \";\"); "
                "grep workspace/skills /proc/mounts | head -3"
                "'",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        print(r.stdout)
        if r.stderr:
            print("stderr:", r.stderr[:500])
    except Exception as exc:
        print("docker probe failed:", exc)

    print(f"\nFAILS={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
