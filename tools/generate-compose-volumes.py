#!/usr/bin/env python3
"""Generate docker-compose volume mounts from access/**/agent.json (Phase 3.3).

Usage:
  python tools/generate-compose-volumes.py
  python tools/generate-compose-volumes.py --check   # exit 2 if compose drift
  python tools/generate-compose-volumes.py --host-prefix /mnt/e
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.agent_registry import load_all_agents  # noqa: E402
from lib.compose_registry import agent_compose_services, resolve_compose_service  # noqa: E402
from lib.constants import MAILBUS_ROOT  # noqa: E402
from lib.env_bootstrap import load_mailbus_env, mailbus_paths  # noqa: E402
from lib.sync_layers import normalize_host_path  # noqa: E402

COMPOSE_PATH = ROOT / "docker-agents" / "docker-compose.yml"
OVERRIDE_PATH = ROOT / "docker-agents" / "docker-compose.override.yml"

# Legacy mounts removed in Phase 3.3 (#17 #27 #34)
FORBIDDEN_PATTERNS = (
    re.compile(r"/mailbus/adapters"),
    re.compile(r"/mailbus/roles"),
    re.compile(r"/mailbus/identities"),
    re.compile(r"mail/external-tools:"),
    re.compile(r"adapters/\.sync"),
)

# Required on agent-facing services (hermes, openclaw, codex*, dali, mailbus)
REQUIRED_AGENT_MOUNTS = (
    "/mailbus/skills",
    "/mailbus/access",
    "/mailbus/rules",
)

MAILBUS_SERVICE_MOUNTS = (
    "/mailbus/skills",
    "/mailbus/access",
    "/mailbus/rules",
)

HERMES_EXTRA = ("/mailbus/access/hermes/.sync",)


def _host_prefix(arg: str, mail_root: Path) -> str:
    if arg:
        return arg.rstrip("/")
    # WSL default when mail lives on E:
    drive = mail_root.drive.rstrip(":").lower() if mail_root.drive else "e"
    return f"/mnt/{drive}"


def _to_compose_host(path: Path, host_prefix: str) -> str:
    """Native Path → /mnt/e/... for compose."""
    s = str(path.resolve()).replace("\\", "/")
    if s.startswith("/mnt/"):
        return s
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    if m:
        return f"{host_prefix}/{m.group(2)}"
    return s


def standard_mail_mounts(host_prefix: str, *, mail_root: Path | None = None) -> list[str]:
    root = mail_root or MAILBUS_ROOT
    hp = _to_compose_host(root, host_prefix)
    lines = [
        f"      - {hp}:/mailbus",
        f"      - {hp}/skills:/mailbus/skills:ro",
        f"      - {hp}/rules:/mailbus/rules:ro",
        f"      - {hp}/access:/mailbus/access:ro",
        f"      - {hp}/access/external-tools:/mailbus/external-tools:ro",
    ]
    return lines


def hermes_service_mounts(host_prefix: str, *, mail_root: Path | None = None) -> list[str]:
    root = mail_root or MAILBUS_ROOT
    hp = _to_compose_host(root, host_prefix)
    lines = [
        f"      - {hp}/store:/mailbus/store",
        f"      - {hp}/tools:/mailbus/tools:ro",
        f"      - {hp}/skills:/mailbus/skills:ro",
        f"      - {hp}/rules:/mailbus/rules:ro",
        f"      - {hp}/access:/mailbus/access:ro",
        f"      - {hp}/access/external-tools:/mailbus/external-tools:ro",
        f"      - {hp}/access/hermes/.sync:/mailbus/access/hermes/.sync",
    ]
    return lines


def workspace_mounts(host_prefix: str, *, mail_root: Path | None = None) -> dict[str, list[str]]:
    """Per docker compose service → extra workspace volume lines."""
    root = mail_root or MAILBUS_ROOT
    out: dict[str, list[str]] = {}
    for agent_id, rec in sorted(load_all_agents(mail_root=root, refresh=True).items()):
        docker = rec.get("docker") or {}
        service = resolve_compose_service(agent_id, docker)
        ws = rec.get("workspace")
        if not service or not ws:
            continue
        fw = rec.get("framework") or ""
        host_path = normalize_host_path(str(ws), mail_root=root)
        hp = _to_compose_host(host_path, host_prefix)
        lines = out.setdefault(service, [])
        if fw == "opencode":
            lines.append(f"      - {hp}:/workspace/opencode:ro")
            skills_hp = _to_compose_host(host_path / "skills", host_prefix)
            lines.append(f"      - {skills_hp}:/workspace/opencode/skills")
        elif fw == "openclaw":
            # 只挂一次主 workspace；a-yige 等已在 openclaw_space 子目录内
            root_line = f"      - {hp}:/workspace"
            already = any(
                x.split(":")[0].strip("- ").rstrip() == hp and ":/workspace" in x and "/workspace/" not in x.split(":/")[-1]
                for x in lines
            )
            # 若 ws 是已挂载目录的子路径，跳过（避免 a-yige 盖掉 /workspace）
            parent_mounted = any(
                hp.startswith(x.split(":")[0].strip("- ").rstrip().rstrip("/") + "/")
                for x in lines
                if ":/workspace" in x
            )
            if not already and not parent_mounted:
                lines[:] = [x for x in lines if not (
                    ":/workspace" in x and "/workspace/" not in x.split(":/")[-1]
                    and x.split(":")[0].strip("- ").rstrip().startswith(hp + "/")
                )]
                if not any(
                    x.split(":")[0].strip("- ").rstrip() == hp and ":/workspace" in x
                    for x in lines
                ):
                    lines.append(f"      - {hp}:/workspace")
            # dedupe plain /workspace if rw variant already present via infra
            roots = [i for i, x in enumerate(lines) if x.rstrip().endswith(":/workspace")]
            if len(roots) > 1:
                for i in reversed(roots[1:]):
                    lines.pop(i)
        elif fw == "codex":
            lines.append(f"      - {hp}:/workspace/{agent_id}:ro")
        elif fw == "claude_code":
            claude_hp = _to_compose_host(host_path, host_prefix)
            lines.append(f"      - {claude_hp}:/{agent_id}-workspace:ro")
    return out


def render_fragment(host_prefix: str) -> str:
    parts = ["# --- generated by tools/generate-compose-volumes.py ---", ""]
    parts.append("# mailbus service volumes:")
    parts.extend(standard_mail_mounts(host_prefix))
    parts.append("")
    parts.append("# hermes service volumes:")
    parts.extend(hermes_service_mounts(host_prefix))
    parts.append("")
    parts.append("# workspace mounts by docker service:")
    for svc, lines in workspace_mounts(host_prefix).items():
        parts.append(f"# {svc}:")
        parts.extend(lines)
    parts.append("# --- end generated fragment ---")
    return "\n".join(parts) + "\n"


def infra_volume_lines(host_prefix: str = "", *, mail_root: Path | None = None) -> dict[str, list[str]]:
    """Infra paths from env — used in compose override."""
    load_mailbus_env()
    paths = mailbus_paths()
    root = mail_root or MAILBUS_ROOT
    prefix = _host_prefix(host_prefix, root)
    lines: dict[str, list[str]] = {}

    def add(svc: str, host: str, container: str, mode: str = "ro") -> None:
        if not host or not Path(host).exists():
            return
        hp = _to_compose_host(Path(host), prefix)
        lines.setdefault(svc, []).append(f"      - {hp}:{container}:{mode}")

    add("hermes", paths.get("hermes_data", ""), "/home/hermes/.hermes", "rw")
    hermes_sm = str(Path(paths.get("hermes_data", "")).parent / "shared-memory") if paths.get("hermes_data") else ""
    if Path(hermes_sm).exists():
        add("hermes", hermes_sm, "/hermes/shared-memory", "rw")
    add("openclaw", paths.get("openclaw_workspace", ""), "/workspace", "rw")
    add("dali", paths.get("opencode_root", ""), "/workspace/opencode", "rw")
    op_sk = str(Path(paths.get("opencode_root", "")) / "skills") if paths.get("opencode_root") else ""
    add("dali", op_sk, "/workspace/opencode/skills", "rw")
    nm = paths.get("node_modules", "")
    for svc in ("agentmemory", "lingxiao", "lingjian"):
        add(svc, nm, "/node_modules", "ro")
    lx = paths.get("lingxiao_workspace", "")
    add("lingxiao", lx, "/workspace/lingxiao", "ro")
    return lines


def emit_override(host_prefix: str = "", *, mail_root: Path | None = None) -> str:
    load_mailbus_env()
    from lib.constants import (
        AGENT_VAULT_ROOT,
        MAILBUS_RULES_ROOT,
        MAILBUS_SKILLS_ROOT,
    )

    root = mail_root or MAILBUS_ROOT
    hp = _host_prefix(host_prefix, root)
    paths = mailbus_paths()
    data = _to_compose_host(Path(paths["data_dir"]), hp)
    mroot = _to_compose_host(Path(paths["root"]), hp)
    skills_hp = _to_compose_host(MAILBUS_SKILLS_ROOT, hp)
    rules_hp = _to_compose_host(MAILBUS_RULES_ROOT, hp)
    vault_hp = _to_compose_host(AGENT_VAULT_ROOT, hp) if AGENT_VAULT_ROOT.exists() else ""

    shared = [
        f"      - {data}:/mailbus/store",
        f"      - {mroot}/tools:/mailbus/tools:ro",
        f"      - {skills_hp}:/mailbus/skills:ro",
        f"      - {rules_hp}:/mailbus/rules:ro",
        f"      - {mroot}/access:/mailbus/access:ro",
        f"      - {mroot}/access/external-tools:/mailbus/external-tools:ro",
    ]
    # profiles/*/skills may symlink into a Vault tree; containers that need
    # those targets must bind-mount the Vault root in override.yml (same host path).
    if vault_hp:
        shared.append(f"      - {vault_hp}:{vault_hp}")

    ws = workspace_mounts(hp, mail_root=root)
    infra = infra_volume_lines(hp, mail_root=root)

    agent_services = ["hermes", "openclaw", "lingxiao", "lingjian", "dali", "mailbus"]
    out_lines = [
        "# Generated by mailbus compose sync — do not edit by hand",
        "# Regenerate: mailbus compose sync",
        "services:",
    ]
    for svc in agent_services:
        vols = list(shared)
        if svc == "hermes":
            # .sync = optional framework-skill mirror only; runtime skills SoT = Vault via
            # profiles/*/skills junctions under /home/hermes/.hermes (see Agent/_path-map.md)
            vols.append(f"      - {mroot}/access/hermes/.sync:/mailbus/access/hermes/.sync")
            inbox = str(Path(data) / "inbox").replace("\\", "/")
            vols.append(f"      - {inbox}:/home/hermes/inbox:ro")
        vols.extend(infra.get(svc, []))
        vols.extend(ws.get(svc, []))
        # OpenClaw: Vault SoT mounts MUST come after openclaw_space:/workspace so they win
        if svc == "openclaw" and vault_hp:
            vols.append(f"      - {vault_hp}/skills/library/openclaw:/workspace/skills:ro")
            vols.append(f"      - {vault_hp}/memories/xiaoqi:/workspace/memory")
        if svc == "mailbus":
            vols = [
                f"      - {mroot}:/mailbus",
                f"      - {data}:/mailbus/store",
                f"      - {mroot}/run:/mailbus/run",
            ] + vols[1:]
        if len(vols) <= len(shared) and svc not in ws and svc not in infra:
            continue
        out_lines.append(f"  {svc}:")
        out_lines.append("    volumes:")
        seen = set()
        for v in vols:
            if v not in seen:
                seen.add(v)
                out_lines.append(v)
    return "\n".join(out_lines) + "\n"


def check_override_drift(host_prefix: str = "", *, mail_root: Path | None = None) -> list[str]:
    """Compare on-disk override with emit_override() expectation."""
    errors: list[str] = []
    if not OVERRIDE_PATH.is_file():
        errors.append("compose override missing — run: mailbus compose sync")
        return errors
    expected = emit_override(host_prefix, mail_root=mail_root)
    actual = OVERRIDE_PATH.read_text(encoding="utf-8")
    if expected.strip() == actual.strip():
        return errors

    def _workspace_lines(text: str) -> dict[str, set[str]]:
        by_svc: dict[str, set[str]] = {}
        current: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if line.startswith("  ") and stripped.endswith(":") and not stripped.startswith("- "):
                svc = stripped.rstrip(":")
                if svc != "volumes":
                    current = svc
                    by_svc.setdefault(current, set())
            elif current and stripped.startswith("- ") and ":/workspace" in stripped:
                by_svc.setdefault(current, set()).add(stripped)
            elif stripped == "services:":
                current = None
        return by_svc

    exp_ws = _workspace_lines(expected)
    act_ws = _workspace_lines(actual)
    for svc in sorted(set(exp_ws) | set(act_ws)):
        if exp_ws.get(svc, set()) != act_ws.get(svc, set()):
            missing = exp_ws.get(svc, set()) - act_ws.get(svc, set())
            extra = act_ws.get(svc, set()) - exp_ws.get(svc, set())
            if missing:
                errors.append(f"override drift {svc}: missing {sorted(missing)[:2]}")
            if extra:
                errors.append(f"override drift {svc}: extra {sorted(extra)[:2]}")
    if not errors:
        errors.append("compose override drift — run: mailbus compose sync")
    return errors


def write_override(path: Path | None = None, host_prefix: str = "") -> Path:
    target = path or OVERRIDE_PATH
    text = emit_override(host_prefix)
    target.write_text(text, encoding="utf-8")
    return target


def check_compose(compose_text: str) -> list[str]:
    errors: list[str] = []
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(compose_text):
            errors.append(f"forbidden mount pattern still present: {pat.pattern}")
    for req in REQUIRED_AGENT_MOUNTS:
        if req not in compose_text:
            errors.append(f"missing required mount target: {req}")
    if "/mailbus/access/hermes/.sync" not in compose_text:
        errors.append("missing hermes .sync mount: /mailbus/access/hermes/.sync")
    if "/mailbus/external-tools" not in compose_text:
        errors.append("missing external-tools mount: /mailbus/external-tools")
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description="Generate/check docker-compose volume mounts")
    p.add_argument("--host-prefix", default="", help="WSL host prefix, default /mnt/{drive}")
    p.add_argument("--check", action="store_true", help="Verify docker-compose.yml has v3 mounts")
    p.add_argument("--print", action="store_true", help="Print generated fragment to stdout")
    p.add_argument("--emit", metavar="PATH", nargs="?", const=str(OVERRIDE_PATH), help="Write compose override YAML")
    args = p.parse_args()

    hp = _host_prefix(args.host_prefix, MAILBUS_ROOT)

    if args.emit:
        out = write_override(Path(args.emit), hp)
        print(f"Wrote {out}")
        return 0

    if args.print or not args.check:
        print(render_fragment(hp))

    if args.check:
        if not COMPOSE_PATH.is_file():
            print(f"ERROR: missing {COMPOSE_PATH}", file=sys.stderr)
            return 1
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        if OVERRIDE_PATH.is_file():
            text += OVERRIDE_PATH.read_text(encoding="utf-8")
        errors = check_compose(text)
        if errors:
            for e in errors:
                print("FAIL", e, file=sys.stderr)
            return 2
        drift = check_override_drift(hp, mail_root=MAILBUS_ROOT)
        if drift:
            for e in drift:
                print("FAIL", e, file=sys.stderr)
            return 2
        print("OK: docker-compose.yml v3 mounts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
