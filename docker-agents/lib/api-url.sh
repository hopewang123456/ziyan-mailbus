# Mailbus API base URL — source from docker-agents/*.sh scripts.
# Override: export MAILBUS_API_PORT=9814 (default matches compose + native serve)
MAILBUS_API_PORT="${MAILBUS_API_PORT:-9814}"
MAILBUS_API_BASE="http://127.0.0.1:${MAILBUS_API_PORT}"
