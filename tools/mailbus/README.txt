Mailbus launchers (cross-platform)
==================================

Canonical entry (Windows / Linux / macOS):
  python tools/mailbus.py <cmd>

Examples:
  python tools/mailbus.py start
  python tools/mailbus.py start --fast
  python tools/mailbus.py stop
  python tools/mailbus.py docker restart-mailbus
  python tools/mailbus.py portproxy
  python tools/mailbus.py recover health

Thin launch wrappers (Windows / Linux) live in scripts/:
  scripts/start-mailbus.bat   (Windows)
  scripts/start-mailbus.sh    (Linux / macOS)

Desktop shortcuts should point to scripts\start-mailbus.bat or the CLI above.
