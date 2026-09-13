"""Mailbus 诊断检查 — 供 mailbus doctor、Dashboard 诊所、CLI 工具共用。"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.env_bootstrap import load_mailbus_env, mailbus_paths
from lib.infra.agent_demo import hermes_demo_agents
from lib.adapters.plane.platform_runner import detect_platform, docker_ready, probe_http, run, wsl_exe

Level = Literal["ok", "warn", "fail"]

# 恢复/迁移后必须存在的关键路径（相对 MAILBUS_ROOT）— Wave1+ 新布局
_CRITICAL_FILES = (
    "tools/mailbus.py",
    "tools/generate-compose-volumes.py",
    "lib/composition.py",
    "lib/infra/constants.py",
    "lib/infra/env_bootstrap.py",
    "lib/adapters/config/agent_registry.py",
    "lib/adapters/config/init_store.py",
    "lib/adapters/frameworks/framework_discovery.py",
    "lib/interfaces/message_transport.py",
    "lib/core/a2a/__init__.py",
    "migrate/manifest.yaml",
    "migrate/bundle_import.py",
    "pyproject.toml",
    "config/mailbus/base.json",
    "config/frameworks/registry.json",
    "docker-agents/docker-compose.yml",
    "bus/__main__.py",
    "ARCHITECTURE.md",
    "AGENTS.md",
)

_EXPECTED_TRANSPORT_AGENTS = ()  # personal roster is local-only; see examples/transport/

_THIN_DIRS_WARN_BELOW = {
    "access/hermes": 2,
    "skills": 30,
    # overrides are personal (*.override.json); examples live as *.override.example.json
}


_DEMO_HERMES_AGENTS = tuple(hermes_demo_agents()) or ("agent-a", "agent-b", "agent-c", "agent-d")


def expected_hermes_agents(data_dir: str) -> list[str]:
    """config.json 中 hermes_profile 类型 agents；缺失时回落到 demo 名单。"""
    import json

    cfg_path = os.path.join(data_dir, "config.json")
    try:
        if os.path.isfile(cfg_path):
            cfg = json.load(open(cfg_path, encoding="utf-8"))
            agents = [
                aid for aid, ac in (cfg.get("agents") or {}).items()
                if (ac.get("type") or "").strip() == "hermes_profile"
            ]
            if agents:
                return agents
    except (OSError, json.JSONDecodeError):
        pass
    return list(_DEMO_HERMES_AGENTS)


@dataclass
class DoctorItem:
    level: Level
    category: str
    message: str
    detail: str = ""
    layer: str = "core"

    def to_dict(self) -> dict[str, str]:
        d = asdict(self)
        d["layer"] = CATEGORY_LAYERS.get(self.category, self.layer)
        return d


# 分层健康：core（必需，红/绿）· host（宿主机执行，容器内不误红）· integrations（可选，未配置灰/黄）
CATEGORY_LAYERS = {
    "docker": "host",
    "compose": "host",
    "hermes": "host",
    "frameworks": "host",
    "agentmemory": "integrations",
    "n8n": "integrations",
    "comfyui": "integrations",
    "ollama": "integrations",
    "integrations": "integrations",
    "auth": "core",
    "config": "core",
}


def _cidr_is_overbroad(cidr: str) -> bool:
    """0.0.0.0/0、::/0 或任何 prefixlen==0 的网段视为过宽。"""
    import ipaddress

    text = (cidr or "").strip()
    if not text:
        return False
    if text in ("0.0.0.0/0", "::/0"):
        return True
    try:
        return ipaddress.ip_network(text, strict=False).prefixlen == 0
    except ValueError:
        return False


def check_auth_hardening(config: dict | None = None, *, data_dir: str = "") -> list[DoctorItem]:
    """鉴权硬化：过宽无 Token 写 CIDR、OpenClaw 默认 change-me。"""
    items: list[DoctorItem] = []
    cfg = config if isinstance(config, dict) else {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}

    cidrs: list[str] = []
    for key in ("write_without_token_cidrs", "exempt_cidrs"):
        raw = auth.get(key)
        if raw is None and key == "exempt_cidrs":
            raw = cfg.get("exempt_cidrs")
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.replace(";", "\n").splitlines() if x.strip()]
        if isinstance(raw, list):
            cidrs.extend(str(x).strip() for x in raw if str(x).strip())

    bad = sorted({c for c in cidrs if _cidr_is_overbroad(c)})
    if bad:
        items.append(
            DoctorItem(
                "fail",
                "auth",
                "无 Token 写 CIDR 过宽（公网级）",
                f"拒绝: {', '.join(bad)}；请在设置→鉴权收窄网段",
            )
        )
    elif auth.get("allow_write_without_token"):
        items.append(
            DoctorItem(
                "ok",
                "auth",
                "无 Token 写已开启且 CIDR 未过宽",
                f"{len(cidrs)} 条 CIDR" if cidrs else "空列表=仅 loopback 默认",
            )
        )
    else:
        items.append(DoctorItem("ok", "auth", "写 API 默认要求 Token", "allow_write_without_token=false"))

    agents = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else {}
    openclaw_ids = [
        aid
        for aid, ac in agents.items()
        if isinstance(ac, dict)
        and (ac.get("type") or "").strip() == "openclaw"
        and ac.get("enabled", True) is not False
    ]
    env_tok = (os.environ.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    if openclaw_ids:
        try:
            from lib.adapters.config.browser_auth import openclaw_gateway_token

            resolved = (openclaw_gateway_token() or "").strip()
        except Exception:
            resolved = env_tok
        if not resolved or resolved == "change-me":
            items.append(
                DoctorItem(
                    "fail",
                    "auth",
                    "OpenClaw Gateway Token 未配置或仍为无效默认",
                    f"agents={', '.join(openclaw_ids[:6])}；请在设置/密钥配置 OPENCLAW_GATEWAY_TOKEN",
                )
            )
        else:
            items.append(
                DoctorItem(
                    "ok",
                    "auth",
                    "OpenClaw Gateway Token 已配置",
                    f"agents={len(openclaw_ids)}",
                )
            )
    elif env_tok == "change-me":
        items.append(
            DoctorItem(
                "warn",
                "auth",
                "OPENCLAW_GATEWAY_TOKEN=change-me（当前无启用的 openclaw agent）",
                "上线前请轮换真实 token",
            )
        )

    cors_raw = auth.get("cors_origins") or cfg.get("cors_origins") or []
    if isinstance(cors_raw, str):
        cors_list = [x.strip() for x in cors_raw.replace(";", ",").split(",") if x.strip()]
    elif isinstance(cors_raw, list):
        cors_list = [str(x).strip() for x in cors_raw if str(x).strip()]
    else:
        cors_list = []
    if "*" in cors_list:
        items.append(
            DoctorItem(
                "warn",
                "auth",
                "CORS 白名单含 *（反射任意 Origin）",
                "设置→鉴权改为显式 Origin；空列表=不跨域放行",
            )
        )
    elif cors_list:
        items.append(
            DoctorItem(
                "ok",
                "auth",
                f"CORS 白名单 {len(cors_list)} 条",
                "",
            )
        )
    else:
        items.append(DoctorItem("ok", "auth", "CORS 未开放跨域（无 *）", "cors_origins 为空"))

    return items


def check_config_hygiene(config: dict | None = None) -> list[DoctorItem]:
    """配置卫生：空链路模板等（warn，不阻断 doctor ok）。"""
    items: list[DoctorItem] = []
    cfg = config if isinstance(config, dict) else {}
    chains = cfg.get("mailbus_chains") if isinstance(cfg.get("mailbus_chains"), dict) else {}
    templates = chains.get("templates") if isinstance(chains.get("templates"), list) else []
    valid = [t for t in templates if isinstance(t, dict) and str(t.get("id") or "").strip()]
    if not valid:
        items.append(
            DoctorItem(
                "warn",
                "config",
                "mailbus_chains 无有效链路模板",
                "设置→总线→路由/端口→链路 添加模板，或参考 config/mailbus/chains.template.json",
            )
        )
    else:
        items.append(
            DoctorItem(
                "ok",
                "config",
                f"mailbus_chains 模板 {len(valid)} 个",
                f"daily_budget_cny={chains.get('daily_budget_cny', '—')}",
            )
        )
    return items


def check_mail_path_alias_sunset(config: dict | None = None) -> list[DoctorItem]:
    """探测配置中仍写 mail/ 前缀的路径；兼容期 warn，鼓励改 mailbus/。"""
    items: list[DoctorItem] = []
    cfg = config if isinstance(config, dict) else {}
    blob = ""
    try:
        import json as _json

        blob = _json.dumps(cfg, ensure_ascii=False)
    except Exception:
        blob = str(cfg)
    # 避免误伤 mailbus/ 与 mailbus_ 键名：只计 "mail/skills" "mail/rules" "mail/adapters" 等
    markers = ("mail/skills/", "mail/rules/", "mail/adapters/", '"mail/skills', '"mail/rules')
    hits = [m for m in markers if m in blob]
    if hits:
        items.append(
            DoctorItem(
                "warn",
                "config",
                "配置仍含废弃路径前缀 mail/…",
                f"命中 {', '.join(hits[:3])}；请改为 mailbus/…（兼容期至 2026-12-31）",
            )
        )
    else:
        items.append(DoctorItem("ok", "config", "无 mail/ 技能·规则旧前缀", "sunset 2026-12-31"))
    return items


def check_asset_path_env_conflict(config: dict | None = None) -> list[DoctorItem]:
    """config.asset_paths 自定义与 MAILBUS_*_ROOT env 双源时提示。"""
    items: list[DoctorItem] = []
    cfg = config if isinstance(config, dict) else {}
    stored = cfg.get("asset_paths") if isinstance(cfg.get("asset_paths"), dict) else {}
    env_keys = (
        ("skills", "MAILBUS_SKILLS_ROOT"),
        ("rules", "MAILBUS_RULES_ROOT"),
        ("identities", "MAILBUS_IDENTITIES_ROOT"),
    )
    conflicts: list[str] = []
    for key, env_name in env_keys:
        block = stored.get(key) if isinstance(stored.get(key), dict) else {}
        mode = str(block.get("mode") or "default")
        custom = str(block.get("path") or block.get("custom") or "").strip()
        env_val = (os.environ.get(env_name) or "").strip()
        if mode == "custom" and custom and env_val:
            # normalize light compare
            if os.path.normcase(os.path.normpath(env_val)) != os.path.normcase(os.path.normpath(custom)):
                conflicts.append(f"{key}: config={custom} vs {env_name}={env_val}")
        elif mode == "default" and env_val:
            # env set while config says default — env may still win at process boot
            conflicts.append(f"{key}: asset_paths=default 但 {env_name} 仍设置")
    if conflicts:
        items.append(
            DoctorItem(
                "warn",
                "config",
                "资产路径 config 与 env 双源冲突",
                "; ".join(conflicts[:3]) + ("…" if len(conflicts) > 3 else ""),
            )
        )
    else:
        items.append(DoctorItem("ok", "config", "资产路径无 config/env 冲突", ""))
    return items


_COMPOSE_COUPLING_MARKERS = (
    "ai_tools/Agent",
    "ai_tools\\Agent",
    "../../Agent/docker",
    "..\\..\\Agent\\docker",
    "/mnt/e/ai_tools/Agent",
    "../openclaw_space",
    "../opencode",
    ":-change-me",
    "OPENCLAW_GATEWAY_TOKEN:-change-me",
)


def check_compose_coupling(*, mail_root: Path | None = None) -> list[DoctorItem]:
    """compose / entrypoint 不得再默认兄弟仓路径或 change-me。"""
    items: list[DoctorItem] = []
    root = Path(mail_root) if mail_root else Path(MAILBUS_ROOT)
    targets = [
        root / "docker-agents" / "docker-compose.yml",
        root / "docker-agents" / "compose.public.yml",
        root / "docker-agents" / "openclaw-agent" / "entrypoint.sh",
    ]
    any_file = False
    for path in targets:
        if not path.is_file():
            continue
        any_file = True
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            items.append(DoctorItem("warn", "compose", f"无法读取 {path.name}", str(exc)[:120]))
            continue
        hits = [m for m in _COMPOSE_COUPLING_MARKERS if m in text]
        # entrypoint 里「change-me」作为拒绝分支字符串可保留；仅拦默认赋值
        if path.name == "entrypoint.sh":
            hits = [m for m in hits if m != ":-change-me"]
            if 'OPENCLAW_GATEWAY_TOKEN:-change-me' in text or '${OPENCLAW_GATEWAY_TOKEN:-change-me}' in text:
                hits.append("OPENCLAW_GATEWAY_TOKEN:-change-me")
            # 显式默认：TOKEN="${...:-change-me}"
            if ':-change-me}"' in text or ":-change-me}'" in text:
                if "OPENCLAW_GATEWAY_TOKEN:-change-me" not in hits:
                    hits.append("default-change-me")
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
        if hits:
            items.append(
                DoctorItem(
                    "fail",
                    "config",
                    f"{rel} 仍含耦合默认",
                    f"命中: {', '.join(hits[:4])}",
                )
            )
        else:
            items.append(
                DoctorItem(
                    "ok",
                    "compose",
                    f"{rel} 无 ai_tools/Agent / change-me 硬默认",
                    "",
                )
            )
    if not any_file:
        items.append(DoctorItem("warn", "compose", "未找到 docker-compose.yml", str(root / "docker-agents")))

    override = root / "docker-agents" / "docker-compose.override.yml"
    if override.is_file():
        try:
            ot = override.read_text(encoding="utf-8")
        except OSError:
            ot = ""
        if any(m in ot for m in _COMPOSE_COUPLING_MARKERS):
            items.append(
                DoctorItem(
                    "warn",
                    "compose",
                    "本机 override.yml 含兄弟仓硬编码路径",
                    "改为 ${OPENCLAW_WORKSPACE} 等变量；绝对路径只写 docker-agents/.env / 设置页",
                )
            )

    env_file = root / "docker-agents" / ".env"
    if env_file.is_file():
        try:
            et = env_file.read_text(encoding="utf-8")
        except OSError:
            et = ""
        # .env 指向 Agent 绝对路径 = 合法「配置关联」，不算耦合。
        # 仅当仍用相对兄弟仓默认（../../Agent/docker）时告警。
        rel_hits = [
            m
            for m in ("../../Agent/docker", "..\\..\\Agent\\docker", ":-change-me")
            if m in et
        ]
        if rel_hits:
            items.append(
                DoctorItem(
                    "warn",
                    "compose",
                    "docker-agents/.env 含相对 Agent/docker 或 change-me 默认",
                    "改为显式绝对路径（设置页 / .env），勿依赖相对兄弟仓",
                )
            )
        else:
            items.append(
                DoctorItem(
                    "ok",
                    "compose",
                    "docker-agents/.env 用显式路径关联（允许指向本机 Agent 树）",
                    "",
                )
            )
    return items


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
        from lib.adapters.locale.errors_zh import stable_codes_covered, transport_codes_covered

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
            f"{hermes_data}；典型路径 <HERMES_DATA>/.hermes",
        ))

    sync_root = root / "access" / "hermes" / ".sync"
    missing_sync = [
        a for a in expected_hermes_agents(paths["data_dir"])
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
                probe_agent = (expected_hermes_agents(paths["data_dir"]) or list(_DEMO_HERMES_AGENTS))[0]
                chat_r = run(
                    [
                        wsl, "-d", wsl_distro, "-e", "bash", "-lc",
                        f"docker exec {container} hermes chat -Q -q '只回复OK' --profile {probe_agent} 2>&1 | tail -5",
                    ],
                    timeout=90,
                )
                out = (chat_r.stdout or "") + (chat_r.stderr or "")
                if "OK" in out and chat_r.returncode == 0:
                    items.append(DoctorItem("ok", "hermes", "Hermes chat 探针 (DeepSeek)", f"{probe_agent} → OK"))
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
    api_headers: dict[str, str] = {}
    try:
        from lib.adapters.config.token_store import resolve_token

        tok = resolve_token(str(paths.get("data_dir") or "store"))
        if tok:
            api_headers["Authorization"] = f"Bearer {tok}"
    except Exception:
        pass
    # Reachable if 200 with token, or 401 without — both mean the API process is up
    if probe_http(api_url, headers=api_headers) or probe_http(
        api_url, accept_codes=frozenset({200, 401})
    ):
        items.append(DoctorItem("ok", "services", f"mailbus API {api_url}", ""))
    else:
        items.append(DoctorItem("fail", "services", f"mailbus API down: {api_url}", ""))

    try:
        from .service_registry import service_url

        am_url = service_url("agentmemory")
    except Exception:
        am_url = os.environ.get("AGENTMEMORY_URL", "http://127.0.0.1:3111")
    if probe_http(f"{am_url.rstrip('/')}/agentmemory/health") or probe_http(f"{am_url.rstrip('/')}/health"):
        items.append(DoctorItem("ok", "agentmemory", f"AgentMemory {am_url}", ""))
    else:
        items.append(DoctorItem("warn", "agentmemory", f"AgentMemory 未配置或不可达: {am_url}", "可选集成；未配置不影响 Core"))

    # Drift guard: smart_routing.use_ollama requires agent_types.models.ollama-local
    store_cfg_path = Path(paths["data_dir"]) / "config.json"
    if store_cfg_path.is_file():
        from lib.infra.utils import json_read

        store_cfg = json_read(str(store_cfg_path), {})
        sr = store_cfg.get("smart_routing") or {}
        use_ollama = sr.get("enabled", True) is not False and sr.get("use_ollama", True) is not False
        has_alias = bool(((store_cfg.get("agent_types") or {}).get("models") or {}).get("ollama-local"))
        if use_ollama and not has_alias:
            from lib.adapters.config.init_store import ensure_ollama_local_model_alias

            if ensure_ollama_local_model_alias(store_cfg, mail_root=root):
                from lib.infra.utils import json_write as _save_config

                _save_config(str(store_cfg_path), store_cfg)
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

        items.extend(check_auth_hardening(store_cfg, data_dir=str(paths["data_dir"])))
        items.extend(check_config_hygiene(store_cfg))
        items.extend(check_mail_path_alias_sunset(store_cfg))
        items.extend(check_asset_path_env_conflict(store_cfg))
        items.extend(check_compose_coupling(mail_root=root))
    else:
        items.extend(check_auth_hardening({}, data_dir=str(paths.get("data_dir") or "")))
        items.extend(check_config_hygiene({}))
        items.extend(check_mail_path_alias_sunset({}))
        items.extend(check_asset_path_env_conflict({}))
        items.extend(check_compose_coupling(mail_root=root))

    if plat == "win32":
        if probe_http(api_url, headers=api_headers) or probe_http(
            api_url, accept_codes=frozenset({200, 401})
        ):
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

    from lib.adapters.frameworks.framework_discovery import doctor_framework_lines

    for line in doctor_framework_lines(mail_root=root):
        text = line.strip()
        if text.startswith("OK"):
            items.append(DoctorItem("ok", "frameworks", text[3:].strip(), ""))
        else:
            items.append(DoctorItem("warn", "frameworks", text[5:].strip() if text.startswith("SKIP") else text, ""))

    # 平台适配器实例探测：按当前启动平台（win32/wsl/linux/docker）校验各框架实例
    from lib.adapters.ops.platform_probe import get_platform_probe

    try:
        store_cfg = json_read(str(Path(paths["data_dir"]) / "config.json"), {}) if (Path(paths["data_dir"]) / "config.json").is_file() else {}
    except Exception:
        store_cfg = {}
    probe_adapter = get_platform_probe()
    probes = probe_adapter.probe_all(store_cfg)
    if probes:
        ok_probes = [p for p in probes if p.ok]
        fail_probes = [p for p in probes if not p.ok]
        found_detail = ", ".join(f"{p.instance}:{p.platform}" for p in ok_probes[:8]) or "无"
        if fail_probes:
            missing_detail = ", ".join(p.instance for p in fail_probes[:8]) + ("…" if len(fail_probes) > 8 else "")
            items.append(DoctorItem(
                "warn",
                "frameworks",
                f"平台适配器探测: {len(ok_probes)}/{len(probes)} 实例可用 ({probe_adapter.platform_name})",
                f"可用 {found_detail}；缺失 {missing_detail}",
            ))
        else:
            items.append(DoctorItem(
                "ok",
                "frameworks",
                f"平台适配器探测: {len(probes)} 实例均可用 ({probe_adapter.platform_name})",
                found_detail,
            ))

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

    def _layer_of(i: DoctorItem) -> str:
        return CATEGORY_LAYERS.get(i.category, i.layer or "core")

    core_fail = sum(1 for i in items if i.level == "fail" and _layer_of(i) == "core")
    host_fail = sum(1 for i in items if i.level == "fail" and _layer_of(i) == "host")
    integ_fail = sum(1 for i in items if i.level == "fail" and _layer_of(i) == "integrations")
    fail_count = core_fail
    warn_count = sum(1 for i in items if i.level == "warn") + host_fail + integ_fail
    return {
        "ok": fail_count == 0,
        "platform": plat,
        "docker": dstat,
        "issues": fail_count,
        "warnings": warn_count,
        "layers": {
            "core": {"issues": core_fail},
            "host": {"issues": host_fail},
            "integrations": {"issues": integ_fail},
        },
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
