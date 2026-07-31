"""Discovery source implementations (Ports & Adapters)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from lib.domain.types import DiscoveredAgent
from lib.ports.discovery import DiscoverySource


def _which(name: str) -> str | None:
    return shutil.which(name) or shutil.which(name + ".exe")


def _dir_exists(p: str | None) -> bool:
    return bool(p) and Path(p).expanduser().exists()


def _hit_to_discovered(hit: dict[str, Any]) -> DiscoveredAgent:
    path = str(hit.get("path") or hit.get("container") or "")
    fw = str(hit.get("framework") or "")
    src = str(hit.get("source") or "")
    meta = {k: str(v) for k, v in hit.items() if k not in ("path", "framework", "source", "enabled")}
    agent_id = str(hit.get("container") or Path(path).name or fw or "unknown")
    return DiscoveredAgent(
        agent_id=agent_id,
        framework=fw,
        source=src,
        home_path=path if src != "docker" else "",
        binary_path="",
        meta=meta,
    )


class EnvDiscoverySource:
    def scan(self) -> Sequence[DiscoveredAgent]:
        out: list[dict[str, Any]] = []
        mapping = [
            ("OPENCLAW_WORKSPACE", "openclaw"),
            ("HERMES_DATA", "hermes"),
            ("OPENCODE_ROOT", "opencode"),
            ("LINGXIAO_WORKSPACE", "codex"),
            ("LINGJIAN_WORKSPACE", "codex"),
            ("CODEX_HOME", "codex"),
        ]
        for env_key, fw in mapping:
            val = (os.environ.get(env_key) or "").strip()
            if _dir_exists(val):
                out.append({
                    "source": "env",
                    "env": env_key,
                    "path": val,
                    "framework": fw,
                    "enabled": False,
                })
        return [_hit_to_discovered(h) for h in out]


class DirDiscoverySource:
    def scan(self) -> Sequence[DiscoveredAgent]:
        home = Path.home()
        candidates = [
            (home / ".openclaw", "openclaw"),
            (home / "openclaw_space", "openclaw"),
            (home / ".hermes", "hermes"),
            (home / ".codex", "codex"),
            (home / ".claude", "claude_code"),
            (Path(os.environ.get("USERPROFILE", str(home))) / ".codex", "codex"),
        ]
        for drive in ("E:", "C:"):
            candidates.extend([
                (Path(f"{drive}/ai_tools/openclaw_space"), "openclaw"),
                (Path(f"{drive}/hermes-data/.hermes"), "hermes"),
                (Path(f"{drive}/ai_tools/opencode"), "opencode"),
                (Path(f"{drive}/ai_tools/lingxiao"), "codex"),
            ])
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path, fw in candidates:
            key = str(path)
            if key in seen:
                continue
            if path.exists():
                seen.add(key)
                out.append({
                    "source": "default_dir",
                    "path": key,
                    "framework": fw,
                    "enabled": False,
                })
        return [_hit_to_discovered(h) for h in out]


class DockerDiscoverySource:
    def scan(self) -> Sequence[DiscoveredAgent]:
        docker = _which("docker")
        if not docker:
            return []
        out: list[dict[str, Any]] = []
        try:
            r = subprocess.run(
                [docker, "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode != 0:
                return []
            hints = {
                "openclaw": "openclaw",
                "hermes": "hermes",
                "lingxiao": "codex",
                "lingjian": "codex",
                "dali": "opencode",
                "opencode": "opencode",
                "agentmemory": "agentmemory",
                "iii-engine": "agentmemory",
            }
            for line in (r.stdout or "").splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name, image = parts[0], parts[1]
                fw = None
                low = (name + " " + image).lower()
                for needle, fwv in hints.items():
                    if needle in low:
                        fw = fwv
                        break
                if fw:
                    out.append({
                        "source": "docker",
                        "container": name,
                        "image": image,
                        "status": parts[2] if len(parts) > 2 else "",
                        "framework": fw,
                        "enabled": False,
                    })
        except Exception:
            return []
        return [_hit_to_discovered(h) for h in out]


def build_default_sources() -> list[DiscoverySource]:
    return [EnvDiscoverySource(), DirDiscoverySource(), DockerDiscoverySource()]
