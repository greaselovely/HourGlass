#!/usr/bin/env bash

set -e  # Exit immediately if a command exits with a non-zero status.

# Function to activate virtual environment and run Python command
run_python_command() {
    venv/bin/python3 -c "$1"
}

# Check if we're already in a tmux session
if [ -n "$TMUX" ]; then
    echo "Already in a tmux session. Running vla directly."
    run_python_command "import __main__; __main__.main()"
    exit 0
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Please install it and try again."
    exit 1
fi

# Get the log file path
LOG_FILE=$(run_python_command "
import sys
import os

# Add the current directory to Python path
sys.path.append(os.getcwd())

try:
    from vla_config import LOGGING_FILE
    print(LOGGING_FILE)
except ImportError as e:
    print(f'Error importing vla_config: {e}', file=sys.stderr)
    sys.exit(1)
except AttributeError as e:
    print(f'Error accessing LOGGING_FILE: {e}', file=sys.stderr)
    sys.exit(1)
")

# Check if LOG_FILE is empty or contains an error message
if [ -z "$LOG_FILE" ] || [[ "$LOG_FILE" == Error* ]]; then
    echo "Failed to get log file path: $LOG_FILE"
    exit 1
fi

echo "Log file path: $LOG_FILE"

# Check if the session already exists
if tmux has-session -t vla-timelapse 2>/dev/null; then
    echo "Session 'vla-timelapse' already exists. Attaching to it."
    exec tmux attach-session -t vla-timelapse
fi

exec tmux new-session -s vla-timelapse \; \
    send-keys "echo 'Starting main script...'; venv/bin/python ../VLA" C-m \; \
    split-window -v -l 50 \; \
    select-pane -t 1 \; \
    send-keys "sleep 5 && tail -f '$LOG_FILE' || echo 'Failed to tail log file'" C-m \; \
    select-pane -t 0