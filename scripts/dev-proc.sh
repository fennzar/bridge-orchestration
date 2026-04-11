#!/usr/bin/env bash
# Auto-restart wrapper for dev processes.
# Usage: dev-proc.sh "command to run"
#
# - Restarts on crash (non-zero exit) with exponential backoff
# - Exits cleanly on SIGTERM/SIGINT/SIGHUP (no restart)
# - Resets backoff after 60s of healthy running

RESTART=true
DELAY=2
MAX_DELAY=30
HEALTHY_THRESHOLD=60

trap 'RESTART=false' SIGTERM SIGINT SIGHUP

ulimit -n 65535 2>/dev/null || true

while $RESTART; do
    START=$(date +%s)
    bash -c "$*"
    EXIT_CODE=$?

    # Signal caught or clean exit — don't restart
    $RESTART || break
    [ $EXIT_CODE -eq 0 ] && break

    # Reset backoff if process ran long enough
    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $HEALTHY_THRESHOLD ] && DELAY=2

    echo "[dev-proc] Process crashed (exit $EXIT_CODE), restarting in ${DELAY}s..."
    sleep $DELAY &
    wait $! 2>/dev/null
    $RESTART || break

    # Exponential backoff with cap
    DELAY=$(( DELAY * 2 ))
    [ $DELAY -gt $MAX_DELAY ] && DELAY=$MAX_DELAY
done
