"""FrameworkSpec 完整性校验（W1 契约收敛）。

FRAMEWORKS（lib/infra/framework_spec.py）是框架接入知识的单一事实源，
9 处消费方全部派生自它。本测试做两件事：

1. 金标准：把迁移时（2026-10-11）各消费方原表的值钉死在此——descriptor
   漏填/错填字段立即红，防止「接新框架忘改某一处」的事故复发；
2. 一致性：registry.py Adapter 类属性与 spec 字段必须同步（双写漂移即红）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.infra.framework_spec import FRAMEWORKS, FrameworkSpec, file_task_agent_types


class TestSpecCompleteness(unittest.TestCase):
    def test_every_spec_has_label_and_note(self):
        for fw, spec in FRAMEWORKS.items():
            self.assertTrue(spec.type_name, fw)
            self.assertTrue(spec.label, f"{fw}: label 必填")
            if spec.in_agent_types:
                self.assertTrue(spec.note, f"{fw}: in_agent_types 则 note 必填")

    def test_docker_services_reference_real_frameworks(self):
        owners = {svc for spec in FRAMEWORKS.values() for svc in spec.docker_services}
        self.assertEqual(owners, {"codex-web", "codex-review", "opencode", "hermes", "openclaw", "dsh"})


class TestGoldenDerivedTables(unittest.TestCase):
    """迁移金标准——值漂移即红。新增框架时在此追加条目。"""

    def test_agent_types(self):
        from lib.adapters.config.config_schema import AGENT_TYPES
        self.assertEqual(AGENT_TYPES, (
            "hermes", "hermes_profile", "openclaw", "cline", "opencode", "codex",
            "claude_code", "zcode", "cursor", "dsh", "none",
        ))

    def test_access_dirs(self):
        from lib.adapters.config.access_adapters import FRAMEWORK_ACCESS_DIR
        self.assertEqual(FRAMEWORK_ACCESS_DIR, {
            "hermes": "hermes", "hermes_profile": "hermes", "codex": "codex",
            "claude_code": "claude_code", "zcode": "zcode", "opencode": "opencode",
            "openclaw": "openclaw", "cline": "cline", "cursor": "cursor",
        })

    def test_default_models(self):
        from lib.adapters.config.init_store import DEFAULT_MODELS
        self.assertEqual(DEFAULT_MODELS, {
            "hermes_profile": ["deepseek-flash"], "codex": ["deepseek-flash"],
            "claude_code": ["deepseek-flash"], "zcode": ["glm"],
            "openclaw": ["deepseek-flash"],
            "opencode": ["deepseek-flash", "qwen-max", "zhipu-4"],
        })

    def test_identity_filenames(self):
        from lib.adapters.config.native_scan import _IDENTITY_FILENAME
        self.assertEqual(_IDENTITY_FILENAME, {
            "hermes": "SOUL.md", "hermes_profile": "SOUL.md", "openclaw": "SOUL.md",
            "opencode": "SOUL.md", "codex": "IDENTITY.md", "claude_code": "CLAUDE.md",
            "cursor": "CLAUDE.md", "cline": "CLAUDE.md", "zcode": "AGENTS.md",
            "dsh": "SOUL.md",
        })

    def test_ui_meta_keys_cover_agent_types(self):
        from lib.adapters.config.config_admin import AGENT_TYPE_META
        self.assertEqual(set(AGENT_TYPE_META), set(
            fw for fw, spec in FRAMEWORKS.items() if spec.in_agent_types
        ))
        self.assertEqual(
            AGENT_TYPE_META["zcode"],
            {"label": "ZCode CLI", "note": "宿主机 zcode -p · GLM 后端（Z.AI OAuth）"},
        )

    def test_cli_bin_names(self):
        from lib.adapters.ops.platform_probe import WindowsProbe
        self.assertEqual(WindowsProbe.CLI_BIN_NAMES, {
            "claude_code": "claude", "hermes_profile": "hermes", "hermes": "hermes",
        })

    def test_docker_service_type(self):
        from lib.adapters.frameworks.registry import DOCKER_SERVICE_TYPE
        self.assertEqual(DOCKER_SERVICE_TYPE, {
            "codex-web": "codex", "codex-review": "codex", "opencode": "opencode",
            "hermes": "hermes_profile", "openclaw": "openclaw", "dsh": "dsh",
        })

    def test_run_targets(self):
        from lib.adapters.frameworks.framework_discovery import FRAMEWORK_RUN_TARGETS
        self.assertEqual(FRAMEWORK_RUN_TARGETS["claude_code"], ["windows", "wsl", "linux"])
        self.assertEqual(FRAMEWORK_RUN_TARGETS["zcode"], ["windows"])
        self.assertEqual(FRAMEWORK_RUN_TARGETS["dsh"], ["docker"])
        self.assertNotIn("a2a_remote", FRAMEWORK_RUN_TARGETS)

    def test_file_task_types(self):
        from lib.application.orchestration.file_task_push import FILE_TASK_AGENT_TYPES
        self.assertEqual(FILE_TASK_AGENT_TYPES,
                         frozenset({"cline", "opencode", "codex", "claude_code", "zcode"}))
        self.assertEqual(file_task_agent_types(), FILE_TASK_AGENT_TYPES)

    def test_dispatch_flags(self):
        """resolve_push_cli kwargs 分派金标准：codex 收 pipeline，claude/zcode 收 data_dir。"""
        self.assertTrue(FRAMEWORKS["codex"].pass_pipeline)
        self.assertFalse(FRAMEWORKS["codex"].needs_data_dir)
        self.assertTrue(FRAMEWORKS["claude_code"].needs_data_dir)
        self.assertTrue(FRAMEWORKS["zcode"].needs_data_dir)
        for fw, spec in FRAMEWORKS.items():
            if fw not in ("codex", "claude_code", "zcode"):
                self.assertFalse(spec.pass_pipeline, fw)
                self.assertFalse(spec.needs_data_dir, fw)


class TestAdapterSpecConsistency(unittest.TestCase):
    """registry.py Adapter 类属性与 FRAMEWORKS 必须一致（双写漂移即红）。

    新框架落地时两处都要写：spec 进 FRAMEWORKS，行为进 Adapter 类——
    本测试保证数据面不脱钩。
    """

    def test_every_adapter_has_spec(self):
        from lib.adapters.frameworks.registry import ADAPTERS
        missing = set(ADAPTERS) - set(FRAMEWORKS)
        self.assertEqual(missing, set(), f"adapter 无 spec: {missing}")

    def test_adapter_class_attributes_match_spec(self):
        from lib.adapters.frameworks.registry import ADAPTERS
        for fw, adapter in ADAPTERS.items():
            spec = FRAMEWORKS[fw]
            self.assertEqual(adapter.container_service, spec.container_service,
                             f"{fw}: container_service")
            self.assertEqual(adapter.supports_auto_ack, spec.supports_auto_ack,
                             f"{fw}: supports_auto_ack")
            self.assertEqual(adapter.mark_processing_on_task_push,
                             spec.mark_processing_on_task_push, f"{fw}: mark_processing")
            self.assertEqual(adapter.allow_no_push_cli, spec.allow_no_push_cli,
                             f"{fw}: allow_no_push_cli")

    def test_agent_types_all_resolvable(self):
        """config 允许的每个 type 都有 adapter（扩展原 test_all_types_have_adapter）。"""
        from lib.adapters.config.config_schema import AGENT_TYPES
        from lib.adapters.frameworks.registry import get_adapter
        for fw in AGENT_TYPES:
            self.assertIsNotNone(get_adapter(fw), f"{fw}: 无 adapter")

    def test_dispatch_flags_match_adapter_signatures(self):
        """spec 声明要传的 kwarg，Adapter.build_push_cli 必须能收（否则运行时 TypeError）。"""
        import inspect
        from lib.adapters.frameworks.registry import ADAPTERS
        for fw, adapter in ADAPTERS.items():
            spec = FRAMEWORKS[fw]
            sig = inspect.signature(adapter.build_push_cli)
            params = sig.parameters
            for flag, kwarg in (("pass_pipeline", "pipeline"), ("needs_data_dir", "data_dir")):
                if getattr(spec, flag):
                    self.assertIn(kwarg, params, f"{fw}: spec.{flag} 但 build_push_cli 无 {kwarg} 形参")

    def test_direct_builders_table_covers_builtin_frameworks(self):
        """direct_push 表分派：8 个内置 direct 框架全注册（运行时可增外部），签名统一。"""
        import inspect
        from lib.adapters.frameworks.direct_push import DIRECT_BUILDERS, register_direct_builder
        self.assertTrue({
            "claude_code", "codex", "hermes", "hermes_profile",
            "openclaw", "cline", "opencode", "zcode",
        } <= set(DIRECT_BUILDERS))
        for fw, fn in DIRECT_BUILDERS.items():
            params = inspect.signature(fn).parameters
            for kwarg in ("data_dir", "prompt", "model_name", "pipeline"):
                self.assertIn(kwarg, params, f"{fw}: direct builder 缺统一 kwarg {kwarg}")

    def test_register_direct_builder_roundtrip(self):
        """register_framework + register_direct_builder 配套注册即生效（W2 扩展形态）。"""
        from lib.adapters.frameworks.direct_push import (
            DIRECT_BUILDERS, register_direct_builder, try_build_push_direct,
        )
        from lib.adapters.frameworks.registry import (
            NoneAdapter, register_framework, unregister_framework,
        )
        seen = {}

        def _probe(agent_name, agent_cfg, agent_types, *, data_dir="", prompt="",
                   model_name=None, pipeline=False):
            seen.update(prompt=prompt, pipeline=pipeline)
            # argv[0] 须在 spawn_guard 白名单内（try_build 末尾会校验）
            return {"argv": ["python", "-c", "pass"], "env": {}, "cwd": None}

        register_framework("w2-probe", NoneAdapter())
        register_direct_builder("w2-probe", _probe)
        try:
            out = try_build_push_direct(
                "p1", {"type": "w2-probe"}, {},
                data_dir="", prompt="hello", model_name=None, pipeline=True,
            )
            self.assertEqual(out["argv"], ["python", "-c", "pass"])
            self.assertEqual(seen, {"prompt": "hello", "pipeline": True})
        finally:
            unregister_framework("w2-probe")
            DIRECT_BUILDERS.pop("w2-probe", None)
        with self.assertRaises(ValueError):
            register_direct_builder("claude_code", _probe)  # 已存在且 replace=False


if __name__ == "__main__":
    unittest.main()
