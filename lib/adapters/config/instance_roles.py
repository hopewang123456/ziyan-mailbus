"""Discover & attach roles under an Agent instance (Members / path-map / native)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.adapters.config.agent_instances import _instance_key
from lib.adapters.config.avatar_paths import default_animated_path, default_portrait_path
from lib.adapters.config.launch_ports import resolve_port
from lib.infra.constants import AGENT_VAULT_ROOT
from lib.infra.utils import json_read, json_write

# instance.type → path-map frameworks / persons.framework
_TYPE_TO_MAP_FW = {
    "hermes": "hermes",
    "hermes_profile": "hermes",
    "openclaw": "openclaw",
    "codex": "codex",
    "claude_code": "claude_code",
    "cursor": "cursor",
    "opencode": "opencode",
    "cline": "cline",
}

_DEFAULT_LAUNCH = {
    "hermes_profile": "hermes_dashboard",
    "hermes": "hermes_dashboard",
    "openclaw": "openclaw_gateway",
    "codex": "codex_docker",
    "claude_code": "claude_host",
    "opencode": "opencode_cli",
    "cursor": None,
}


def _path_map() -> dict[str, Any]:
    root = Path(AGENT_VAULT_ROOT)
    # AGENT_VAULT_ROOT may be …/Agent or vault; tolerate both
    candidates = [
        root / "_path-map.json",
        root / "Agent" / "_path-map.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def map_framework(instance_type: str) -> str:
    return _TYPE_TO_MAP_FW.get((instance_type or "").strip(), (instance_type or "").strip())


def discover_roles_for_instance(instance: dict[str, Any]) -> list[dict[str, Any]]:
    """Return candidate roles [{id, display_name, members_category, source}]."""
    atype = (instance.get("type") or "").strip()
    fw = map_framework(atype)
    found: dict[str, dict[str, Any]] = {}

    pmap = _path_map()
    vault = Path(pmap.get("vault_root") or str(AGENT_VAULT_ROOT))
    persons = pmap.get("persons") or {}
    for pid, meta in persons.items():
        if not isinstance(meta, dict):
            continue
        if (meta.get("framework") or "").strip() != fw:
            continue
        cat = meta.get("category") or ""
        found[pid] = {
            "id": pid,
            "display_name": meta.get("display_name") or pid,
            "members_category": str(vault / cat) if cat else "",
            "source": "path-map",
        }

    # Native: Hermes profiles under install_path (skip ids owned by other frameworks in path-map)
    install = (instance.get("install_path") or "").strip()
    if fw == "hermes" and install:
        other_fw_ids = {
            pid
            for pid, meta in persons.items()
            if isinstance(meta, dict) and (meta.get("framework") or "").strip() not in ("", fw)
        }
        profiles = Path(install) / "profiles"
        if profiles.is_dir():
            for child in profiles.iterdir():
                if not child.is_dir() or child.name.startswith("."):
                    continue
                rid = child.name
                if rid in other_fw_ids:
                    continue
                found.setdefault(
                    rid,
                    {
                        "id": rid,
                        "display_name": rid,
                        "members_category": "",
                        "source": "native-profiles",
                    },
                )

    return sorted(found.values(), key=lambda x: x["id"])


def _members_paths_for_role(role_id: str, instance: dict[str, Any]) -> dict[str, str]:
    pmap = _path_map()
    vault = Path(pmap.get("vault_root") or str(AGENT_VAULT_ROOT))
    person = (pmap.get("persons") or {}).get(role_id) or {}
    fw_key = map_framework(instance.get("type") or "")
    fw = (pmap.get("frameworks") or {}).get(fw_key) or {}
    category = fw.get("category") or ""
    config_rel = fw.get("config") or ""
    skills_rel = fw.get("skills") or ""
    person_cat = person.get("category") or ""
    pid = person.get("id") or ""

    def ap(*parts: str) -> str:
        return str(vault.joinpath(*[p for p in parts if p]))

    paths = dict(instance.get("paths") or {}) if isinstance(instance.get("paths"), dict) else {}
    if category and config_rel:
        paths.setdefault("framework_config", ap(category, config_rel))
        paths.setdefault("native_config", ap(category, config_rel))
    if category and skills_rel:
        paths.setdefault("framework_skills", ap(category, skills_rel))
        paths.setdefault("skills", ap(category, skills_rel))
    if person_cat:
        paths["persona"] = ap(person_cat)
        paths["path_map_person"] = person_cat
        if pid:
            paths["config"] = ap(person_cat, f"{pid}1-config")
            paths["memory"] = ap(person_cat, f"{pid}3-memory")
    paths.setdefault("portrait", default_portrait_path(role_id))
    paths.setdefault("avatar_animated", default_animated_path(role_id))
    paths.setdefault("members_root", ap(pmap.get("roots", {}).get("members_root") or "Agent/02-members"))
    return {k: v for k, v in paths.items() if v}


def load_roles_for_instance(data_dir: str, instance_id: str) -> dict[str, Any]:
    """Discover roles, upsert into agents[], link instance_id, update role_ids."""
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    instances = dict(cfg.get("agent_instances") or {})
    inst = instances.get(instance_id)
    if not isinstance(inst, dict):
        raise ValueError(f"unknown instance: {instance_id}")

    discovered = discover_roles_for_instance(inst)
    agents = dict(cfg.get("agents") or {})
    atype = (inst.get("type") or "none").strip()
    # hermes instance → roles are hermes_profile
    role_type = "hermes_profile" if atype in ("hermes", "hermes_profile") else atype
    tmpl = _DEFAULT_LAUNCH.get(role_type)

    role_ids: list[str] = []
    created: list[str] = []
    updated: list[str] = []

    for item in discovered:
        rid = item["id"]
        role_ids.append(rid)
        paths = _members_paths_for_role(rid, inst)
        launch: dict[str, Any] = {"has_browser": role_type not in ("opencode", "cursor", "none")}
        if tmpl:
            launch["template"] = tmpl
            if role_type in ("hermes_profile", "hermes"):
                launch["browser"] = {"kind": "hermes_dashboard"}
            elif role_type == "openclaw":
                launch["browser"] = {"kind": "openclaw_gateway"}
            elif role_type == "codex":
                launch["browser"] = {"kind": "codex_docker"}
            elif role_type == "claude_code":
                launch["browser"] = {"kind": "claude_ttyd"}
                launch["launch_via_api"] = True

        port = None
        try:
            port = resolve_port(rid, {"type": role_type, "port": None}, launch.get("browser") or {})
        except Exception:
            port = None
        if port is None and inst.get("port") not in (None, ""):
            # only use instance port for single-role frameworks
            if role_type in ("opencode", "cursor") or len(discovered) == 1:
                port = inst.get("port")

        prev = agents.get(rid) if isinstance(agents.get(rid), dict) else {}
        rec = dict(prev)
        # 运行环境字段（run_target/install_path/host/custom_paths）唯一 SoT 在实例；
        # 清理角色级历史冗余，运行时只读继承实例，避免双源漂移。
        for _legacy in ("run_target", "install_path", "host", "custom_paths"):
            rec.pop(_legacy, None)
        rec.update(
            {
                "type": role_type,
                "name": rec.get("name") or item.get("display_name") or rid,
                "role": rec.get("role") or item.get("display_name") or rid,
                "instance_id": instance_id,
                "paths": paths,
                "native_config_path": paths.get("framework_config") or paths.get("config") or "",
                "enabled": rec.get("enabled", True),
                "available": True,
            }
        )
        if port not in (None, ""):
            rec["port"] = int(port)
            br = dict((rec.get("launch") or {}).get("browser") or launch.get("browser") or {})
            if role_type in ("hermes_profile", "hermes"):
                br["dashboard_port"] = int(port)
            elif role_type == "openclaw":
                br["gateway_port"] = int(port)
            launch["browser"] = br
        if not rec.get("launch"):
            rec["launch"] = launch
        else:
            merged_launch = dict(rec["launch"])
            merged_launch.update({k: v for k, v in launch.items() if k != "browser"})
            if launch.get("browser"):
                merged_launch["browser"] = {
                    **dict(merged_launch.get("browser") or {}),
                    **launch["browser"],
                }
            rec["launch"] = merged_launch

        if not rec.get("auth") and isinstance(inst.get("auth"), dict):
            rec["auth"] = dict(inst["auth"])
        if rid not in agents:
            created.append(rid)
        else:
            updated.append(rid)
        agents[rid] = rec

    inst = dict(inst)
    inst["role_ids"] = role_ids
    inst["roles_loaded_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    instances[instance_id] = inst
    cfg["agent_instances"] = instances
    cfg["agents"] = agents
    json_write(cfg_path, cfg)

    return {
        "instance_id": instance_id,
        "discovered": discovered,
        "role_ids": role_ids,
        "created": created,
        "updated": updated,
        "count": len(role_ids),
    }


def upsert_instance(data_dir: str, fields: dict[str, Any], *, instance_id: str | None = None) -> dict[str, Any]:
    """Create or update an agent instance card (config page SoT).

    Returns ``{instance, ...auth_gate}`` where auth_gate may include
    ``auth_required`` + ``obtain_credential_url`` when the framework needs
    browser creds and none are held yet.
    """
    from lib.adapters.config.auth_policy import (
        agent_has_stored_browser_cred,
        agent_requires_browser_auth,
        raw_browser_entry_url,
    )
    from lib.adapters.config import token_store

    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    instances = dict(cfg.get("agent_instances") or {})
    atype = str(fields.get("type") or "").strip()
    if not atype:
        raise ValueError("type required")
    run_target = str(fields.get("run_target") or "windows").strip()
    install_path = str(fields.get("install_path") or "").strip()
    host = str(fields.get("host") or "127.0.0.1").strip()
    port = fields.get("port")
    if port not in (None, ""):
        try:
            port = int(port)
        except (TypeError, ValueError):
            pass
    if instance_id and instance_id in instances:
        iid = instance_id
        rec = dict(instances[iid])
    else:
        distro = str(fields.get("distro") or "auto").strip() or "auto"
        iid = _instance_key(atype, run_target, install_path, host, None, distro)
        rec = {"id": iid, "role_ids": []}
    for k in (
        "type",
        "run_target",
        "install_path",
        "host",
        "port",
        "custom_paths",
        "paths",
        "label",
        "native_config_path",
        "enabled",
        "distro",
    ):
        if k in fields:
            rec[k] = fields[k]
    if "port" in fields:
        rec["port"] = port
    # 实例级监测开关默认开启；distro 仅对 wsl/linux 有意义，默认 auto
    rec.setdefault("enabled", True)
    rec.setdefault("distro", "auto")

    # Persist credentials into secrets; keep only mode/refs on the card
    if "auth" in fields and isinstance(fields.get("auth"), dict):
        auth_in = dict(fields["auth"])
        mode = str(auth_in.get("mode") or "none").strip().lower() or "none"
        if mode == "token" and (auth_in.get("token") or "").strip():
            token_store.ensure_browser_credentials(
                data_dir, iid, mode="token", token=str(auth_in["token"]).strip()
            )
            auth_in.pop("token", None)
            auth_in["token_ref"] = iid
            auth_in["mode"] = "token"
        elif mode == "basic" and (
            (auth_in.get("password") or "").strip() or (auth_in.get("user") or "").strip()
        ):
            token_store.ensure_browser_credentials(data_dir, iid, mode="basic")
            data = token_store.read_secrets(data_dir)
            ba = data.setdefault(token_store.BROWSER_AUTH_KEY, {})
            cur = dict(ba.get(iid) or {})
            if (auth_in.get("user") or "").strip():
                cur["user"] = str(auth_in["user"]).strip()
            if (auth_in.get("password") or "").strip():
                cur["password"] = str(auth_in["password"]).strip()
            ba[iid] = cur
            token_store.write_secrets(data_dir, data)
            auth_in.pop("password", None)
            auth_in.pop("user", None)
            auth_in["username_ref"] = iid
            auth_in["password_ref"] = iid
            auth_in["mode"] = "basic"
        else:
            auth_in["mode"] = mode
        rec["auth"] = auth_in

    rec["id"] = iid
    rec.setdefault("label", f"{atype}@{run_target}")
    rec.setdefault("role_ids", [])
    if "host" in fields or not rec.get("host"):
        rec["host"] = host
    instances[iid] = rec
    cfg["agent_instances"] = instances
    json_write(cfg_path, cfg)

    out: dict[str, Any] = {"instance": rec}
    if agent_requires_browser_auth(atype, rec) and not agent_has_stored_browser_cred(data_dir, iid, rec):
        out["auth_required"] = True
        out["obtain_credential_url"] = raw_browser_entry_url(data_dir, iid, rec)
        out["auth_hint"] = "该 Agent 类型需要登录凭证；已保存实例，请在打开的网页端完成登录/取凭据后写回"
    return out
