#!/usr/bin/env bash
# Start, stop and check Xtoo in WSL.
#
#   ~/xtoo/scripts/xtoo.sh start     leave it running in the background
#   ~/xtoo/scripts/xtoo.sh status    is it up, and what does it hold
#   ~/xtoo/scripts/xtoo.sh stop      stop it
#   ~/xtoo/scripts/xtoo.sh restart   after upgrading or changing configuration
#
# Starting twice is harmless: an already running server is left alone, so the
# start line can go in ~/.bashrc. Everything uses the virtual environment's own
# path, so no environment has to be active first.
#
# The running server is tracked by process id in a file, never by matching
# command lines. Matching would also find any other process whose command line
# merely contains the pattern, and stopping Xtoo would then kill it too.
#
# Override with XTOO_PORT, XTOO_LOG, XTOO_PID or XTOO_CONFIG.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XTOO="$ROOT/.venv/bin/xtoo"
PORT="${XTOO_PORT:-8765}"
LOG="${XTOO_LOG:-$HOME/xtoo.log}"
PIDFILE="${XTOO_PID:-$HOME/.xtoo.pid}"
CONFIG="${XTOO_CONFIG:-}"
WAIT_SECONDS=60

url() { echo "http://localhost:$PORT"; }

# The recorded process id, but only if it is alive and really is Xtoo. A stale
# file, or a number reused by something else, counts as not running.
running() {
    local pid
    [ -f "$PIDFILE" ] || return 1
    pid="$(cat "$PIDFILE" 2>/dev/null)"
    case "$pid" in
        '' | *[!0-9]*) return 1 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 1
    tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q "xtoo" || return 1
    echo "$pid"
}

start() {
    local pid
    if pid="$(running)"; then
        echo "Already running (pid $pid) on $(url)"
        return 0
    fi
    if [ ! -x "$XTOO" ]; then
        echo "Xtoo is not installed at $XTOO" >&2
        echo "Create it with:  python3 -m venv $ROOT/.venv && $ROOT/.venv/bin/pip install -e $ROOT" >&2
        return 1
    fi

    local arguments=(serve --port "$PORT")
    [ -n "$CONFIG" ] && arguments=(--config "$CONFIG" "${arguments[@]}")
    nohup "$XTOO" "${arguments[@]}" >>"$LOG" 2>&1 &
    echo "$!" >"$PIDFILE"

    local waited=0
    while [ "$waited" -lt "$WAIT_SECONDS" ]; do
        if curl -sf -o /dev/null "$(url)/api/status" 2>/dev/null; then
            echo "Started (pid $(cat "$PIDFILE")) on $(url)"
            return 0
        fi
        if ! running >/dev/null; then
            echo "Xtoo stopped during startup. Last lines of $LOG:" >&2
            tail -15 "$LOG" >&2
            rm -f "$PIDFILE"
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "Started, but $(url) did not answer within ${WAIT_SECONDS}s. See $LOG" >&2
    return 1
}

stop() {
    local pid waited=0
    if ! pid="$(running)"; then
        rm -f "$PIDFILE"
        echo "Not running"
        return 0
    fi
    kill "$pid" 2>/dev/null
    while running >/dev/null && [ "$waited" -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if running >/dev/null; then
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi
    rm -f "$PIDFILE"
    echo "Stopped"
}

status() {
    local pid
    if ! pid="$(running)"; then
        echo "Not running. Start it with: $0 start"
        return 1
    fi
    echo "Running (pid $pid) on $(url)"
    curl -sf "$(url)/api/status" 2>/dev/null | "$ROOT/.venv/bin/python" -c '
import json, sys

try:
    state = json.load(sys.stdin)
except ValueError:
    sys.exit("  the server is up but returned no status")
kinds = state.get("kinds", {})
busiest = sorted(kinds.items(), key=lambda item: -item[1])[:6]
print("  {:,} documents: ".format(sum(kinds.values()))
      + ", ".join("{:,} {}".format(count, kind) for kind, count in busiest))
if state.get("running"):
    print("  indexing now: {:,} updated, {:,} unchanged".format(
        state.get("indexed") or 0, state.get("unchanged") or 0))
else:
    print("  last scan " + (state.get("last_finished") or "not yet"))
if state.get("error_count"):
    print("  {:,} indexing issues, see the interface".format(state["error_count"]))
if state.get("semantic"):
    print("  semantic search ready")
' || echo "  (no status returned)"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart)
        stop
        start
        ;;
    status) status ;;
    *)
        echo "Usage: $0 [start|stop|restart|status]" >&2
        exit 2
        ;;
esac
