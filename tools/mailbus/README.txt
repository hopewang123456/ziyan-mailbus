Mailbus launchers (cross-platform)
==================================

Canonical entry (Windows / Linux / macOS):
  python tools/mailbus.py <cmd>

Examples:
  python tools/mailbus.py start
  python tools/mailbus.py start --fast
  python tools/mailbus.py stop
  python tools/mailbus.py portproxy
  python tools/mailbus.py recover health

Windows .bat files in this folder are optional thin wrappers.
They cd to the repo root and call python (or py -3 if python is not on PATH).
Prefer the python command above for scripts, CI, and non-Windows hosts.

Desktop shortcuts may point at tools\mailbus\*.bat or scripts\*.bat.
