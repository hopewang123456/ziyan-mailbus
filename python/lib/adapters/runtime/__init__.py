"""run_target runtime package — dispatcher + path adapters + distro + boundary + cred."""

from lib.adapters.runtime.boundary import is_cross_boundary, loopback_safe_for_peer, peer_host_hint
from lib.adapters.runtime.cred_delivery import (
    apply_instance_endpoint,
    resolve_codex_ui_password,
    resolve_openclaw_token,
    sync_browser_credentials_to_env,
)
from lib.adapters.runtime.dispatcher import (
    VALID_TARGETS,
    RunTargetError,
    dispatch,
    dispatch_agent,
    normalize_run_target,
    path_forms_for,
)
from lib.adapters.runtime.distro import CENTOS, UBUNTU, detect_distro
from lib.adapters.runtime.paths import resolve_all_path_forms

__all__ = [
    "VALID_TARGETS",
    "RunTargetError",
    "dispatch",
    "dispatch_agent",
    "normalize_run_target",
    "path_forms_for",
    "resolve_all_path_forms",
    "detect_distro",
    "UBUNTU",
    "CENTOS",
    "is_cross_boundary",
    "loopback_safe_for_peer",
    "peer_host_hint",
    "sync_browser_credentials_to_env",
    "resolve_openclaw_token",
    "resolve_codex_ui_password",
    "apply_instance_endpoint",
]
