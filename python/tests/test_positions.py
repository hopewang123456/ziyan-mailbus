"""P1 发令窗口后端地基 — 职位目录（D3 职位≠角色）聚合与 inputs schema。"""
from __future__ import annotations

import os
import tempfile
import unittest


def _make_store_with_roles(roles_doc: dict, agents_cfg: dict | None = None) -> str:
    td = tempfile.mkdtemp()
    os.makedirs(os.path.join(td, "roles", "json"), exist_ok=True)
    with open(os.path.join(td, "roles", "json", "role-types.json"), "w", encoding="utf-8") as f:
        import json
        json.dump(roles_doc, f, ensure_ascii=False)
    with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
        import json
        json.dump({"agents": agents_cfg or {}}, f, ensure_ascii=False)
    return td


class TestPositionCatalog(unittest.TestCase):
    def _catalog(self, agents_cfg=None):
        from lib.application.orchestration.dispatch.role_resolver import position_catalog

        roles = {
            "roles": {
                "1": {
                    "key": "designer",
                    "display": {"zh": "方案设计师", "en": "Designer"},
                    "candidates": ["agentA", "agentB"],
                    "default_sla_minutes": 30,
                    "inputs": [
                        {"name": "topic", "label": {"zh": "主题"}, "type": "string", "required": True},
                        {"name": "priority", "label": {"zh": "优先级"}, "type": "enum",
                         "options": ["high", "normal"], "default": "normal"},
                    ],
                },
                "8": {
                    "key": "developer",
                    "display": {"zh": "开发工程师", "en": "Developer"},
                    "candidates": [],
                },
            }
        }
        td = _make_store_with_roles(roles, agents_cfg)
        return position_catalog(td), td

    def test_positions_shape_and_inputs_passthrough(self):
        cat, _ = self._catalog()
        self.assertEqual(cat["total"], 2)
        p1 = cat["positions"][0]
        self.assertEqual(p1["role_type"], 1)
        self.assertEqual(p1["name_zh"], "方案设计师")
        self.assertEqual(p1["key"], "designer")
        self.assertEqual([i["name"] for i in p1["inputs"]], ["topic", "priority"])
        self.assertTrue(p1["inputs"][0]["required"])
        # 无 inputs 的职位缺省空列表（存量 SoT 兼容）
        self.assertEqual(cat["positions"][1]["inputs"], [])

    def test_candidate_metadata_and_busy(self):
        cat, _ = self._catalog(agents_cfg={
            "agentA": {"name": "甲", "type": "codex", "concurrency": 1},
            "agentB": {"name": "乙", "type": "hermes"},
        })
        cands = {c["agent_id"]: c for c in cat["positions"][0]["candidates"]}
        self.assertEqual(cands["agentA"]["name"], "甲")
        self.assertEqual(cands["agentA"]["framework"], "codex")
        self.assertIn("busy", cands["agentA"])
        self.assertIn("active_tasks", cands["agentA"])

    def test_composition_facade(self):
        from lib.composition import position_catalog as facade

        cat, td = self._catalog()
        got = facade(td)
        self.assertEqual(got["total"], 2)


if __name__ == "__main__":
    unittest.main()
