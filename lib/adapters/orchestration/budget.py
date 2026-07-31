"""File-backed budget meter — daily chain spend + Q8B fsm_state."""
from __future__ import annotations

import os
from typing import Any, Mapping

from lib.utils import json_read, json_write

DEFAULT_DAILY_BUDGET_CNY = 30.0

# Budget FSM (Q8B): running → awaiting_decision → paused_budget → running
BUDGET_RUNNING = "running"
BUDGET_AWAITING = "awaiting_decision"
BUDGET_PAUSED = "paused_budget"


class FileBudgetMeter:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def _path(self) -> str:
        return os.path.join(self.data_dir, "system", "chain-budget.json")

    def load(self, cfg: Mapping[str, Any] | None = None) -> dict:
        cfg = cfg or json_read(os.path.join(self.data_dir, "config.json"), {})
        state = json_read(self._path(), {})
        cap = float(
            ((cfg.get("mailbus_chains") or {}).get("daily_budget_cny"))
            or state.get("cap_cny")
            or DEFAULT_DAILY_BUDGET_CNY
        )
        state.setdefault("spent_cny", 0.0)
        state.setdefault("cap_cny", cap)
        # migrate legacy paused bool → fsm_state
        if not state.get("fsm_state"):
            if state.get("paused"):
                state["fsm_state"] = BUDGET_PAUSED
            elif state.get("awaiting_ollama_decision"):
                state["fsm_state"] = BUDGET_AWAITING
            else:
                state["fsm_state"] = BUDGET_RUNNING
        state["paused"] = state["fsm_state"] == BUDGET_PAUSED
        state["awaiting_ollama_decision"] = state["fsm_state"] == BUDGET_AWAITING
        return state

    def _write(self, state: dict) -> dict:
        state["paused"] = state.get("fsm_state") == BUDGET_PAUSED
        state["awaiting_ollama_decision"] = state.get("fsm_state") == BUDGET_AWAITING
        os.makedirs(os.path.dirname(self._path()), exist_ok=True)
        json_write(self._path(), state)
        return state

    def record_spend(self, amount_cny: float, cfg: Mapping[str, Any] | None = None) -> dict:
        state = self.load(cfg)
        state["spent_cny"] = float(state.get("spent_cny") or 0) + float(amount_cny)
        cap = float(state.get("cap_cny") or DEFAULT_DAILY_BUDGET_CNY)
        if state["spent_cny"] >= cap and state.get("fsm_state") == BUDGET_RUNNING:
            state["fsm_state"] = BUDGET_AWAITING
            state["alert"] = (
                f"Daily chain budget ¥{cap} reached; confirm switch to Ollama or tasks will pause."
            )
        return self._write(state)

    def apply_ollama_decision(self, use_ollama: bool | None, cfg: Mapping[str, Any] | None = None) -> dict:
        state = self.load(cfg)
        if use_ollama is None:
            state["fsm_state"] = BUDGET_PAUSED
            state["alert"] = "No reply on budget prompt — chain tasks paused."
        else:
            state["fsm_state"] = BUDGET_RUNNING
            state["force_ollama"] = bool(use_ollama)
            state["alert"] = ""
        return self._write(state)

    def is_paused(self) -> bool:
        return self.load().get("fsm_state") == BUDGET_PAUSED
