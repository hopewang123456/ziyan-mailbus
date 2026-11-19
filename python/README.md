# mailbus — Python service

FastAPI + SQLite implementation of the mailbus contract.

```bash
pip install -e ".[dev]"
uvicorn mailbus.bootstrap.main:app --port 9814
python -m pytest -q
```

Package layout:

```
mailbus/core         # pure domain: workflow, identity, org, approval, messaging
mailbus/application  # use cases, transaction boundaries, outbox, queries
mailbus/adapters     # SQLite, transports (a2a / mcp / file_bus), clock, ids
mailbus/api          # routers, schemas, mappers, auth dependency
mailbus/bootstrap    # settings, container, app entry
```

Runtime paths are resolved only in `mailbus/bootstrap/settings.py`.
Data defaults to `<repo>/data` and can be overridden with `MAILBUS_DATA_DIR`.
The generated HTTP contract lives at `shared/contracts/generated/openapi.json`.
