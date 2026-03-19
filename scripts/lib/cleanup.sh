#!/bin/bash
# ===========================================
# Shared Cleanup Functions
# ===========================================
# Kill stale app processes, overmind instances, and tmux sockets.

# App ports that should be free before starting overmind
APP_PORTS=(7050 7051 7000 7100)

# Kill any processes listening on app ports.
kill_stale_app_processes() {
    local killed=0
    for port in "${APP_PORTS[@]}"; do
        local pids
        pids=$(lsof -t -i ":$port" 2>/dev/null) || true
        if [ -n "$pids" ]; then
            for pid in $pids; do
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

# Kill ALL overmind processes and clean their tmux sockets + temp dirs.
# This is the nuclear option — use when overmind is stuck or stale.
kill_all_overmind() {
    # Kill overmind processes
    killall -9 overmind 2>/dev/null || true
    sleep 1

    # Clean stale tmux sockets (overmind uses per-instance tmux servers)
    rm -f /tmp/tmux-"$(id -u)"/overmind-bridge-orchestration-* 2>/dev/null || true

    # Clean overmind temp dirs
    rm -rf /tmp/overmind-bridge-orchestration-* 2>/dev/null || true
}

# Full overmind shutdown: quit + kill zombies + clean everything
# Usage: shutdown_overmind <socket_path>
shutdown_overmind() {
    local sock="$1"

    # Try graceful quit first
    if [ -S "$sock" ]; then
        overmind quit -s "$sock" 2>/dev/null || true
        for i in $(seq 1 10); do
            [ ! -S "$sock" ] && break
            sleep 0.5
        done
    fi
    rm -f "$sock" 2>/dev/null || true

    # Kill any stale overmind instances + their tmux sockets
    kill_all_overmind

    # Kill any zombie app processes that survived
    local killed=0
    kill_stale_app_processes || killed=$?
    if [ "$killed" -gt 0 ]; then
        echo "  Killed $killed stale app process(es)" >&2
    fi
}
