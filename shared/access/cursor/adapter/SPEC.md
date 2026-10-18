# L1 — Cursor Framework Spec

> **Layer**: L1 · **Framework**: cursor · **Agents**: user-defined

## Runtime 契约

- Push: `cursor-agent -p 'MSG'` or `agent -p 'MSG'` when on PATH
- Delivery SoT (D1): `store/msg-results/{task_id}/step-{step_id}.json`
- Registered in `lib/agent_adapters.py` as `CursorAdapter`

## Notes

If CLI missing, mailbus still registers the agent (file_bus / harness contract); enable from cockpit when ready.
