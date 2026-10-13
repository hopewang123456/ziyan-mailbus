"""FrameworkSpec — 框架声明式 descriptor（单一事实源）。

新增框架的接入知识一律先落 FRAMEWORKS（本模块），各消费方从 descriptor
派生自己的视图，不再各自维护 per-framework 表：

- config_schema.AGENT_TYPES          config/config_schema.py（schema enum + 运行时校验）
- config_admin.AGENT_TYPE_META       config/config_admin.py（web 配置页下拉）
- access_adapters.FRAMEWORK_ACCESS_DIR   access/{dir}/ 目录映射
- init_store.DEFAULT_MODELS          init-store 生成 agent 卡默认模型
- native_scan._IDENTITY_FILENAME     原生身份文件扫描
- file_task_push.FILE_TASK_AGENT_TYPES   工单推送集合
- platform_probe.WindowsProbe.CLI_BIN_NAMES  probe 二进制名
- framework_discovery.FRAMEWORK_RUN_TARGETS  运行端适用性矩阵
- registry.DOCKER_SERVICE_TYPE       compose 服务名 → type

行为类知识（Adapter 类的 build_push_cli 等）仍在 registry.py；本模块只收敛
数据。Adapter 类属性与 spec 的一致性由 tests/test_framework_spec.py 钉死。

放 lib/infra 的原因：config 包（access_adapters 等）与 frameworks 包
（registry 等）互有依赖，若本模块放 frameworks 会经 frameworks/__init__
→ registry → access_adapters 构成 import 环；infra 是两者共同的底层
（registry 本就 import lib.infra.agent_demo 的框架数据），application 层
import infra 也不违反分层守卫。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameworkSpec:
    type_name: str
    label: str                        # UI 显示名（config_admin.AGENT_TYPE_META）
    note: str = ""                    # UI 备注
    container_service: str = ""       # docker compose 服务名（BaseAdapter 同名属性）
    docker_services: tuple[str, ...] = ()   # 反向映射 DOCKER_SERVICE_TYPE 的来源
    cli_bin: str = ""                 # probe 二进制名；空 = 与 type_name 相同
    identity_filename: str = ""       # 原生目录身份文件名；空 = 无原生身份扫描
    access_dir: str = ""              # access/{dir}/ 子目录；空 = 无 adapter SPEC
    default_models: tuple[str, ...] = ()   # init-store 默认模型；空 = 不生成默认
    run_targets: tuple[str, ...] = ("windows",)  # 运行端适用性；空 = 不进矩阵（走默认兜底）
    file_task: bool = False           # 可执行任务走 msg-files 工单 + msg-results 验收
    supports_auto_ack: bool = False
    mark_processing_on_task_push: bool = False
    allow_no_push_cli: bool = False   # 无 CLI 也可投递（file_bus / A2A 降级）
    in_agent_types: bool = True       # 是否进 config_schema.AGENT_TYPES（a2a_remote 仅运行时）
    # resolve_push_cli 的 kwargs 分派声明（registry 按此传参，不再 per-type 特判）：
    # pass_pipeline=True → build_push_cli(..., pipeline=pipeline)（CodexAdapter 沙箱双路）
    pass_pipeline: bool = False
    # needs_data_dir=True → data_dir 非空时 build_push_cli(..., data_dir=data_dir)
    # （CLI 解析要读 store config 的框架：claude_code / zcode）
    needs_data_dir: bool = False


FRAMEWORKS: dict[str, FrameworkSpec] = {
    spec.type_name: spec
    for spec in (
        FrameworkSpec(
            type_name="hermes",
            label="Hermes Agent",
            note="统一 Hermes 容器",
            container_service="hermes",
            cli_bin="hermes",
            identity_filename="SOUL.md",
            access_dir="hermes",
            run_targets=("windows", "wsl", "linux", "docker"),
            supports_auto_ack=True,
            mark_processing_on_task_push=True,
        ),
        FrameworkSpec(
            type_name="hermes_profile",
            label="Hermes Profile",
            note="Hermes --profile 多角色",
            container_service="hermes",
            docker_services=("hermes",),
            cli_bin="hermes",
            identity_filename="SOUL.md",
            access_dir="hermes",
            default_models=("deepseek-flash",),
            run_targets=("windows", "wsl", "linux", "docker"),
            supports_auto_ack=True,
            mark_processing_on_task_push=True,
        ),
        FrameworkSpec(
            type_name="openclaw",
            label="OpenClaw Gateway",
            note="OpenClaw 本地 Gateway",
            container_service="openclaw",
            docker_services=("openclaw",),
            identity_filename="SOUL.md",
            access_dir="openclaw",
            default_models=("deepseek-flash",),
            run_targets=("windows", "wsl", "linux", "docker"),
            supports_auto_ack=True,
        ),
        FrameworkSpec(
            type_name="cline",
            label="Cline CLI",
            note="类 Claude Code 工作流 · codex 容器",
            container_service="codex-web",
            identity_filename="CLAUDE.md",
            access_dir="cline",
            run_targets=("windows", "wsl", "linux"),
            file_task=True,
            mark_processing_on_task_push=True,
        ),
        FrameworkSpec(
            type_name="opencode",
            label="OpenCode CLI",
            note="OpenCode run · opencode 容器",
            container_service="opencode",
            docker_services=("opencode",),
            identity_filename="SOUL.md",
            access_dir="opencode",
            default_models=("deepseek-flash", "qwen-max", "zhipu-4"),
            run_targets=("windows", "wsl", "linux", "docker"),
            file_task=True,
            mark_processing_on_task_push=True,
        ),
        FrameworkSpec(
            type_name="codex",
            label="Codex CLI",
            note="codex exec · codex Docker",
            container_service="codex-web",
            docker_services=("codex-web", "codex-review"),
            identity_filename="IDENTITY.md",
            access_dir="codex",
            default_models=("deepseek-flash",),
            run_targets=("windows", "wsl", "linux", "docker"),
            file_task=True,
            mark_processing_on_task_push=True,
            pass_pipeline=True,
        ),
        FrameworkSpec(
            type_name="claude_code",
            label="Claude Code CLI",
            note="宿主机 claude -p · Windows/Linux 可选",
            cli_bin="claude",
            identity_filename="CLAUDE.md",
            access_dir="claude_code",
            default_models=("deepseek-flash",),
            run_targets=("windows", "wsl", "linux"),
            file_task=True,
            mark_processing_on_task_push=True,
            needs_data_dir=True,
        ),
        FrameworkSpec(
            type_name="zcode",
            label="ZCode CLI",
            note="宿主机 zcode -p · GLM 后端（Z.AI OAuth）",
            identity_filename="AGENTS.md",
            access_dir="zcode",
            default_models=("glm",),
            run_targets=("windows",),
            file_task=True,
            mark_processing_on_task_push=True,
            needs_data_dir=True,
        ),
        FrameworkSpec(
            type_name="cursor",
            label="Cursor",
            note="Windows Cursor IDE / cursor-agent CLI",
            identity_filename="CLAUDE.md",
            access_dir="cursor",
            run_targets=("windows",),
            mark_processing_on_task_push=True,
            allow_no_push_cli=True,
        ),
        FrameworkSpec(
            type_name="dsh",
            label="DeepSeek Harness",
            note="dsh headless · mailbus-dsh 容器",
            container_service="dsh",
            docker_services=("dsh",),
            identity_filename="SOUL.md",
            run_targets=("docker",),
            mark_processing_on_task_push=True,
        ),
        FrameworkSpec(
            type_name="a2a_remote",
            label="A2A Remote",
            note="HTTP A2A 远端 agent（仅运行时注册，不进 config enum）",
            run_targets=(),
            allow_no_push_cli=True,
            in_agent_types=False,
        ),
        FrameworkSpec(
            type_name="none",
            label="纯文件",
            note="无 CLI 推送",
            allow_no_push_cli=True,
        ),
    )
}


def spec_for(framework: str) -> FrameworkSpec | None:
    """按 type 名取 descriptor（未知框架返回 None）。"""
    return FRAMEWORKS.get((framework or "").strip().lower())


def file_task_agent_types() -> frozenset[str]:
    """内置框架的工单推送静态集（模块级固化消费方用）。

    外部框架（store/frameworks/*.json，in_agent_types=False）不进静态集；
    运行时判定走 FRAMEWORKS 直查（file_task_push._uses_file_task）。
    """
    return frozenset(
        fw for fw, spec in FRAMEWORKS.items()
        if spec.file_task and spec.in_agent_types
    )
