#!/bin/bash
cd /mnt/e/ai_tools/mail
exec /mnt/e/hermes-data/.hermes/hermes-agent/venv/bin/python3 bus.py serve --host 0.0.0.0 --port 9812 --data-dir /mnt/e/ai_tools/mail/store >> /mnt/e/ai_tools/mail/store/cron.log 2>&1
