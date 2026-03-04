# Shared tool availability check — source from any script
require_tool() {
    command -v "$1" &>/dev/null || { echo "ERROR: '$1' not found in PATH." >&2; exit 1; }
}
