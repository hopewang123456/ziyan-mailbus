#!/bin/bash
docker exec docker-agents-lingxiao-1 python3 <<'PY'
import sqlite3, json
c = sqlite3.connect("/home/node/.codex/state_5.sqlite")
cols = [r[1] for r in c.execute("PRAGMA table_info(threads)")]
print("columns:", cols)
for row in c.execute("SELECT * FROM threads ORDER BY rowid DESC LIMIT 5"):
    d = dict(zip(cols, row))
    print(json.dumps({k: d[k] for k in d if k in ('id','cwd','title','preview','updated_at','created_at')}, ensure_ascii=False))
PY
