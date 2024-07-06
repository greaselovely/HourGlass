#!/bin/bash

# Function to check if command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "[!]\t$1 could not be found"
        return 1
    else
        echo -e "[✓]\t$1 is installed"
        return 0
    fi
}

install_debian() {
    echo -e "[i]\tUpdating package lists..."
    sudo apt-get update || { echo -e "[!]\tFailed to update package lists"; exit 1; }

    echo -e "[i]\tInstalling Python3-OpenCV and venv..."
    sudo apt-get install -y python3-opencv python3-venv || { echo -e "[!]\tFailed to install required packages"; exit 1; }

    check_command python3
    check_command pip3
}

install_rhel() {
    echo -e "[i]\tChecking for updates..."
    sudo dnf check-update
    local check_update_status=$?
    if [ $check_update_status -eq 1 ]; then
        echo -e "[!]\tFailed to check for updates"
        exit 1
    fi
    # No need to exit if updates are available (status 100) or if there are no updates (status 0)

    echo -e "[i]\tInstalling Python3-OpenCV and python3..."
    sudo dnf install -y python3-opencv python3 || { echo -e "[!]\tFailed to install required packages"; exit 1; }

    check_command python3
    check_command pip3
}

install_macos() {
    if ! check_command brew; then
        echo -e "[!]\tHomebrew is required for macOS. Please install it first."
        exit 1
    fi

    echo -e "[i]\tUpdating Homebrew..."
    brew update || { echo -e "[!]\tFailed to update Homebrew"; exit 1; }

    echo -e "[i]\tInstalling OpenCV and Python..."
    brew install opencv python || { echo -e "[!]\tFailed to install required packages"; exit 1; }

    check_command python3
    check_command pip3
}

# Detect system type and run appropriate function
if [ -f /etc/debian_version ]; then
    echo -e "[i]\tDetected Debian-based system."
    install_debian
elif [ -f /etc/redhat-release ]; then
    echo -e "[i]\tDetected RHEL-based system."
    install_rhel
elif [ "$(uname)" == "Darwin" ]; then
    echo -e "[i]\tDetected macOS."
    install_macos
else
    echo -e "[!]\tYour system is not supported by this script."
    exit 1
fi

# Check if venv exists, if not create it
VENV_DIR="./venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "[i]\tCreating virtual environment..."
    python3 -m venv $VENV_DIR || { echo -e "[!]\tFailed to create virtual environment"; exit 1; }
fi

# Activate virtual environment
echo -e "[i]\tActivating virtual environment..."
source $VENV_DIR/bin/activate || { echo -e "[!]\tFailed to activate virtual environment"; exit 1; }

# Install packages from requirements.txt
if [ -f "requirements.txt" ]; then
    echo -e "[i]\tInstalling packages from requirements.txt..."
    pip install -r requirements.txt || { echo -e "[!]\tFailed to install packages from requirements.txt"; exit 1; }
else
    echo -e "[!]\trequirements.txt not found. Skipping package installation."
fi

echo -e "[i]\tVerifying OpenCV installation..."
if python -c "import cv2; print(cv2.__version__)" 2>/dev/null; then
    echo -e "[✓]\tOpenCV installed successfully"
else
    echo -e "[!]\tOpenCV installation verification failed"
    exit 1
fi

echo -e "[i]\tInstallation complete. Virtual environment is active and packages are installed."
echo -e "[i]\tTo deactivate the virtual environment, run 'deactivate'."
echo -e "[i]\tTo activate it again, run 'source $VENV_DIR/bin/activate'."