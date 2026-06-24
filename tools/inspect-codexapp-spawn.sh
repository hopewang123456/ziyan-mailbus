#!/bin/bash
docker exec docker-agents-lingxiao-1 node <<'NODE'
const fs = require('fs');
const s = fs.readFileSync('/usr/local/lib/node_modules/codexapp/dist-cli/index.js', 'utf8');
for (const k of ['CODEX_HOME', 'app-server', '--memories', 'developer_instructions', 'AGENTS.md', 'projectPath', 'spawn(', 'base_instructions', 'codex login', 'HOME']) {
  let idx = 0;
  let count = 0;
  while ((idx = s.indexOf(k, idx)) >= 0 && count < 2) {
    console.log('\n===', k, 'at', idx, '===');
    console.log(s.slice(Math.max(0, idx - 100), idx + 200).replace(/\n/g, ' '));
    idx += k.length;
    count++;
  }
  if (count === 0) console.log(k, ': NOT FOUND');
}
NODE
