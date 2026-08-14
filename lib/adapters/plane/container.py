"""Container plane — docker compose up/down/ps for framework services."""
from __future__ import annotations

import os
import time
from typing import Any

from lib.domain.types import PlaneActionResult, ProbeResult
from lib.infra.utils import json_read

# framework_id → compose service name(s)
FRAMEWORK_COMPOSE_SERVICES: dict[str, list[str]] = {
    "hermes": ["hermes"],
    "hermes_profile": ["hermes"],
    "openclaw": ["openclaw"],
    "codex": ["codex-web", "codex-review"],
    "opencode": ["opencode"],
    "agentmemory": ["iii-engine", "agentmemory"],
}


def _compose_services_for(framework: str, entry: dict) -> list[str]:
    raw = entry.get("compose_services") or entry.get("compose_service")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list) and raw:
        return [str(x).strip() for x in raw if str(x).strip()]
    return list(FRAMEWORK_COMPOSE_SERVICES.get(framework, []))


def _run_compose(*args: str, timeout: int = 180) -> tuple[int, str]:
    from lib.adapters.plane.platform_runner import compose_cmd, run

    argv = compose_cmd(*args)
    try:
        r = run(argv, timeout=timeout)
        detail = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
        return r.returncode, detail[:500]
    except Exception as exc:
        return 1, str(exc)


class ContainerPlane:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def _entry(self, framework: str) -> dict[str, Any]:
        cfg = json_read(os.path.join(self.data_dir, "config.json"), {})
        return dict((cfg.get("frameworks") or {}).get(framework) or {})

    def start_framework(self, framework: str) -> PlaneActionResult:
        from lib.adapters.plane.platform_runner import ensure_docker

        if not ensure_docker(30):
            return PlaneActionResult(ok=False, framework=framework, detail="docker_not_ready")
        entry = self._entry(framework)
        services = _compose_services_for(framework, entry)
        if not services:
            # no compose mapping — treat as ok noop (host-only frameworks)
            return PlaneActionResult(ok=True, framework=framework, detail="no_compose_services")
        last_detail = ""
        for attempt in range(1, 4):
            code, detail = _run_compose("up", "-d", "--no-build", *services, timeout=180)
            last_detail = detail or f"attempt={attempt}"
            if code == 0:
                probe = self.probe_framework(framework)
                if probe.ok:
                    return PlaneActionResult(ok=True, framework=framework, detail=f"up:{','.join(services)}")
            time.sleep(2)
        return PlaneActionResult(ok=False, framework=framework, detail=last_detail or "compose_up_failed")

    def stop_framework(self, framework: str) -> PlaneActionResult:
        entry = self._entry(framework)
        services = _compose_services_for(framework, entry)
        if not services:
            return PlaneActionResult(ok=True, framework=framework, detail="no_compose_services")
        code, detail = _run_compose("stop", *services, timeout=120)
        return PlaneActionResult(
            ok=code == 0,
            framework=framework,
            detail=detail or ("stopped" if code == 0 else "compose_stop_failed"),
        )

    def probe_framework(self, framework: str) -> ProbeResult:
        entry = self._entry(framework)
        health_url = str(entry.get("health_url") or "").strip()
        if health_url:
            from lib.adapters.plane.probe import probe_http

            ok = probe_http(health_url)
            return ProbeResult(ok=ok, agent_id=framework, detail=health_url if ok else "health_fail")
        services = _compose_services_for(framework, entry)
        if not services:
            return ProbeResult(ok=True, agent_id=framework, detail="no_services")
        # container running check via docker compose ps
        code, detail = _run_compose("ps", "--status", "running", *services, timeout=30)
        ok = code == 0 and any(s in detail for s in services)
        # compose ps output formats vary — also try docker inspect via platform
        if not ok:
            from lib.adapters.frameworks.registry import container_for_service
            from lib.adapters.plane.platform_runner import docker_container_running

            running_any = False
            for svc in services:
                cname = container_for_service(svc)
                if docker_container_running(cname):
                    running_any = True
                    break
            ok = running_any
        return ProbeResult(ok=ok, agent_id=framework, detail=detail[:200] if detail else ("up" if ok else "down"))
