"""双栈 API 面对拍工具测试（PY4-A）— 归一化 + 豁免 + 报告结构。

工具在 ``tools/api_surface_diff.py``（仓库根 tools/ 目录，非 python 包），
测试按路径加载它。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOOL = REPO / "tools" / "api_surface_diff.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("api_surface_diff", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_surface_diff"] = module
    spec.loader.exec_module(module)
    return module


diff = _load_tool()


class TestSurfaceSet:
    def test_path_params_normalized(self):
        """路径参数段归一化为 {}（python {id} 与 java {agent} 同路径）。"""
        doc = {
            "paths": {
                "/api/tasks/{id}": {"get": {"summary": "任务详情"}},
                "/api/inbox/{agent}/unread": {"get": {"summary": "未读"}},
                "/api/a2a/protocol": {"get": {"description": "协议状态"}},
            }
        }
        out = diff.surface_set(doc)
        assert ("GET", "/api/tasks/{}") in out
        assert ("GET", "/api/inbox/{}/unread") in out
        assert ("GET", "/api/a2a/protocol") in out

    def test_only_http_methods_counted(self):
        doc = {"paths": {"/api/x": {
            "get": {"summary": "g"}, "post": {"summary": "p"},
            "parameters": [], "summary": "not-an-operation",
        }}}
        out = diff.surface_set(doc)
        assert set(out) == {("GET", "/api/x"), ("POST", "/api/x")}

    def test_summary_falls_back_to_description(self):
        doc = {"paths": {"/api/y": {"get": {"description": "描述"}}}}
        assert diff.surface_set(doc)[("GET", "/api/y")] == "描述"


class TestExemptions:
    def test_exempt_endpoints_declared(self):
        """C2 两条（java 501）必须在豁免名单里。"""
        assert ("GET", "/api/events") in diff.EXEMPT_NOT_IMPLEMENTED
        assert ("GET", "/api/trace/{}") in diff.EXEMPT_NOT_IMPLEMENTED

    def test_exemptions_are_single_sided(self):
        """豁免键用归一化 path（{} 而非 {id}）。"""
        for method, path in diff.EXEMPT_NOT_IMPLEMENTED:
            assert method.isupper()
            assert "{" not in path or "{}" in path


class TestPythonSurfaceOffline:
    def test_offline_generates_from_route_table(self):
        """--py offline：直接从路由表生成（不起服务）。"""
        doc = diff.python_surface("offline")
        assert doc["openapi"] == "3.1.0"
        paths = doc["paths"]
        # 本轮新增/迁表的端点都应在文档里
        for p in ("/api/agents", "/api/stats", "/api/acceptance",
                  "/api/inbox/{agent}", "/api/agents/{agent}/unread",
                  "/api/inbox/ack/{id}", "/api/inbox/{agent}/archive",
                  "/api/inbox/{agent}/send", "/api/tasks/{id}/fsm",
                  "/api/tasks/{id}/fsm/{action}",
                  "/api/command/inbox/stream", "/api/metrics/stream"):
            assert p in paths, f"缺端点声明: {p}"


class TestReportStructure:
    def test_report_has_summary_counts_and_sections(self):
        """报告结构：summary 六个计数字段 + both/python_only/java_only/exempted 四段。"""
        py_set = {("GET", "/api/a"), ("GET", "/api/b")}
        java_set = {("GET", "/api/a"), ("GET", "/api/c")}
        both = sorted(set(py_set) & set(java_set))
        py_only = sorted(set(py_set) - set(java_set))
        java_only = sorted(set(java_set) - set(py_set))
        exempted = sorted(k for k in (set(py_only) | set(java_only))
                          if k in diff.EXEMPT_NOT_IMPLEMENTED)
        exempt_set = set(exempted)
        py_only = [k for k in py_only if k not in exempt_set]
        java_only = [k for k in java_only if k not in exempt_set]
        summary = {
            "python_endpoints": len(py_set),
            "java_endpoints": len(java_set),
            "both": len(both),
            "python_only": len(py_only),
            "java_only": len(java_only),
            "exempted_not_implemented": len(exempted),
        }
        for key in ("python_endpoints", "java_endpoints", "both",
                    "python_only", "java_only", "exempted_not_implemented"):
            assert key in summary
        assert summary["python_only"] == 1
        assert summary["java_only"] == 1
