#!/bin/bash

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "[i] Updating package lists..."
sudo apt-get update || { echo "[!] Failed to update package lists"; exit 1; }

echo "[i] Installing Python3-OpenCV and venv..."
sudo apt-get install -y python3-opencv python3-venv || { echo "[!] Failed to install required packages"; exit 1; }

# Check if venv exists, if not create it
VENV_DIR="./venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[i] Creating virtual environment..."
    python3 -m venv $VENV_DIR || { echo "[!] Failed to create virtual environment"; exit 1; }
fi

# Activate virtual environment
echo "[i] Activating virtual environment..."
source $VENV_DIR/bin/activate || { echo "[!] Failed to activate virtual environment"; exit 1; }

# Install packages from requirements.txt
if [ -f "requirements.txt" ]; then
    echo "[i] Installing packages from requirements.txt..."
    pip install -r requirements.txt || { echo "[!] Failed to install packages from requirements.txt"; exit 1; }
else
    echo "[!] requirements.txt not found. Skipping package installation."
fi

echo "[i] Verifying OpenCV installation..."
if python -c "import cv2; print(cv2.__version__)" 2>/dev/null; then
    echo "[✓] OpenCV installed successfully"
else
    echo "[!] OpenCV installation verification failed"
    exit 1
fi

echo "[i] Installation complete. Virtual environment is active and packages are installed."
echo "[i] To deactivate the virtual environment, run 'deactivate'."
echo "[i] To activate it again, run 'source $VENV_DIR/bin/activate'."
