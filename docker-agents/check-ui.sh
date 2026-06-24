#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc 'cat /tmp/codex-ui/codexapp-lingxiao.log 2>/dev/null; echo ---; ps aux | grep codexapp | grep -v grep; echo ---; curl -sf http://127.0.0.1:7681/ | head -c 100'
