#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
echo "=== store AGENTS.md ==="
head -5 /mailbus/store/AGENTS.md 2>/dev/null || echo "none"
echo "=== threads ==="
if command -v sqlite3 >/dev/null; then
  sqlite3 /home/node/.codex/state_5.sqlite "SELECT id, cwd, substr(name,1,40) FROM threads ORDER BY rowid DESC LIMIT 8;" 2>/dev/null || echo "no threads table"
else
  python3 - <<PY
import sqlite3
c=sqlite3.connect("/home/node/.codex/state_5.sqlite")
for row in c.execute("SELECT name FROM sqlite_master WHERE type=\"table\""):
    print("table:", row[0])
try:
    for row in c.execute("SELECT id, cwd, name FROM threads ORDER BY updated_at DESC LIMIT 8"):
        print(row)
except Exception as e:
    print("err", e)
PY
fi
'
