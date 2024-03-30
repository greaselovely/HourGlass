#!/bin/bash

# You can use this to start a tmux session and start tailing the log file for visibility.
# 1: Update the alias command below to where you installed this repo.  
# 2: Setup a venv for this repo (python3.12 -m venv venv)
# 3: source venv/bin/activate
# 4: pip install -r requirements.txt
# 5: Use this script moving forward to start your capture.

alias vla='cd projects/python/VLA && source venv/bin/activate && venv/bin/python3.12 vla.py'

# Start tmux session
tmux new-session -d -s vla-timelapse

# Split the window vertically
tmux split-window -h

# Resize the left pane
tmux resize-pane -L 10

# Run the commands in each pane
tmux send-keys -t 0 'vla' C-m
tmux send-keys -t 1 'tail -f ~/VLA/logging/vla_log.txt' C-m

# Attach to the session
tmux attach-session -t vla-timelapse