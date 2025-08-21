#!/usr/bin/env bash
# hourglass.sh
set -euo pipefail

PROJECT_NAME="${1:-}"
if [ -z "$PROJECT_NAME" ]; then
    echo "Error: Project name is required"
    echo "Usage: $0 <project_name> [options]"
    exit 1
fi

CONFIG_FILE="configs/${PROJECT_NAME}.json"
shift

run_python_command() {
    venv/bin/python3 -c "$1"
}

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE"
    echo "Please run: python timelapse_setup.py"
    exit 1
fi

# If already inside tmux, just run directly
if [ -n "${TMUX:-}" ]; then
    echo "Already in a tmux session. Running HourGlass directly."
    exec venv/bin/python3 main.py "$PROJECT_NAME" "$@"
fi

# Require tmux
if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux is not installed. Please install it and try again."
    exit 1
fi

# Pull log path and session name from config
CONFIG_DATA=$(run_python_command "
import sys, os, json
with open('$CONFIG_FILE','r') as f: config=json.load(f)
log_file = os.path.join(config['files_and_folders']['LOGGING_FOLDER'], config['files_and_folders']['LOG_FILE_NAME'])
session_name = config.get('tmux', {}).get('session_name', 'hourglass-timelapse')
print(f'{log_file}|{session_name}')
")
IFS='|' read -r LOG_FILE SESSION_NAME <<< "$CONFIG_DATA"
if [ -z "$LOG_FILE" ]; then
    echo "Failed to get configuration"
    exit 1
fi

echo "Log file path: $LOG_FILE"
echo "Session name: $SESSION_NAME"

# Interactive check: 1 if stdout is a TTY, else 0
INTERACTIVE=0
if [ -t 1 ]; then INTERACTIVE=1; fi

# If session exists already
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists."
    if [ "$INTERACTIVE" -eq 1 ]; then
        exec tmux attach -t "$SESSION_NAME"
    else
        # From cron: do not try to attach. Treat as already running.
        exit 0
    fi
fi

# Build the python command
ARGS="$*"
PYTHON_CMD="venv/bin/python3 main.py $PROJECT_NAME $ARGS"

# Ensure tmux does not keep dead panes
tmux set -g remain-on-exit off >/dev/null 2>&1 || true

if [ "$INTERACTIVE" -eq 1 ]; then
    # Interactive: create session, tail pane, then attach
    tmux new-session -d -s "$SESSION_NAME"
    tmux send-keys -t "$SESSION_NAME" \
        "echo 'Starting HourGlass Timelapse System...'; $PYTHON_CMD; EXIT=\$?; tmux display-message 'HourGlass finished with code '\$EXIT; tmux kill-session -t \"$SESSION_NAME\"; exit \$EXIT" C-m
    tmux split-window -t "$SESSION_NAME" -v -l 20
    tmux select-pane -t "$SESSION_NAME":0.1
    tmux send-keys -t "$SESSION_NAME":0.1 "sleep 5; tail -f '$LOG_FILE' || echo 'Failed to tail log file'" C-m
    exec tmux attach -t "$SESSION_NAME"
else
    # Cron: start detached and auto-kill session when done. No attach, no tail.
    tmux new-session -d -s "$SESSION_NAME" \
        "bash -lc '$PYTHON_CMD; EXIT=\$?; tmux display-message \"HourGlass finished with code \$EXIT\"; tmux kill-session -t \"$SESSION_NAME\"; exit \$EXIT'"
    echo "Started detached tmux session '$SESSION_NAME'."
fi
