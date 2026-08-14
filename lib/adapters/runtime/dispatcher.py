"""RunTargetDispatcher — middle router from agent JSON run_target to adapters."""

from __future__ import annotations

from typing import Any

from lib.adapters.frameworks.framework_discovery import framework_run_targets
from lib.adapters.runtime.paths import ADAPTERS, RuntimeAdapter, resolve_all_path_forms

VALID_TARGETS = ("windows", "wsl", "linux", "docker")

# Old configs / typos → canonical
_COMPAT = {
    "": "windows",
    "win": "windows",
    "window": "windows",
    "wsl/linux": "wsl",
    "wsl_linux": "wsl",
}


class RunTargetError(ValueError):
    """Invalid or framework-disallowed run_target."""


def normalize_run_target(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in _COMPAT:
        return _COMPAT[s]
    if s in VALID_TARGETS:
        return s
    return "windows"


def dispatch(run_target: str, framework: str = "") -> RuntimeAdapter:
    """Select adapter; raise if framework matrix forbids the target."""
    target = normalize_run_target(run_target)
    allowed = framework_run_targets(framework) if framework else list(VALID_TARGETS)
    # Matrices that omit linux still allow it when explicitly requested after Arch1 expansion;
    # prefer matrix when non-empty.
    if allowed and target not in allowed:
        # Compat: old matrices without linux — map linux→wsl if wsl allowed
        if target == "linux" and "wsl" in allowed:
            target = "wsl"
        elif target not in allowed:
            raise RunTargetError(
                f"run_target={target!r} not allowed for framework={framework!r}; allowed={allowed}"
            )
    adapter = ADAPTERS.get(target)
    if adapter is None:
        raise RunTargetError(f"unknown run_target={target!r}")
    return adapter


def dispatch_agent(agent_cfg: dict[str, Any] | None) -> RuntimeAdapter:
    cfg = agent_cfg or {}
    return dispatch(str(cfg.get("run_target") or "windows"), str(cfg.get("type") or ""))


def path_forms_for(
    logical_path: str,
    data_dir: str = "",
    *,
    install_root: str = "",
    framework: str = "",
) -> dict[str, str]:
    return resolve_all_path_forms(
        logical_path, data_dir, install_root=install_root, framework=framework
    )
