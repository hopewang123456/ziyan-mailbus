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

Windows .bat wrappers in this folder:
  start.bat / stop.bat / restart.bat / fix-port.bat

Desktop shortcuts (e.g. Desktop\子言AI\*.bat) should point here or scripts\*.bat.
