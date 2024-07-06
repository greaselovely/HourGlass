#!/bin/bash

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
elif [ "$(uname)" == "Darwin" ]; then
    OS="macOS"
else
    echo "[!] Unsupported operating system"
    exit 1
fi

# Set package manager and install commands based on OS
case $OS in
    "Ubuntu" | "Debian GNU/Linux")
        PKG_MANAGER="apt-get"
        UPDATE_CMD="sudo $PKG_MANAGER update"
        INSTALL_CMD="sudo $PKG_MANAGER install -y"
        PACKAGES="python3-opencv python3-venv"
        ;;
    "Red Hat Enterprise Linux" | "CentOS Linux" | "Fedora")
        PKG_MANAGER="dnf"
        UPDATE_CMD="sudo $PKG_MANAGER check-update"
        INSTALL_CMD="sudo $PKG_MANAGER install -y"
        PACKAGES="python3-opencv python3"
        ;;
    "macOS")
        if ! command_exists brew; then
            echo "[!] Homebrew is required for macOS. Please install it first."
            exit 1
        fi
        PKG_MANAGER="brew"
        UPDATE_CMD="brew update"
        INSTALL_CMD="brew install"
        PACKAGES="opencv python"
        ;;
    *)
        echo "[!] Unsupported operating system: $OS"
        exit 1
        ;;
esac

echo "[i] Updating package lists..."
$UPDATE_CMD || { echo "[!] Failed to update package lists"; exit 1; }

echo "[i] Installing required packages..."
$INSTALL_CMD $PACKAGES || { echo "[!] Failed to install required packages"; exit 1; }

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