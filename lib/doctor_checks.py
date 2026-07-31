"""Mailbus 诊断检查 — 供 mailbus doctor、Dashboard 诊所、CLI 工具共用。"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .constants import MAILBUS_ROOT
from .env_bootstrap import load_mailbus_env, mailbus_paths
from .platform_runner import detect_platform, docker_ready, probe_http, run, wsl_exe

Level = Literal["ok", "warn", "fail"]

# 恢复/迁移后必须存在的关键路径（相对 MAILBUS_ROOT）
_CRITICAL_FILES = (
    "tools/mailbus.py",
    "tools/generate-compose-volumes.py",
    "lib/constants.py",
    "lib/env_bootstrap.py",
    "lib/agent_registry.py",
    "lib/init_store.py",
    "lib/framework_discovery.py",
    "migrate/manifest.yaml",
    "migrate/bundle_import.py",
    "pyproject.toml",
    "config/mailbus/base.json",
    "config/frameworks/registry.json",
    "docker-agents/docker-compose.yml",
    "bus/__main__.py",
)

_EXPECTED_TRANSPORT_AGENTS = ()  # personal roster is local-only; see examples/transport/

_THIN_DIRS_WARN_BELOW = {
    "access/hermes": 2,
    "skills": 30,
    # overrides are personal (*.override.json); examples live as *.override.example.json
}


_EXPECTED_HERMES_AGENTS = (
    "lingjin", "lingtuo", "lingxi", "lingxun", "lingzhang", "lingzhao",
)


@dataclass
class DoctorItem:
    level: Level
    category: str
    message: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def docker_ready_wsl(distro: str = "Ubuntu") -> tuple[bool, str]:
    """Windows 上探测 WSL 内 docker daemon。"""
    wsl = wsl_exe()
    if not wsl:
        return False, "wsl.exe not found"
    try:
        r = run(
            [wsl, "-d", distro, "-e", "bash", "-lc", "docker info >/dev/null 2>&1 && echo ok"],
            timeout=30,
        )
        if r.returncode == 0 and "ok" in (r.stdout or ""):
            return True, distro
        err = (r.stderr or r.stdout or "").strip()[:200]
        return False, err or f"docker info failed in WSL ({distro})"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def docker_status(*, distro: str = "Ubuntu") -> dict[str, Any]:
    """汇总本机 / WSL Docker 可达性（Docker 栈在 WSL 时 Windows 本机 docker 可能不可用）。"""
    plat = detect_platform()
    local = docker_ready()
    wsl_ok, wsl_detail = (False, "")
    if plat == "win32":
        wsl_ok, wsl_detail = docker_ready_wsl(distro)
    ready = local or wsl_ok
    source = "local"
    if not local and wsl_ok:
        source = "wsl"
    elif local:
        source = "local"
    return {
        "platform": plat,
        "local": local,
        "wsl": wsl_ok,
        "wsl_detail": wsl_detail,
        "ready": ready,
        "source": source if ready else "",
    }


def check_data_integrity(*, mail_root: Path | None = None) -> list[DoctorItem]:
    """恢复 mail 源码树后的数据/文件完整性探测。"""
    root = Path(mail_root) if mail_root else MAILBUS_ROOT
    items: list[DoctorItem] = []

    missing_files = [rel for rel in _CRITICAL_FILES if not (root / rel).is_file()]
    if missing_files:
        items.append(DoctorItem(
            "fail",
            "integrity",
            f"关键文件缺失 ({len(missing_files)})",
            ", ".join(missing_files[:12]) + ("…" if len(missing_files) > 12 else ""),
        ))
    else:
        items.append(DoctorItem("ok", "integrity", "关键源码文件齐全", f"{len(_CRITICAL_FILES)} paths"))

    transport_dir = root / "access" / "transport"
    found = sorted(
        p.parent.name
        for p in transport_dir.glob("*/transport.json")
        if p.is_file()
    )
    if not found:
        items.append(DoctorItem(
            "warn",
            "integrity",
            "尚无本机 transport（个人 Agent 未配置）",
            "复制 examples/transport/agent-*/transport.json → access/transport/<your-id>/；见 config/README.md",
        ))
    else:
        items.append(DoctorItem(
            "ok",
            "integrity",
            f"本机 transport {len(found)} agents",
            ", ".join(found[:16]) + ("…" if len(found) > 16 else ""),
        ))

    for rel, min_files in _THIN_DIRS_WARN_BELOW.items():
        d = root / rel
        if not d.is_dir():
            items.append(DoctorItem("warn", "integrity", f"目录缺失: {rel}", "恢复可能不完整"))
            continue
        count = sum(1 for _ in d.rglob("*") if _.is_file())
        if count < min_files:
            items.append(DoctorItem(
                "warn",
                "integrity",
                f"{rel} 文件偏少 ({count} < {min_files})",
                "历史镜像可能更完整，按需从备份/Cursor History 补回",
            ))

    store = Path(os.environ.get("MAILBUS_DATA", root / "store"))
    if not (store / "config.json").is_file():
        items.append(DoctorItem("warn", "integrity", "store/config.json 不存在", "运行 init-store 或保留现有 store"))
    else:
        items.append(DoctorItem("ok", "integrity", "store/config.json 存在", str(store)))

    override = root / "docker-agents" / "docker-compose.override.yml"
    if override.is_file():
        items.append(DoctorItem("ok", "integrity", "compose override 已生成", str(override)))
    else:
        items.append(DoctorItem("warn", "integrity", "compose override 缺失", "运行: mailbus compose sync"))

    return items


def check_locale_transport_codes() -> list[DoctorItem]:
    """Wave3 + W7e: locale 覆盖 transport 与稳定错误码目录。"""
    try:
        from lib.locale.errors_zh import stable_codes_covered, transport_codes_covered

        items: list[DoctorItem] = []
        if transport_codes_covered():
            items.append(DoctorItem("ok", "locale", "transport 错误码中文齐全", "Wave3 S3"))
        else:
            items.append(DoctorItem("fail", "locale", "transport 错误码 locale 缺失", "补全 errors_zh.ERROR_ZH"))
        if stable_codes_covered():
            items.append(DoctorItem("ok", "locale", "稳定错误码 locale 目录齐全", "W7e D21"))
        else:
            items.append(DoctorItem("fail", "locale", "稳定错误码 locale 缺失", "补全 ALL_STABLE_CODES → ERROR_ZH"))
        return items
    except Exception as exc:
        return [DoctorItem("fail", "locale", "locale 检查失败", str(exc))]


def check_layout_hazard(*, repo_parent: Path | None = None) -> list[DoctorItem]:
    from .layout_guard import layout_report

    report = layout_report(repo_parent)
    if report.dedup_unsafe:
        return [DoctorItem(
            "warn",
            "layout",
            "mail ≡ mailbus-core（junction）— 禁止代码去重",
            report.message,
        )]
    if report.core_is_reparse and report.mail_exists:
        return [DoctorItem(
            "warn",
            "layout",
            "mailbus-core 为 reparse 点",
            report.message,
        )]
    return [DoctorItem("ok", "layout", "mail/ 与 mailbus-core/ 独立", report.message)]


def check_hermes_readiness(
    *,
    mail_root: Path | None = None,
    docker_ready_flag: bool = False,
    wsl_distro: str = "Ubuntu",
    chat_probe: bool = False,
) -> list[DoctorItem]:
    """Hermes + DeepSeek 就绪检查（chat_probe 较慢，诊所工具专用）。"""
    load_mailbus_env()
    paths = mailbus_paths()
    root = Path(mail_root) if mail_root else Path(paths["root"])
    items: list[DoctorItem] = []

    ds_key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("MAILBUS_INTERNAL_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if ds_key:
        items.append(DoctorItem("ok", "hermes", "DeepSeek/API key 已配置", "DEEPSEEK_API_KEY 或 fallback"))
    else:
        items.append(DoctorItem(
            "fail",
            "hermes",
            "缺少 DEEPSEEK_API_KEY",
            "在 mailbus-core/.env 设置 DEEPSEEK_API_KEY",
        ))

    hermes_data = Path(paths["hermes_data"])
    if hermes_data.is_dir():
        items.append(DoctorItem("ok", "hermes", "HERMES_DATA 目录存在", str(hermes_data)))
    else:
        items.append(DoctorItem(
            "fail",
            "hermes",
            "HERMES_DATA 不存在",
            f"{hermes_data}；典型路径 E:/hermes-data/.hermes",
        ))

    sync_root = root / "access" / "hermes" / ".sync"
    missing_sync = [
        a for a in _EXPECTED_HERMES_AGENTS
        if not (sync_root / a / "skills").is_dir()
    ]
    if missing_sync:
        items.append(DoctorItem(
            "warn",
            "hermes",
            f"access/hermes/.sync 缺失 {len(missing_sync)} 个 agent",
            ", ".join(missing_sync) + "；运行 sync_framework_workspace_skills 或 sync-all-agent-layers",
        ))
    else:
        items.append(DoctorItem("ok", "hermes", "Hermes .sync skills 齐全", str(sync_root)))

    if not docker_ready_flag:
        items.append(DoctorItem("warn", "hermes", "Docker 未就绪，跳过容器探针", ""))
        return items

    hermes_url = "http://127.0.0.1:9126/chat"
    if probe_http(hermes_url):
        items.append(DoctorItem("ok", "hermes", "Hermes dashboard :9126", hermes_url))
    else:
        items.append(DoctorItem("fail", "hermes", "Hermes :9126 不可达", "mailbus start 或 docker compose up hermes"))

    plat = detect_platform()
    container = os.environ.get("MAILBUS_HERMES_CONTAINER", "docker-agents-hermes-1")
    if plat == "win32":
        wsl = wsl_exe()
        if wsl:
            r = run(
                [
                    wsl, "-d", wsl_distro, "-e", "bash", "-lc",
                    f"docker inspect -f '{{{{.State.Running}}}}' {container} 2>/dev/null || echo missing",
                ],
                timeout=15,
            )
            state = (r.stdout or "").strip()
            if state == "true":
                items.append(DoctorItem("ok", "hermes", f"容器运行中 {container}", ""))
            else:
                items.append(DoctorItem("fail", "hermes", f"容器未运行 {container}", state or "missing"))
            key_r = run(
                [
                    wsl, "-d", wsl_distro, "-e", "bash", "-lc",
                    f"docker exec {container} sh -c 'test -n \"$DEEPSEEK_API_KEY\" && echo set || echo empty' 2>/dev/null",
                ],
                timeout=15,
            )
            key_state = (key_r.stdout or "").strip()
            if key_state == "set":
                items.append(DoctorItem("ok", "hermes", "容器内 DEEPSEEK_API_KEY", "已注入"))
            else:
                items.append(DoctorItem(
                    "fail",
                    "hermes",
                    "容器内 DEEPSEEK_API_KEY 为空",
                    "检查 docker-agents/.env 与 compose env",
                ))
            if chat_probe:
                chat_r = run(
                    [
                        wsl, "-d", wsl_distro, "-e", "bash", "-lc",
                        f"docker exec {container} hermes chat -Q -q '只回复OK' --profile lingzhao 2>&1 | tail -5",
                    ],
                    timeout=90,
                )
                out = (chat_r.stdout or "") + (chat_r.stderr or "")
                if "OK" in out and chat_r.returncode == 0:
                    items.append(DoctorItem("ok", "hermes", "Hermes chat 探针 (DeepSeek)", "lingzhao → OK"))
                else:
                    items.append(DoctorItem(
                        "fail",
                        "hermes",
                        "Hermes chat 探针失败",
                        out.strip()[:200] or f"exit={chat_r.returncode}",
                    ))
    return items


def run_doctor_checks(*, mail_root: Path | None = None, wsl_distro: str = "Ubuntu") -> dict[str, Any]:
    """结构化 doctor 结果 — Dashboard / API / CLI 共用。"""
    load_mailbus_env()
    paths = mailbus_paths()
    root = Path(mail_root) if mail_root else Path(paths["root"])
    items: list[DoctorItem] = []
    plat = detect_platform()

    items.append(DoctorItem("ok", "env", f"platform={plat}", f"MAILBUS_ROOT={paths['root']}"))
    items.append(DoctorItem("ok", "env", f"MAILBUS_DATA={paths['data_dir']}", ""))

    items.extend(check_layout_hazard(repo_parent=root.parent))

    for label, path in (
        ("compose dir", paths["compose_dir"]),
        ("mailbus.py", os.path.join(paths["root"], "tools", "mailbus.py")),
        ("launch_agent.py", os.path.join(paths["root"], "tools", "ops", "launch_agent.py")),
        ("store config", os.path.join(paths["data_dir"], "config.json")),
    ):
        if os.path.exists(path):
            items.append(DoctorItem("ok", "paths", label, path))
        else:
            items.append(DoctorItem("fail", "paths", f"{label} missing", path))

    qdir = os.path.join(paths["run_dir"], "launch-queue")
    if os.path.isdir(qdir):
        items.append(DoctorItem("ok", "paths", "launch-queue", qdir))
    else:
        items.append(DoctorItem("fail", "paths", "launch-queue missing", qdir))

    dstat = docker_status(distro=wsl_distro)
    if dstat["ready"]:
        if dstat["source"] == "wsl":
            items.append(DoctorItem(
                "ok",
                "docker",
                "Docker daemon (WSL)",
                dstat.get("wsl_detail") or wsl_distro,
            ))
        else:
            items.append(DoctorItem("ok", "docker", "Docker daemon", plat))
    else:
        if plat == "win32":
            detail = f"local={dstat['local']}, wsl={dstat['wsl']}"
            if dstat.get("wsl_detail"):
                detail += f" — {dstat['wsl_detail']}"
            items.append(DoctorItem(
                "fail",
                "docker",
                "Docker 不可达（本机与 WSL 均失败）",
                detail + "；请在 WSL 内: sudo service docker start",
            ))
        else:
            items.append(DoctorItem("fail", "docker", "Docker daemon not reachable", plat))

    if dstat["ready"] and plat == "win32" and not dstat["local"]:
        prefix = os.environ.get("MAILBUS_CONTAINER_PREFIX", "docker-agents")
        wsl = wsl_exe()
        if wsl:
            r = run(
                [
                    wsl, "-d", wsl_distro, "-e", "bash", "-lc",
                    f"docker ps --filter name=^{prefix}- --format '{{{{.Names}}}}' 2>/dev/null | head -5",
                ],
                timeout=20,
            )
            names = (r.stdout or "").strip()
            if names:
                items.append(DoctorItem("ok", "docker", "WSL 容器运行中", names.replace("\n", ", ")))
            else:
                items.append(DoctorItem("warn", "docker", "WSL Docker 就绪但无 mailbus 容器", f"prefix={prefix}"))

    api_url = f"http://127.0.0.1:{paths['api_port']}/"
    if probe_http(api_url):
        items.append(DoctorItem("ok", "services", f"mailbus API {api_url}", ""))
    else:
        items.append(DoctorItem("fail", "services", f"mailbus API down: {api_url}", ""))

    try:
        from .service_registry import service_url

        am_url = service_url("agentmemory")
    except Exception:
        am_url = os.environ.get("AGENTMEMORY_URL", "http://127.0.0.1:3111")
    if probe_http(f"{am_url.rstrip('/')}/agentmemory/health") or probe_http(f"{am_url.rstrip('/')}/health"):
        items.append(DoctorItem("ok", "services", f"AgentMemory {am_url}", ""))
    else:
        items.append(DoctorItem("fail", "services", f"AgentMemory unreachable: {am_url}", ""))

    # Drift guard: smart_routing.use_ollama requires agent_types.models.ollama-local
    store_cfg_path = Path(paths["data_dir"]) / "config.json"
    if store_cfg_path.is_file():
        from .utils import json_read

        store_cfg = json_read(str(store_cfg_path), {})
        sr = store_cfg.get("smart_routing") or {}
        use_ollama = sr.get("enabled", True) is not False and sr.get("use_ollama", True) is not False
        has_alias = bool(((store_cfg.get("agent_types") or {}).get("models") or {}).get("ollama-local"))
        if use_ollama and not has_alias:
            from .init_store import ensure_ollama_local_model_alias

            if ensure_ollama_local_model_alias(store_cfg, mail_root=root):
                from .commands import save_config

                save_config(str(store_cfg_path), store_cfg)
                items.append(DoctorItem(
                    "warn",
                    "routing",
                    "已自动合并 agent_types.models.ollama-local（防漂移）",
                    "来自 config/mailbus/agent-types.json",
                ))
            else:
                items.append(DoctorItem(
                    "fail",
                    "routing",
                    "smart_routing.use_ollama 开启但缺少 ollama-local 模型映射",
                    "运行: mailbus init-store merge 或检查 agent-types.json",
                ))
        elif use_ollama and has_alias:
            items.append(DoctorItem("ok", "routing", "agent_types.models.ollama-local 已配置", ""))

    if plat == "win32":
        if probe_http(api_url):
            items.append(DoctorItem("ok", "services", "Windows localhost → mailbus", ""))
        else:
            items.append(DoctorItem("fail", "services", "Windows localhost 无法访问 mailbus", "mailbus portproxy"))

    try:
        from .migrate_ops import manifest_entries

        for entry in manifest_entries(root.parent):
            if entry["optional"]:
                if entry["exists"]:
                    items.append(DoctorItem("ok", "manifest", f"{entry['env']} (optional)", entry["path"]))
                else:
                    items.append(DoctorItem("warn", "manifest", f"optional missing: {entry['env']}", entry["path"]))
            elif not entry["exists"]:
                items.append(DoctorItem("fail", "manifest", f"required {entry['env']} missing", entry["path"]))
            else:
                items.append(DoctorItem("ok", "manifest", entry["env"], entry["path"]))
    except BaseException as exc:
        items.append(DoctorItem("warn", "manifest", "manifest 检查跳过", str(exc)[:120]))

    from .framework_discovery import doctor_framework_lines

    for line in doctor_framework_lines(mail_root=root):
        text = line.strip()
        if text.startswith("OK"):
            items.append(DoctorItem("ok", "frameworks", text[3:].strip(), ""))
        else:
            items.append(DoctorItem("warn", "frameworks", text[5:].strip() if text.startswith("SKIP") else text, ""))

    override = paths.get("compose_override", "")
    if override and os.path.isfile(override):
        items.append(DoctorItem("ok", "compose", "compose override present", override))
    else:
        items.append(DoctorItem("warn", "compose", "compose override missing", "mailbus compose sync"))

    items.extend(check_data_integrity(mail_root=root))
    items.extend(check_locale_transport_codes())
    items.extend(check_hermes_readiness(
        mail_root=root,
        docker_ready_flag=bool(dstat["ready"]),
        wsl_distro=wsl_distro,
        chat_probe=False,
    ))

    fail_count = sum(1 for i in items if i.level == "fail")
    warn_count = sum(1 for i in items if i.level == "warn")
    return {
        "ok": fail_count == 0,
        "platform": plat,
        "docker": dstat,
        "issues": fail_count,
        "warnings": warn_count,
        "items": [i.to_dict() for i in items],
    }


def format_doctor_text(report: dict[str, Any]) -> str:
    lines = [
        f"[doctor] platform={report.get('platform')} issues={report.get('issues')} warnings={report.get('warnings')}",
    ]
    dstat = report.get("docker") or {}
    if dstat:
        lines.append(
            f"[doctor] docker local={dstat.get('local')} wsl={dstat.get('wsl')} ready={dstat.get('ready')} source={dstat.get('source')}"
        )
    for item in report.get("items") or []:
        flag = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}.get(item.get("level"), "?")
        msg = item.get("message", "")
        detail = item.get("detail") or ""
        cat = item.get("category", "")
        suffix = f" — {detail}" if detail else ""
        lines.append(f"  {flag} [{cat}] {msg}{suffix}")
    lines.append(f"[doctor] done — {report.get('issues', 0)} issue(s)")
    return "\n".join(lines)


def doctor_exit_code(report: dict[str, Any]) -> int:
    return 1 if int(report.get("issues") or 0) > 0 else 0
