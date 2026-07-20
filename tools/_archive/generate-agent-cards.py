#!/usr/bin/env python3
"""从 team-pack agent-registry 生成 store/agents/cards/{agent_id}.json。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.constants import MAILBUS_ROOT, TEAM_PACK_ROOT
from lib.profile_registry import load_all_profiles
from lib.transport.agent_card_cache import enrich_agent_channels, load_registry
from lib.transport.a2a_mapper import to_agent_card
from lib.utils import json_write


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate A2A Agent Cards")
    ap.add_argument("--data-dir", type=Path, default=MAILBUS_ROOT / "store")
    ap.add_argument("--base-url", default="https://mailbus.example")
    args = ap.parse_args()

    data_dir = str(args.data_dir)
    registry = load_registry(data_dir)
    profiles = load_all_profiles()
    out_dir = Path(data_dir) / "agents" / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for agent_id in sorted(registry):
        entry = enrich_agent_channels(agent_id, dict(registry[agent_id]))
        prof = profiles.get(agent_id) or {}
        display = prof.get("display_name") or entry.get("display_name") or agent_id
        card = to_agent_card(
            agent_id,
            entry,
            display_name=display,
            functional_group=entry.get("functional_group", ""),
            base_url=args.base_url,
        )
        doc = {
            "schema": "mailbus-agent-card-v1",
            "agent_id": agent_id,
            "publish": entry.get("status", "active") == "active",
            "wire": card,
        }
        json_write(str(out_dir / f"{agent_id}.json"), doc)
        n += 1

    print(f"generated {n} cards -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
