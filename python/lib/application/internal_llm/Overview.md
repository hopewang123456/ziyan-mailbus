# lib.application.internal_llm

Planner / triage / token budget / RAG context use cases.

## Role

Application logic for internal LLM (Ollama) planning and triage.

## Dependency direction

→ `interfaces` / adapters.internal_llm client via composition or thin imports; infra ensure in `lib.infra.internal_llm`

## Forbidden imports

Prefer not importing Docker/process ensure from application (use infra)

## Files

| File | Purpose |
|------|---------|
| `planner.py` / `triage.py` | Planning / triage |
| `routing.py` | 自动中转路由提示词草案（选下一 agent，不含 transport） |
| `token_budget.py` | Budget |
| `context.py` | RAG context |
