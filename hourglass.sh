#!/usr/bin/env bash
# hourglass.sh
set -e

# Function to activate virtual environment and run Python command
run_python_command() {
    venv/bin/python3 -c "$1"
}

# Check if config.json exists, if not run initial setup
if [ ! -f "config.json" ]; then
    echo "No configuration found. Running initial setup..."
    venv/bin/python3 initial_setup.py
    if [ $? -ne 0 ]; then
        echo "Setup failed. Please run initial_setup.py manually."
        exit 1
    fi
fi

# Check if we're already in a tmux session
if [ -n "$TMUX" ]; then
    echo "Already in a tmux session. Running HourGlass directly."
    run_python_command "import main; main.main()"
    exit 0
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Please install it and try again."
    exit 1
fi

# Get the log file path and session name from config
CONFIG_DATA=$(run_python_command "
import sys
import os
import json
sys.path.append(os.getcwd())
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    log_file = os.path.join(config['files_and_folders']['LOGGING_FOLDER'], config['files_and_folders']['LOG_FILE_NAME'])
    session_name = config.get('tmux', {}).get('session_name', 'hourglass-timelapse')
    print(f'{log_file}|{session_name}')
except Exception as e:
    print(f'Error reading config: {e}', file=sys.stderr)
    sys.exit(1)
")

# Split the output
IFS='|' read -r LOG_FILE SESSION_NAME <<< "$CONFIG_DATA"

# Check if LOG_FILE is empty or contains an error message
if [ -z "$LOG_FILE" ] || [[ "$LOG_FILE" == Error* ]]; then
    echo "Failed to get configuration: $LOG_FILE"
    exit 1
fi

echo "Log file path: $LOG_FILE"
echo "Session name: $SESSION_NAME"

# Check if the session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching to it."
    exec tmux attach-session -t "$SESSION_NAME"
fi

# Pass any arguments to the Python script (like --no-time-check)
ARGS="$*"

exec tmux new-session -s "$SESSION_NAME" \; \
    send-keys "echo 'Starting HourGlass Timelapse System...'; venv/bin/python main.py $ARGS" C-m \; \
    split-window -v -l 20 \; \
    select-pane -t 1 \; \
    send-keys "sleep 5 && tail -f '$LOG_FILE' || echo 'Failed to tail log file'" C-m \; \
    select-pane -t 0