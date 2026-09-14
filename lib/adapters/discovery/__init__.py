"""Discovery source implementations (Ports & Adapters)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from lib.domain.types import DiscoveredAgent
from lib.interfaces.discovery import DiscoverySource


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
            ("CODEX_WORKSPACE", "codex"),
            ("CODEX_REVIEW_WORKSPACE", "codex"),
            ("CODEX_HOME", "codex"),
            ("DSH_WORKSPACE", "dsh"),
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
    """本机常见家目录 + 显式配置/环境；不硬猜 ai_tools/Agent 布局。"""

    def scan(self) -> Sequence[DiscoveredAgent]:
        home = Path.home()
        candidates: list[tuple[Path, str]] = [
            (home / ".openclaw", "openclaw"),
            (home / ".hermes", "hermes"),
            (home / ".codex", "codex"),
            (home / ".claude", "claude_code"),
            (Path(os.environ.get("USERPROFILE", str(home))) / ".codex", "codex"),
        ]
        # 可选：MAILBUS_DISCOVERY_DIRS=path1;path2（framework 由末级目录名猜测）
        extra = (os.environ.get("MAILBUS_DISCOVERY_DIRS") or "").strip()
        if extra:
            fw_guess = {
                "openclaw_space": "openclaw",  # legacy folder name if user lists it
                "openclaw": "openclaw",
                "opencode": "opencode",
                "codex": "codex",
                "hermes": "hermes",
                "dsh": "dsh",
                ".claude": "claude_code",
                "claude": "claude_code",
            }
            for part in extra.replace(",", ";").split(";"):
                p = Path(part.strip()).expanduser()
                if not str(p):
                    continue
                name = p.name.lower()
                fw = fw_guess.get(name, name.replace("-", "_") or "unknown")
                candidates.append((p, fw))
        # store frameworks.*.root_path（已配置的安装根）
        try:
            from lib.infra.constants import MAILBUS_ROOT

            cfg_path = Path(os.environ.get("MAILBUS_DATA") or MAILBUS_ROOT / "store") / "config.json"
            if cfg_path.is_file():
                import json

                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                fws = cfg.get("frameworks") if isinstance(cfg.get("frameworks"), dict) else {}
                for fw_id, block in fws.items():
                    if not isinstance(block, dict):
                        continue
                    root = str(block.get("root_path") or "").strip()
                    if root:
                        candidates.append((Path(root), str(fw_id)))
        except Exception:
            pass

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


def _compose_service_hints() -> dict[str, str]:
    """从 store/config.json agents 的 docker.compose_service 推导容器名→framework。"""
    import json

    hints: dict[str, str] = {}
    data_dir = os.environ.get("MAILBUS_DATA") or os.environ.get("DATA_DIR") or ""
    if not data_dir:
        return hints
    cfg_path = os.path.join(data_dir, "config.json")
    try:
        if not os.path.isfile(cfg_path):
            return hints
        cfg = json.load(open(cfg_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return hints
    for aid, ac in (cfg.get("agents") or {}).items():
        svc = (ac.get("docker") or {}).get("compose_service") or (ac.get("docker") or {}).get("service")
        if svc:
            hints[str(svc)] = ac.get("type") or "hermes_profile"
    return hints


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
                "codex": "codex",
                "codex-web": "codex",
                "codex-review": "codex",
                "opencode": "opencode",
                "agentmemory": "agentmemory",
                "iii-engine": "agentmemory",
            }
            hints.update(_compose_service_hints())
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
