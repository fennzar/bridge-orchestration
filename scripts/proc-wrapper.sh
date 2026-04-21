#!/usr/bin/env bash
# Process wrapper for all overmind-managed apps.
# Usage: proc-wrapper.sh "command to run"
#
# Features:
# - Restarts on crash with exponential backoff (unchanged)
# - Pipes output to both stdout AND logs/<process>.log via tee
# - Rotates log file when it exceeds MAX_LOG_SIZE (on process restart)

RESTART=true
DELAY=2
MAX_DELAY=30
HEALTHY_THRESHOLD=60

# ── Log management ────────────────────────────
PROC_NAME="$1"
shift
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$ORCH_DIR/logs"
LOG_FILE="$LOG_DIR/$PROC_NAME.log"
LOG_PREV="$LOG_DIR/$PROC_NAME.log.1"
MAX_LOG_SIZE=$((10 * 1024 * 1024))  # 10MB, matches Docker's max-size

mkdir -p "$LOG_DIR"

rotate_log() {
    [ ! -f "$LOG_FILE" ] && return
    local size
    size=$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -ge "$MAX_LOG_SIZE" ]; then
        mv "$LOG_FILE" "$LOG_PREV"
    fi
}

# Pipe stdout+stderr through tee (line-buffered)
exec > >(stdbuf -oL tee -a "$LOG_FILE") 2>&1
TEE_PID=$!

trap 'RESTART=false; kill $TEE_PID 2>/dev/null' SIGTERM SIGINT SIGHUP

ulimit -n 65535

while $RESTART; do
    rotate_log  # Check before each restart
    START=$(date +%s)
    bash -c "$*"
    EXIT_CODE=$?

    $RESTART || break
    [ $EXIT_CODE -eq 0 ] && break

    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $HEALTHY_THRESHOLD ] && DELAY=2

    echo "[proc-wrapper] Process crashed (exit $EXIT_CODE), restarting in ${DELAY}s..."
    sleep $DELAY &
    wait $! 2>/dev/null
    $RESTART || break

    DELAY=$(( DELAY * 2 ))
    [ $DELAY -gt $MAX_DELAY ] && DELAY=$MAX_DELAY
done

kill $TEE_PID 2>/dev/null
