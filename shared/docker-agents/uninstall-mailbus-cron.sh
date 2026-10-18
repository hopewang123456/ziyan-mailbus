#!/bin/bash
# 委托 Python — 见 lib/adapters/plane.post_start.uninstall_mailbus_cron
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 -c "
import sys
sys.path.insert(0, '${ROOT}')
from lib.infra.env_bootstrap import load_mailbus_env
from lib.adapters.plane.post_start import uninstall_mailbus_cron
load_mailbus_env()
raise SystemExit(uninstall_mailbus_cron())
"
