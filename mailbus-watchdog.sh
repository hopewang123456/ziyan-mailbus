#!/bin/bash
# mailbus-watchdog.sh — 通用 mailbus inbox 检查脚本
# 用法: ./mailbus-watchdog.sh <agent_name>
# 检查对应 inbox，有 pending 消息则写 ack 并输出到临时文件

AGENT="$1"
MAILBUS_INBOX="/mnt/e/ai_tools/mail/store/inbox/${AGENT}/inbox.json"
OUTFILE="/tmp/mailbus-${AGENT}-inbox.txt"

if [ ! -f "$MAILBUS_INBOX" ]; then
    exit 0
fi

python3 -c "
import json, os, sys

agent = '$AGENT'
inbox_file = '$MAILBUS_INBOX'
outfile = '$OUTFILE'

try:
    with open(inbox_file) as f:
        inbox = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    sys.exit(0)

pending = [m for m in inbox.get('messages', []) if m.get('status') == 'pending']
if not pending:
    if os.path.exists(outfile):
        os.remove(outfile)
    sys.exit(0)

# 写 ack
ack_file = inbox_file.replace('inbox.json', 'ack.json')
ack_entries = []
for m in pending:
    ack_entries.append({
        'action': 'ack',
        'msg_id': m['id'],
        'agent': agent,
        'timestamp': '$(date -Iseconds)',
    })

existing = []
if os.path.exists(ack_file):
    try:
        with open(ack_file) as f:
            data = json.load(f)
            existing = data if isinstance(data, list) else [data]
    except:
        pass
existing.extend(ack_entries)
with open(ack_file, 'w') as f:
    json.dump(existing, f, ensure_ascii=False)

# 写输出文件供 agent 读取
with open(outfile, 'w') as f:
    for m in pending:
        f.write(f\"[{m['id']}] {m.get('from','?')}: {m.get('content','')}\n\")

print(f\"mailbus: {len(pending)} 条消息已写 ack\")
" 2>/dev/null || true
