#!/bin/bash
# 委托 Python — 见 lib/team_post_start.uninstall_mailbus_cron
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 -c "
import sys
sys.path.insert(0, '${ROOT}')
from lib.env_bootstrap import load_mailbus_env
from lib.team_post_start import uninstall_mailbus_cron
load_mailbus_env()
raise SystemExit(uninstall_mailbus_cron())
"
