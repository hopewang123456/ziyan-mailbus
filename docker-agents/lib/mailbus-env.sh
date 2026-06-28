# Mailbus path + port env — source from shell scripts (start-team, mailbus-boot, repo scripts).
# Template: mail/config/env.template → copy to mail/.env or export before serve.
#
# Usage:
#   . "$(dirname "$0")/lib/mailbus-env.sh"
#   . /path/to/mail/docker-agents/lib/mailbus-env.sh

_mailbus_env_script="${BASH_SOURCE[0]:-$0}"
_mailbus_env_dir="$(cd "$(dirname "$_mailbus_env_script")" && pwd)"
MAIL_DIR="${MAIL_DIR:-$(cd "${_mailbus_env_dir}/../.." && pwd)}"
MAILBUS_ROOT="${MAILBUS_ROOT:-$MAIL_DIR}"
MAILBUS_DATA="${MAILBUS_DATA:-${MAILBUS_DATA_DIR:-$MAIL_DIR/store}}"
MAILBUS_API_PORT="${MAILBUS_API_PORT:-9814}"
MAILBUS_API_BASE="http://127.0.0.1:${MAILBUS_API_PORT}"
export MAIL_DIR MAILBUS_ROOT MAILBUS_DATA MAILBUS_API_PORT MAILBUS_API_BASE

# Load .env without overriding existing exports
_load_env_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$line" ] || continue
    case "$line" in
      *=*)
        local key="${line%%=*}"
        local val="${line#*=}"
        key="$(echo "$key" | sed 's/[[:space:]]*$//')"
        val="$(echo "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed "s/^['\"]//;s/['\"]$//")"
        if [ -n "$key" ] && [ -z "${!key:-}" ]; then
          export "$key=$val"
        fi
        ;;
    esac
  done < "$f"
}

_load_env_file "$MAIL_DIR/.env"
_load_env_file "$MAIL_DIR/docker-agents/.env"

# Re-apply derived paths after .env (env wins for explicit MAILBUS_*)
MAILBUS_ROOT="${MAILBUS_ROOT:-$MAIL_DIR}"
MAILBUS_DATA="${MAILBUS_DATA:-${MAILBUS_DATA_DIR:-$MAIL_DIR/store}}"
MAILBUS_API_PORT="${MAILBUS_API_PORT:-9814}"
MAILBUS_API_BASE="http://127.0.0.1:${MAILBUS_API_PORT}"
export MAILBUS_ROOT MAILBUS_DATA MAILBUS_API_PORT MAILBUS_API_BASE

unset _mailbus_env_script _mailbus_env_dir _load_env_file
