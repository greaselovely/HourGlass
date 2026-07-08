#!/usr/bin/env bash
# restart.sh — cleanly restart a HourGlass project.
#
# Kills the project's capture tmux session (and any stray main.py), restarts the
# status API systemd service, then relaunches capture exactly the way cron does
# (non-interactive + detached, same log). Capture resumes today's existing image
# folder, so restarting mid-day does NOT lose already-captured frames.
#
# Usage: ./restart.sh [PROJECT] [--no-service]   (PROJECT default: VLA)
#   --no-service   skip the sudo systemctl restart of the status API (bounce
#                  only the capture; lets the script run without sudo)
set -euo pipefail

PROJECT="VLA"
NO_SERVICE=0
for arg in "$@"; do
    case "$arg" in
        --no-service) NO_SERVICE=1 ;;
        -*) echo "Unknown option: $arg" >&2; exit 1 ;;
        *)  PROJECT="$arg" ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_LOG="${HOME}/hourglass_cron.log"          # same log the 05:00 cron writes to
STATUS_UNIT="hourglass-status"                 # system service (see setup.sh)

cd "$SCRIPT_DIR"

CONFIG_FILE="configs/${PROJECT}.json"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config not found: ${SCRIPT_DIR}/${CONFIG_FILE}" >&2
    exit 1
fi

# Session name straight from config — the same source hourglass.sh uses.
SESSION_NAME="$(venv/bin/python3 -c "import json;print(json.load(open('$CONFIG_FILE')).get('tmux',{}).get('session_name','hourglass-timelapse'))")"

echo "== Restarting HourGlass '${PROJECT}'  (tmux session: ${SESSION_NAME}) =="

# 1) Kill the capture tmux session (SIGHUPs its main.py child with it).
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "[*] Killing tmux session ${SESSION_NAME}"
    tmux kill-session -t "$SESSION_NAME"
else
    echo "[*] No tmux session ${SESSION_NAME} to kill"
fi

# 2) Reap any stray main.py for THIS project only (surgical — matches the arg,
#    so it never touches other projects or the status service).
if pgrep -f "main.py ${PROJECT}" >/dev/null 2>&1; then
    echo "[*] Reaping stray 'main.py ${PROJECT}' process(es)"
    pkill -f "main.py ${PROJECT}" || true
    sleep 1
fi

# 3) Restart the status API systemd service. Non-fatal: a sudo hiccup must not
#    leave capture dead, so we warn and continue to step 4 regardless.
if [[ "$NO_SERVICE" -eq 1 ]]; then
    echo "[*] Skipping status service restart (--no-service)"
elif systemctl list-unit-files 2>/dev/null | grep -q "^${STATUS_UNIT}\.service"; then
    echo "[*] Restarting ${STATUS_UNIT} service (sudo)"
    sudo systemctl restart "${STATUS_UNIT}" \
        || echo "[!] Failed to restart ${STATUS_UNIT} (sudo?) — continuing"
else
    echo "[!] ${STATUS_UNIT} service not found — skipping"
fi

# 4) Relaunch capture exactly like cron: redirect stdout so hourglass.sh sees a
#    non-TTY and starts detached (instead of trying to attach), same log target.
echo "[*] Launching capture: hourglass.sh ${PROJECT}"
bash hourglass.sh "$PROJECT" >>"$CRON_LOG" 2>&1

sleep 2
echo "== Post-restart state =="
tmux ls 2>/dev/null || echo "  (no tmux sessions)"
echo "  ${STATUS_UNIT}: $(systemctl is-active "${STATUS_UNIT}" 2>/dev/null || echo unknown)"
echo "Done. Capture log -> ${CRON_LOG}"
