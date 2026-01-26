#!/bin/bash
# ===========================================
# Shared Environment Loading
# ===========================================
# Safe .env loading that handles unquoted values (like mnemonics)
# and expands variable references (like ${ROOT}, $PATH).
#
# Usage:
#   source "$SCRIPT_DIR/lib/env.sh"
#   load_env "$ORCH_DIR/.env"

load_env() {
    local env_file="$1"

    if [ ! -f "$env_file" ]; then
        echo "Error: $env_file not found" >&2
        return 1
    fi

    # Single pass: load and expand variables immediately so that
    # references like $PATH resolve against the current environment.
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace from key
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        [[ -z "$key" ]] && continue
        # Expand variable references in value
        local expanded_value
        expanded_value=$(eval echo "$value" 2>/dev/null) || expanded_value="$value"
        export "$key=$expanded_value"
    done < "$env_file"

    return 0
}
