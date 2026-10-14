"""G0 intake: dispatch the design-proposal work order to the planner station."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "store")

from lib.application.orchestration.router.envelope_validate import validate_envelope
from lib.application.orchestration.router.planner import plan_tier0
from lib.application.orchestration.tracker import TaskTracker
from lib.application.workflow.engine import bind_workflow
from lib.application.orchestration.router.dispatch import dispatch_first_step, start_executing
from lib.infra.utils import json_write

INTENT = (
    "CUSTOM ORDER — Design proposals for a simulation/management game (mailbus production-line experiment).\n"
    "Hard constraints:\n"
    "1) Three deliverables: Unity 2022 LTS C# client (WebGL buildable), Python backend "
    "(accounts / cloud save / economy settlement / leaderboard REST APIs), web operations console "
    "(metrics dashboard + config management).\n"
    "2) Art: CC0 asset packs only (Kenney-style); workers assemble assets, never draw.\n"
    "3) Core gameplay loop must sustain >= 20 minutes of play.\n"
    "4) Production window: 2 days — scope systems accordingly (milestone-friendly).\n"
    "5) ALL deliverable documents in English.\n"
    "Your task: produce 2-3 game proposals. Each proposal must include: game title + one-line concept; "
    "core gameplay loop (3-5 steps); system list (>=8 buildings/facilities, >=2 progression lines, "
    ">=3 economy resources); numeric framework outline; three-tier work split & milestones; risks.\n"
    "Write the full proposals to /mailbus/store/deliverables/game/docs/proposals.md (English). "
    "In your step-result summary, give a one-line digest of each proposal."
)

envelope = {
    "task_id": "game-g0-intake",
    "intent": INTENT,
    "initiator": "ziyan(proxy)",
    "mode": "explicit",
    "tier": "M",
    "task_type": "custom",
    "planned_chain": [{"station": "planner", "reason": "design proposals"}],
}

errors = validate_envelope(envelope, data_dir=DATA_DIR)
assert not errors, errors
out = plan_tier0(envelope, data_dir=DATA_DIR)
tracker = TaskTracker(DATA_DIR)
assert not tracker.get("game-g0-intake"), "task exists"
task = tracker.create_from_envelope(
    envelope, planned_chain=out["planned_chain"], plan_meta=out["plan_meta"]
)
bind_workflow(task, envelope, data_dir=DATA_DIR)
json_write(tracker._task_path("game-g0-intake"), task)
start_executing(task)
ok = dispatch_first_step(DATA_DIR, task)
step = (task.get("chain") or [{}])[0]
print("G0 dispatched:", ok, "| assignee:", step.get("to_agent"),
      "| station:", step.get("station"), "| meta:", step.get("dispatch_meta"))
