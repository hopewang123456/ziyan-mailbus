"""外部框架 descriptor 加载（W2 配置化接入通道）。

store/frameworks/*.json = 零代码接入的载体：一个 JSON 声明一个 CLI 推送型
框架（FrameworkSpec 字段 + push_template），加载后自动获得：

- config type 校验放行（validate_config 按 FRAMEWORKS 运行时键集）
- TemplateAdapter（push 模板构建 shell 命令，'MSG' 占位符由 pusher 替换）
- file_task / probe / UI meta 等一切 FRAMEWORKS 派生视图

与 Python 插件（entry_point_discovery，module/entry-point）互补：JSON 是
数据域（无代码），Python 插件是行为域（怪癖 hook）。加载入口统一挂
ensure_framework_plugins_loaded，serve 与 CLI scan 两条路径都会触发。

单文件失败隔离（毒文件不炸全局，P11 教训）；重复加载幂等跳过。
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from lib.adapters.frameworks.registry import (
    BaseAdapter,
    model_flag,
    register_framework,
)
from lib.infra.framework_spec import FRAMEWORKS, FrameworkSpec

# JSON descriptor 允许的字段（FrameworkSpec 投影 + 模板字段）。
_ALLOWED_FIELDS = {
    "type_name", "label", "note", "cli_bin", "identity_filename",
    "access_dir", "default_models", "run_targets", "file_task",
    "supports_auto_ack", "mark_processing_on_task_push", "allow_no_push_cli",
    "push_template", "interactive_template", "push_argv",
}
_REQUIRED_FIELDS = ("type_name", "label", "push_template")


class TemplateAdapter(BaseAdapter):
    """通用模板适配器——纯配置框架的 Adapter（无专属类）。

    push_template 约定与 agent_types.push 模板一致：'MSG' 占位符留给
    pusher 做 shell 转义替换；MODEL/PROFILE/AGENT 在此替换（无 model
    配置时清掉 '--model MODEL' 残段）。
    """

    def __init__(self, spec: FrameworkSpec, push_template: str, interactive_template: str = ""):
        self.spec = spec
        self.type_name = spec.type_name
        self.container_service = spec.container_service
        self.supports_auto_ack = spec.supports_auto_ack
        self.mark_processing_on_task_push = spec.mark_processing_on_task_push
        self.allow_no_push_cli = spec.allow_no_push_cli
        self.push_template = push_template
        self.interactive_template = interactive_template

    def build_push_cli(
        self,
        agent_name: str,
        agent_cfg: dict,
        agent_types: dict,
        model_alias: Optional[str] = None,
    ) -> str:
        cmd = self.push_template
        profile = agent_cfg.get("profile", "") or agent_cfg.get("agent", "")
        cmd = cmd.replace("PROFILE", profile).replace("AGENT", agent_cfg.get("agent", ""))
        mflag = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        if mflag:
            # mflag 是完整 flag 串（"--model X"）：先替换长形态 '--model MODEL'
            # 再替换裸 'MODEL'，避免嵌套出 '--model --model X'。
            cmd = cmd.replace("--model MODEL", mflag).replace("MODEL", mflag)
        else:
            cmd = cmd.replace("--model MODEL", "").replace("MODEL", "")
        return cmd

    def build_interactive_cli(
        self,
        agent_name: str,
        agent_cfg: dict,
        agent_types: dict,
    ) -> str:
        return self.interactive_template

    def cli_active_in_ps(self, agent_name: str, agent_cfg: dict, ps_output: str) -> bool:
        # 外部框架按声明二进制名匹配进程；未声明则视为不活跃（scan 保守重推语义）
        return bool(self.spec.cli_bin) and self.spec.cli_bin.lower() in (ps_output or "").lower()

    def validate(self, agent_name: str, agent_cfg: dict) -> list[str]:
        return []


def _load_descriptor_file(path: str) -> dict[str, Any]:
    """读取并校验单个 descriptor JSON——读端比写端严（G10 教训）。"""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("descriptor 须为 JSON object")
    unknown = set(data) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"未知字段: {sorted(unknown)}")
    for field in _REQUIRED_FIELDS:
        if not str(data.get(field) or "").strip():
            raise ValueError(f"缺少必填字段: {field}")
    return data


def _argv_direct_builder(push_argv: list[str]):
    """按 push_argv 声明构建 subprocess 直启规格（不经 shell，零转义）。

    argv 元素 "{MSG}" 为完整推送文本槽位（长消息/reply_format JSON 的唯一
    可靠通道——Windows shell 路径的引号转义会截断复杂文本）；cwd 取
    agent 卡 push.cwd（未配则 None 走进程当前目录）。
    """

    def _build(
        agent_name: str,
        agent_cfg: dict,
        agent_types: dict,
        *,
        data_dir: str = "",
        prompt: str = "",
        model_name: str | None = None,
        pipeline: bool = False,
    ) -> dict | None:
        from lib.adapters.frameworks.registry import _push_cwd

        argv = [prompt if el == "{MSG}" else el for el in push_argv]
        if not prompt and "{MSG}" in push_argv:
            return None
        return {"argv": argv, "env": {}, "cwd": _push_cwd(agent_cfg) or None}

    return _build


def load_external_frameworks(data_dir: str, *, force: bool = False) -> list[dict[str, Any]]:
    """扫描 {data_dir}/frameworks/*.json 并注册（幂等）。

    返回每个文件的处理结果（含失败原因），单个文件失败不阻断其余。
    """
    results: list[dict[str, Any]] = []
    if not data_dir:
        return results
    folder = os.path.join(data_dir, "frameworks")
    if not os.path.isdir(folder):
        return results
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(folder, fname)
        row: dict[str, Any] = {"file": fname}
        try:
            data = _load_descriptor_file(path)
            tname = str(data["type_name"]).strip().lower()
            row["type_name"] = tname
            if tname in FRAMEWORKS and not force:
                row.update(ok=True, skipped=True, reason="already_registered")
                results.append(row)
                continue
            spec = FrameworkSpec(
                type_name=tname,
                label=str(data["label"]),
                note=str(data.get("note") or ""),
                cli_bin=str(data.get("cli_bin") or ""),
                identity_filename=str(data.get("identity_filename") or ""),
                access_dir=str(data.get("access_dir") or ""),
                default_models=tuple(data.get("default_models") or ()),
                run_targets=tuple(data.get("run_targets") or ("windows",)),
                file_task=bool(data.get("file_task")),
                supports_auto_ack=bool(data.get("supports_auto_ack")),
                mark_processing_on_task_push=bool(data.get("mark_processing_on_task_push")),
                allow_no_push_cli=bool(data.get("allow_no_push_cli")),
                # 外部框架不进静态派生视图（AGENT_TYPES/META 是 import 时固化的
                # 内置集）；config type 校验由 validate_config 按 FRAMEWORKS
                # 运行时键集放行，与 in_agent_types 无关。
                in_agent_types=False,
            )
            adapter = TemplateAdapter(
                spec,
                push_template=str(data["push_template"]),
                interactive_template=str(data.get("interactive_template") or ""),
            )
            register_framework(tname, adapter, replace=force)
            FRAMEWORKS[tname] = spec
            push_argv = [str(x) for x in (data.get("push_argv") or []) if str(x).strip()]
            if push_argv:
                from lib.adapters.frameworks.direct_push import register_direct_builder

                register_direct_builder(
                    tname, _argv_direct_builder(push_argv), replace=force,
                )
            row.update(ok=True, skipped=False)
        except Exception as exc:  # 毒文件隔离：记录并继续
            row.update(ok=False, error=str(exc))
        results.append(row)
    return results
