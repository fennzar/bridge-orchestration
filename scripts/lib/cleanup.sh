#!/bin/bash
# ===========================================
# Shared Cleanup Functions
# ===========================================
# Kill stale app processes and clean overmind sockets.

# App ports that should be free before starting overmind
APP_PORTS=(7050 7051 7000 7100)

# Kill any processes listening on app ports.
# Called before starting overmind and during cleanup.
kill_stale_app_processes() {
    local killed=0
    for port in "${APP_PORTS[@]}"; do
        local pids
        pids=$(lsof -t -i ":$port" 2>/dev/null) || true
        if [ -n "$pids" ]; then
            for pid in $pids; do
                # Don't kill ourselves
                [ "$pid" = "$$" ] && continue
                kill "$pid" 2>/dev/null && ((killed++)) || true
            done
        fi
    done
    if [ "$killed" -gt 0 ]; then
        sleep 1
        # Force kill anything that didn't die gracefully
        for port in "${APP_PORTS[@]}"; do
            local pids
            pids=$(lsof -t -i ":$port" 2>/dev/null) || true
            if [ -n "$pids" ]; then
                for pid in $pids; do
                    [ "$pid" = "$$" ] && continue
                    kill -9 "$pid" 2>/dev/null || true
                done
            fi
        done
    fi
    return "$killed"
}

# Full overmind shutdown: quit + kill zombies + clean socket
# Usage: shutdown_overmind <socket_path>
shutdown_overmind() {
    local sock="$1"

    # Quit overmind if running
    if [ -S "$sock" ]; then
        overmind quit -s "$sock" 2>/dev/null || true
        for i in $(seq 1 10); do
            [ ! -S "$sock" ] && break
            sleep 0.5
        done
        rm -f "$sock"
    fi

    # Kill any zombie app processes that survived
    local killed=0
    kill_stale_app_processes || killed=$?
    if [ "$killed" -gt 0 ]; then
        echo "  Killed $killed stale app process(es)" >&2
    fi
}
