#!/bin/bash
# migrate-hermes-home — slim Hermes HOME → HERMES_DATA (+ optional Vault skill links)
# Requires explicit env; does not guess ai_tools layout.
set -euo pipefail

: "${HERMES_DATA:?set HERMES_DATA to the new Hermes home root}"
: "${HERMES_OLD_HOME:?set HERMES_OLD_HOME to the previous .hermes path}"
VAULT="${VAULT_AGENT_ROOT:-}"
NEW_HOME="$HERMES_DATA"
OLD_HOME="$HERMES_OLD_HOME"
SHARED="${VAULT:+$VAULT/03-shared}"
HERMES_CAT="${VAULT:+$VAULT/02-members/022-category/0221-hermes}"
PERSONS="${HERMES_CAT:+$HERMES_CAT/02213-persons}"

# id → person dir suffix (optional Vault layout; skip skill links if VAULT unset)
declare -A PERSON=(
  [lingzhao]=022131-lingzhao
  [lingjin]=022132-lingjin
  [lingtuo]=022133-lingtuo
  [lingxi]=022134-lingxi
  [lingxun]=022135-lingxun
  [lingzhang]=022136-lingzhang
)

echo "[migrate] NEW_HOME=$NEW_HOME"
mkdir -p "$NEW_HOME/profiles"

# --- slim seed from old home (no sessions/logs/cache) ---
if [ -d "$OLD_HOME" ]; then
  for f in config.yaml .env SOUL.md AGENTS.md auth.json channel_directory.json; do
    if [ -f "$OLD_HOME/$f" ] && [ ! -f "$NEW_HOME/$f" ]; then
      cp -a "$OLD_HOME/$f" "$NEW_HOME/$f" 2>/dev/null || echo "[migrate] skip (perm): $f"
    fi
  done
fi

link_or_replace() {
  local link="$1" target="$2"
  mkdir -p "$(dirname "$link")"
  if [ -L "$link" ] || [ -e "$link" ]; then
    rm -rf "$link"
  fi
  ln -s "$target" "$link"
}

rebuild_profile() {
  local id="$1"
  local pdir="${PERSON[$id]:-}"
  [ -n "$pdir" ] || { echo "[migrate] skip unknown $id"; return; }
  [ -n "$VAULT" ] || { echo "[migrate] VAULT_AGENT_ROOT unset — seed profile only for $id"; return; }

  local prof="$NEW_HOME/profiles/$id"
  mkdir -p "$prof"

  # seed slim profile config from old if present
  if [ -d "$OLD_HOME/profiles/$id" ]; then
    for f in config.yaml .env SOUL.md; do
      if [ -f "$OLD_HOME/profiles/$id/$f" ] && [ ! -f "$prof/$f" ]; then
        cp -a "$OLD_HOME/profiles/$id/$f" "$prof/$f" 2>/dev/null || true
      fi
    done
  fi

  local pid="${pdir%%-*}"
  local mem="${PERSONS}/${pdir}/${pid}3-memory"
  if [ ! -d "$mem" ]; then
    echo "[migrate] WARN missing memory dir: $mem"
  else
    link_or_replace "$prof/memories" "$mem"
    echo "[migrate] $id memories -> $mem"
  fi

  local priv="${PERSONS}/${pdir}/${pid}2-skills-private"
  mkdir -p "$priv"

  local skills="$prof/skills"
  rm -rf "$skills"
  mkdir -p "$skills"
  if [ -d "$SHARED" ]; then
    local d base
    for d in "$SHARED"/*; do
      [ -e "$d" ] || continue
      base="$(basename "$d")"
      ln -s "$d" "$skills/$base"
    done
  fi
  if [ -d "$priv" ]; then
    for d in "$priv"/*; do
      [ -e "$d" ] || continue
      base="$(basename "$d")"
      rm -f "$skills/$base"
      ln -s "$d" "$skills/$base"
    done
  fi
  echo "shared=$SHARED" >"$prof/.mailbus-skills-layout"
  echo "private=$priv" >>"$prof/.mailbus-skills-layout"
  echo "[migrate] $id skills: $(ls -1 "$skills" 2>/dev/null | wc -l) links"
}

for id in lingzhao lingjin lingtuo lingxi lingxun lingzhang; do
  rebuild_profile "$id"
done

chmod -R a+rwX "$NEW_HOME" 2>/dev/null || true
echo "[migrate] done. HERMES_DATA=$NEW_HOME"
