"""catalog_search — 外部工具可被 mailbus search 索引。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_index_and_search_external_tools():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        ext = os.path.join(tmp, "external-tools")
        os.makedirs(os.path.join(ext, "adapters", "lingtuo"))
        os.environ["MAILBUS_EXTERNAL_TOOLS_DIR"] = ext

        import json
        with open(os.path.join(ext, "registry.example.json"), "w", encoding="utf-8") as f:
            json.dump({
                "version": "0.2.0",
                "tools": [{
                    "id": "dify-lead-enrich",
                    "provider": "dify",
                    "kind": "workflow",
                    "description": "商机背景 enrichment Coze Dify",
                }],
            }, f)
        with open(os.path.join(ext, "grants.example.json"), "w", encoding="utf-8") as f:
            json.dump({"agent_grants": {"lingtuo": ["dify-lead-enrich"]}}, f)
        with open(os.path.join(ext, "adapters", "lingtuo", "dify-lead-enrich.json"), "w", encoding="utf-8") as f:
            json.dump({
                "agent_id": "lingtuo",
                "tool_id": "dify-lead-enrich",
                "enabled": True,
                "description": "灵拓专用 Dify 工作流",
            }, f)

        from lib.catalog_search import index_catalog, search_catalog

        n = index_catalog(store, {"lingtuo": {"name": "灵拓", "role": "市场拓展", "type": "hermes_profile"}})
        assert n >= 2

        hits = search_catalog(store, "dify")
        assert any(h.get("tool_id") == "dify-lead-enrich" for h in hits)

        hits2 = search_catalog(store, "lingtuo")
        assert any(h.get("agent_id") == "lingtuo" for h in hits2)

        os.environ.pop("MAILBUS_EXTERNAL_TOOLS_DIR", None)
        print("  ok test_index_and_search_external_tools")


if __name__ == "__main__":
    test_index_and_search_external_tools()
