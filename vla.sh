#!/bin/bash

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Please install it and try again."
    exit 1
fi

# Function to run vla.py
vla() {
    source venv/bin/activate && python vla.py
}
export -f vla

# Get the log file path from vla.py with error handling and debugging
LOG_FILE=$(python3 -c "
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
" 2>&1)

# Check if LOG_FILE is empty or contains an error message
if [ -z "$LOG_FILE" ] || [[ "$LOG_FILE" == Error* ]]; then
    echo "Failed to get log file path: $LOG_FILE"
    exit 1
fi

echo "Log file path: $LOG_FILE"

# Check if the session already exists
if tmux has-session -t vla-timelapse 2>/dev/null; then
    echo "Session 'vla-timelapse' already exists. Attaching to it."
    tmux attach-session -t vla-timelapse
    exit 0
fi

# Start tmux session
tmux new-session -d -s vla-timelapse

# Split the window vertically
tmux split-window -h

# Resize the left pane
tmux resize-pane -L 10

# Run the commands in each pane
tmux send-keys -t 0 'vla' C-m
tmux send-keys -t 1 "tail -f '$LOG_FILE'" C-m

# Attach to the session
tmux attach-session -t vla-timelapse