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

# Get the log file path from vla.py
LOG_FILE=$(python3 -c "
import os
from pathlib import Path

HOME = Path.home()
VLA_BASE = os.path.join(HOME, 'VLA')
LOGGING_FOLDER = os.path.join(VLA_BASE, 'logging')
LOG_FILE_NAME = 'vla_log.txt'
LOGGING_FILE = os.path.join(LOGGING_FOLDER, LOG_FILE_NAME)
print(LOGGING_FILE)
")

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