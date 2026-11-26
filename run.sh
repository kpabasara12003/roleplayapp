#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh - start the whole roleplay stack in one terminal.
#
#   ./run.sh          (or: bash run.sh)
#
# Starts four processes from the repository root:
#   gateway      python -m fastapi_server.run
#   chronicler   python -m chronicler_agent.app.agent
#   director     python -m director_agent.app.agent
#   actor        python -m actor_agent.app.agent
#
# Each process writes to logs/<name>.log and its output is echoed here with a
# [name] prefix. Press Ctrl+C once to stop everything.
# ---------------------------------------------------------------------------
set -u

cd "$(dirname "$0")" || exit 1

# --- locate the interpreter -------------------------------------------------
PY=""
for candidate in \
    "venv/Scripts/python.exe" \
    "venv/bin/python" \
    ".venv/Scripts/python.exe" \
    ".venv/bin/python"
do
    if [ -x "$candidate" ]; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PY="python3"
    elif command -v python >/dev/null 2>&1; then
        PY="python"
    fi
fi
if [ -z "$PY" ]; then
    echo "error: no Python found. Create the venv first (venv/Scripts/python.exe or venv/bin/python)."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "error: .env not found in $(pwd)."
    echo "       Every service reads .env relative to the working directory, so run this from the repo root."
    exit 1
fi

# --- read the port from .env (optional) -------------------------------------
API_PORT="$(sed -n 's/^[[:space:]]*API_PORT[[:space:]]*=[[:space:]]*//p' .env | tr -d '\r "' | tail -n 1)"
API_PORT="${API_PORT:-8000}"
BASE_URL="http://127.0.0.1:${API_PORT}"

# --- health probing ---------------------------------------------------------
# The services may be Windows executables (venv/Scripts/python.exe) even when
# this script runs under WSL. curl inside WSL probes the WSL network
# namespace and can never reach a Windows-bound port, so probe with the same
# interpreter the services use: it runs in the same namespace as the servers.
port_answering() {
    "$PY" tools/health_probe.py "http://127.0.0.1:${1}/health" --any >/dev/null 2>&1
}

gateway_healthy() {
    "$PY" tools/health_probe.py "http://127.0.0.1:${1}/health" >/dev/null 2>&1
}

if port_answering "${API_PORT}"; then
    echo "error: something is already answering on ${BASE_URL}."
    echo "       Stop it first, then run ./run.sh again."
    exit 1
fi

mkdir -p logs

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

pids=()
names=()
followers=()

# --- teardown ---------------------------------------------------------------
# On Windows the venv's python.exe is a launcher that spawns the real
# interpreter as a child, so killing the pid we started is not enough: kill the
# whole process tree via taskkill. Elsewhere a plain TERM/KILL is sufficient.
stop_service() {
    local pid="$1"
    [ -n "$pid" ] || return 0

    if [ -r "/proc/${pid}/winpid" ] && command -v taskkill >/dev/null 2>&1; then
        local winpid
        winpid="$(cat "/proc/${pid}/winpid" 2>/dev/null)"
        if [ -n "$winpid" ]; then
            taskkill //PID "$winpid" //T //F >/dev/null 2>&1 && return 0
        fi
    fi

    kill "$pid" 2>/dev/null
    sleep 0.2
    kill -9 "$pid" 2>/dev/null
}

cleanup() {
    trap - INT TERM EXIT
    echo
    echo "stopping roleplay stack..."

    if [ "${#pids[@]}" -gt 0 ]; then
        for pid in "${pids[@]}"; do
            stop_service "$pid"
        done
    fi

    # Each follower runs `tail --pid=<service>`, so it exits by itself once the
    # service is gone. Give them a moment, then clean up whatever is left.
    for pid in ${followers[@]+"${followers[@]}"}; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
    done
    sleep 1
    for pid in ${followers[@]+"${followers[@]}"}; do
        [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
    done

    echo "stopped."
}
trap cleanup INT TERM EXIT

# --- start one service ------------------------------------------------------
start_service() {
    local name="$1"
    shift
    : > "logs/${name}.log"
    "$@" > "logs/${name}.log" 2>&1 &
    local pid=$!
    pids+=("$pid")
    names+=("$name")
    printf '  %-11s started (pid %s) -> logs/%s.log\n' "$name" "$pid" "$name"
}

echo "using $PY"
echo "starting services from $(pwd)"
echo
"$PY" -m shared.db.migrate || exit 1
start_service outbox     "$PY" -m shared.outbox
start_service gateway    "$PY" -m fastapi_server.run
GATEWAY_PID="${pids[${#pids[@]}-1]}"
start_service chronicler "$PY" -m chronicler_agent.app.agent
start_service director   "$PY" -m director_agent.app.agent
start_service actor      "$PY" -m actor_agent.app.agent

# --- wait for the gateway ---------------------------------------------------
echo
echo -n "waiting for the gateway on ${BASE_URL} "
ready=0
for _ in $(seq 1 60); do
    if gateway_healthy "${API_PORT}"; then
        ready=1
        break
    fi
    # Bail out early if the gateway process already died.
    if ! kill -0 "${GATEWAY_PID}" 2>/dev/null; then
        break
    fi
    echo -n "."
    sleep 0.5
done
echo

if [ "$ready" -ne 1 ]; then
    echo
    echo "the gateway did not become healthy. Last lines of logs/gateway.log:"
    echo "-----------------------------------------------------------------"
    tail -n 30 logs/gateway.log 2>/dev/null
    echo "-----------------------------------------------------------------"
    exit 1
fi

# --- follow every log in this terminal --------------------------------------
for i in "${!names[@]}"; do
    name="${names[$i]}"
    tail --pid="${pids[$i]}" -n +1 -f "logs/${name}.log" 2>/dev/null \
        | sed -u "s/^/[${name}] /" &
    followers+=("$!")
done

printf '\n'
printf '  gateway    %s\n' "$BASE_URL"
printf '  api docs   %s/docs\n' "$BASE_URL"
printf '\n  press Ctrl+C to stop the whole stack\n\n'

# Block until the gateway exits (Ctrl+C is handled by the trap above).
while true; do
    for i in "${!pids[@]}"; do
        if ! kill -0 "${pids[$i]}" 2>/dev/null; then
            echo "${names[$i]} exited; shutting down the stack."
            exit 1
        fi
    done
    sleep 1
done
echo
echo "gateway exited; shutting down the rest."
