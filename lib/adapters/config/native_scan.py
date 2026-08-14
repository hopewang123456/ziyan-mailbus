"""Agent 原生目录资产扫描 — 安装路径配置（35f）。

输入：framework + agent_id + 用户配置的安装根路径。
输出：该 agent 在原生目录下 rule/skill/memory/identity 资产路径（含存在性），
      以及四端（windows / wsl / linux / docker）路径形态。

扫描依据：`_path-map.json` 的 `junctions.mount_points`（原生目录 → Obsidian 目标
的正式映射），叠加各框架身份文件约定（SOUL.md / CLAUDE.md / IDENTITY.md）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.infra.constants import AGENT_VAULT_ROOT
from lib.adapters.frameworks.framework_discovery import framework_run_targets

__all__ = ["scan_agent_assets", "path_map_mounts_for", "identity_file_candidates"]

# 各框架身份文件名（原生目录内）
_IDENTITY_FILENAME = {
    "hermes": "SOUL.md",
    "hermes_profile": "SOUL.md",
    "openclaw": "SOUL.md",
    "opencode": "SOUL.md",
    "codex": "IDENTITY.md",
    "claude_code": "CLAUDE.md",
    "cursor": "CLAUDE.md",
    "cline": "CLAUDE.md",
}


def _vault_abs(rel: str) -> str:
    return str((AGENT_VAULT_ROOT / rel).resolve())


def _load_path_map() -> dict[str, Any]:
    candidates = [
        AGENT_VAULT_ROOT / "_path-map.json",
        AGENT_VAULT_ROOT.parent / "_path-map.json",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                return json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def _norm_framework(fw: str) -> str:
    """_path-map.json framework 归一化：hermes_profile → hermes。"""
    f = (fw or "").strip()
    if f == "hermes_profile":
        return "hermes"
    return f


def path_map_mounts_for(framework: str, agent_id: str = "") -> list[dict[str, str]]:
    """返回 _path-map.json junctions 中匹配该 framework（及 agent）的挂载点。"""
    pm = _load_path_map()
    mounts = pm.get("junctions", {}).get("mount_points") or []
    fw = _norm_framework(framework)
    aid = (agent_id or "").strip()
    out: list[dict[str, str]] = []
    for m in mounts:
        if not isinstance(m, dict):
            continue
        if m.get("framework") != fw:
            continue
        ids = m.get("ids") or []
        if ids and aid and aid not in ids:
            continue
        # 无 ids 的挂载：若 native 含 `-<person>`（如 .claude-agent-b）而当前 agent 不匹配则过滤
        native = str(m.get("native") or "")
        if not ids and aid:
            person_slugs = list((pm.get("persons") or {}).keys())
            for slug in person_slugs:
                if slug == aid:
                    continue
                if f"-{slug}" in native:
                    break  # 该挂载属于其他人物 → 过滤
            else:
                out.append({str(k): str(v) for k, v in m.items()})
            continue
        out.append({str(k): str(v) for k, v in m.items()})
    return out


def _subst_mount_native(native: str, *, framework: str, agent_id: str, person_dir: str, person_id: str) -> str:
    """替换挂载点 native 路径中的占位符：{id}/{person_dir}/{person_id}。"""
    out = native
    if "{id}" in out:
        out = out.replace("{id}", agent_id)
    if "{person_dir}" in out:
        out = out.replace("{person_dir}", person_dir or agent_id)
    if "{person_id}" in out:
        out = out.replace("{person_id}", person_id or agent_id)
    # %USERPROFILE% / %HOME% 展开
    out = os.path.expandvars(out.replace("/", os.sep))
    return out


def _person_folder_guess(framework: str, agent_id: str) -> tuple[str, str]:
    """从 AGENT_VAULT_ROOT 人物索引推断 person_dir / person_id（尽力而为）。"""
    pm = _load_path_map()
    person = (pm.get("persons") or {}).get(agent_id) or {}
    if person:
        return str(person.get("dir") or agent_id), str(person.get("id") or agent_id)
    # 兜底：按 022N3-persons 目录形状找 <id>-<agent_id>
    fw_cfg = (pm.get("frameworks") or {}).get(_norm_framework(framework)) or {}
    cat = pm.get("roots", {}).get("members_root", "Agent/02-members") + "/022-category"
    base = AGENT_VAULT_ROOT / cat / str(fw_cfg.get("dir") or "") / str(fw_cfg.get("persons") or "")
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.name.endswith(f"-{agent_id}") and child.is_dir():
                return child.name, child.name.split("-")[0]
    return agent_id, agent_id


def identity_file_candidates(framework: str, agent_id: str, install_root: str) -> list[dict[str, Any]]:
    """按框架约定返回身份文件候选路径（原生目录内）。"""
    fw = (framework or "").strip()
    fname = _IDENTITY_FILENAME.get(fw, "SOUL.md")
    base = Path(install_root) if install_root else Path()
    cands: list[dict[str, Any]] = []
    patterns: list[str] = []
    if fw in ("hermes", "hermes_profile"):
        patterns = [
            f"profiles/{agent_id}/{fname}",
        ]
    elif fw == "openclaw":
        patterns = [
            f"space/{agent_id}/{fname}",
            f"{agent_id}/{fname}",
            f"space/{fname}",
            fname,
        ]
    elif fw == "codex":
        patterns = [fname, f"agents/{agent_id}/{fname}"]
    elif fw in ("claude_code", "cline"):
        patterns = [fname]
    elif fw == "opencode":
        patterns = [fname, f"{agent_id}/{fname}"]
    else:
        patterns = [fname]
    for rel in patterns:
        p = base / rel.replace("/", os.sep)
        p = Path(os.path.expandvars(str(p)))
        cands.append({
            "path": str(p),
            "exists": p.is_file(),
            "kind": "identity",
            "source": "native",
        })
    return cands


def _native_paths_for_mount(mount: dict[str, str], *, framework: str, agent_id: str, install_root: str) -> list[dict[str, Any]]:
    """把一条 mount 记录转成可展示的原生资产路径。install_root 覆盖 native 的根前缀。"""
    native_tpl = mount.get("native") or ""
    target_rel = mount.get("target") or ""
    if not native_tpl:
        return []
    person_dir, person_id = _person_folder_guess(framework, agent_id)
    native = _subst_mount_native(native_tpl, framework=framework, agent_id=agent_id, person_dir=person_dir, person_id=person_id)
    # 若用户给了 install_root，则替换根前缀
    if install_root:
        # native_tpl 的盘符/根前缀替换为 install_root
        native = _override_root(native_tpl, install_root, framework=framework, agent_id=agent_id, person_dir=person_dir, person_id=person_id)
    p = Path(native)
    return [{
        "path": str(p),
        "exists": p.is_dir() or p.is_file(),
        "kind": "memory" if "memor" in native_tpl.lower() else "skills",
        "source": "junction-map",
        "target": _vault_abs(target_rel) if target_rel else "",
    }]


def _override_root(native_tpl: str, install_root: str, *, framework: str, agent_id: str, person_dir: str, person_id: str) -> str:
    """用用户安装根覆盖模板根前缀。

    native_tpl 形如 `<HERMES_DATA>/.hermes/profiles/{id}/skills` 或
    `%USERPROFILE%/.claude-agent-b/skills`。
    规则：先做占位符替换得到 native_full；若 install_root 与 native_full 的根前缀
    一致则直接用 native_full，否则用 install_root 拼模板相对尾。
    """
    # 1) 占位符替换后的完整路径
    native_full = _subst_mount_native(
        native_tpl, framework=framework, agent_id=agent_id, person_dir=person_dir, person_id=person_id
    )
    root_norm = os.path.normpath(os.path.abspath(install_root)) if install_root else ""
    full_norm = os.path.normpath(os.path.abspath(native_full))
    if not root_norm:
        return full_norm
    # 2) 根前缀一致（盘符或前两段）→ 直接用 full
    def _root_prefix(p: str) -> str:
        p = p.replace("\\", "/")
        segs = [s for s in p.split("/") if s]
        if segs and len(segs[0]) == 2 and segs[0][1] == ":":
            return segs[0]
        if segs:
            return segs[0]
        return ""
    if _root_prefix(root_norm) == _root_prefix(full_norm):
        return full_norm
    # 3) 前缀不一致 → install_root + 模板相对尾（去掉盘符/~/根段）
    tpl = native_tpl.replace("/", os.sep)
    segments = [s for s in tpl.split("/") if s]
    if segments and (len(segments[0]) == 2 and segments[0][1] == ":"):
        segments = segments[1:]
    elif segments and segments[0] in (".", "~", "%USERPROFILE%"):
        segments = segments[1:]
    tail = "/".join(segments)
    if not tail:
        return root_norm
    # 仍做占位符替换
    tail = _subst_mount_native(tail, framework=framework, agent_id=agent_id, person_dir=person_dir, person_id=person_id)
    return os.path.normpath(os.path.join(root_norm, tail.replace("/", os.sep)))


def _run_target_paths(
    win_path: str,
    data_dir: str,
    *,
    install_root: str = "",
    framework: str = "",
) -> dict[str, str]:
    """四端路径：经 RunTargetDispatcher / path_forms（windows/wsl/linux/docker）。"""
    from lib.adapters.runtime.dispatcher import path_forms_for

    return path_forms_for(
        win_path, data_dir, install_root=install_root, framework=framework
    )


def scan_agent_assets(
    framework: str,
    agent_id: str,
    install_root: str = "",
    *,
    data_dir: str = "",
    run_target: str = "",
) -> dict[str, Any]:
    """扫描一个 agent 的原生目录资产。

    - install_root: 用户配置的安装根（如 <HERMES_DATA>/.hermes、<OPENCODE_ROOT>）
    - run_target: 用户选择的运行端（windows/wsl/docker），未传回落到 windows
    - 返回 rule/skill/memory/identity 各资产路径 + 存在性 + 三端形态 + path_existence_gate
    """
    fw = (framework or "").strip()
    aid = (agent_id or "").strip()
    from lib.adapters.runtime.dispatcher import normalize_run_target

    run_target = normalize_run_target(run_target)

    # path_existence_gate：归一化 install_root 到 host 表示后 stat（读写真源在 host，35g3 host_rw）。
    host_root = ""
    install_root_exists = False
    if install_root:
        try:
            from .sync_layers import normalize_host_path

            host_root = str(normalize_host_path(install_root))
        except Exception:
            host_root = install_root
        install_root_exists = bool(host_root) and (
            os.path.isdir(host_root) or os.path.isfile(host_root)
        )
    gate = {
        "exists": install_root_exists,
        "passed": install_root_exists,
        "install_root": host_root or install_root,
        "reason": "" if install_root_exists else f"install path missing: {install_root}",
    }

    mounts = path_map_mounts_for(fw, aid)
    assets: list[dict[str, Any]] = []
    for m in mounts:
        assets.extend(_native_paths_for_mount(m, framework=fw, agent_id=aid, install_root=install_root))

    identities = identity_file_candidates(fw, aid, install_root)

    # rules：Obsidian 侧规则由 person 索引 frontmatter 声明；原生侧常见 `<install>/rules`
    rule_cands: list[dict[str, Any]] = []
    if install_root:
        for rel in ("rules", ".mailbus/rules"):
            p = Path(install_root) / rel
            rule_cands.append({
                "path": str(p),
                "exists": p.is_dir(),
                "kind": "rules",
                "source": "convention",
            })

    all_items = assets + identities + rule_cands

    def _with_targets(it: dict[str, Any]) -> dict[str, Any]:
        return {
            **it,
            "paths": _run_target_paths(
                str(it.get("path") or ""), data_dir, install_root=install_root, framework=fw
            ),
        }

    return {
        "framework": fw,
        "agent_id": aid,
        "install_root": install_root,
        "run_target": run_target,
        "run_targets": framework_run_targets(fw),
        "run_target_labels": {
            "windows": "Windows",
            "wsl": "WSL (Ubuntu)",
            "linux": "Linux",
            "docker": "Docker",
        },
        "gate": gate,
        "run_targets_note": "windows=host / wsl=Ubuntu VM / linux=native / docker=bind-mount",
        "assets": [_with_targets(it) for it in all_items],
        "found": [_with_targets(it) for it in all_items if it.get("exists")],
        "missing": [_with_targets(it) for it in all_items if not it.get("exists")],
        "note": "扫描依据 _path-map.json junctions.mount_points + 框架身份文件约定",
    }
