#!/usr/bin/env bash

# Check if we're already in a tmux session
if [ -n "$TMUX" ]; then
    echo "Already in a tmux session. Running vla directly."
    source venv/bin/activate && python vla.py
    exit 0
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Please install it and try again."
    exit 1
fi

# Get the log file path from vla.py with error handling and debugging
LOG_FILE=$(bash -c "source venv/bin/activate && python3 -c \"
import sys
import os

# Add the current directory to Python path
sys.path.append(os.getcwd())

try:
    import vla
    print(vla.LOGGING_FILE)
except ImportError as e:
    print(f'Error importing vla: {e}', file=sys.stderr)
    sys.exit(1)
except AttributeError as e:
    print(f'Error accessing LOGGING_FILE: {e}', file=sys.stderr)
    sys.exit(1)
\"")

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
    exit 0
fi

# Start tmux session
exec tmux new-session -s vla-timelapse \; \
    split-window -h \; \
    select-pane -t 0 \; \
    send-keys "source venv/bin/activate && python vla.py" C-m \; \
    select-pane -t 1 \; \
    send-keys "tail -f '$LOG_FILE'" C-m