#!/bin/bash
# setup.sh

# Check Python version
check_python_version() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
        
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -eq 12 ]; then
            echo -e "[✓]\tPython 3.12 detected"
            return 0
        else
            echo -e "[!]\tPython $PYTHON_VERSION detected. This project requires Python 3.12"
            echo -e "[i]\tPython 3.13+ has compatibility issues with some dependencies"
            echo -e "[i]\tPlease install Python 3.12 and try again"
            return 1
        fi
    else
        echo -e "[!]\tPython 3 not found"
        return 1
    fi
}

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
    echo -e "[i]\tInstalling Python3-OpenCV, venv..."
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
    check_command python3
    check_command pip3
}

install_opensuse() {
    echo -e "[i]\tUpdating package lists..."
    sudo zypper refresh || { echo -e "[!]\tFailed to update package lists"; exit 1; }
    echo -e "[i]\tInstalling Python3-OpenCV, python3"
    sudo zypper install -y python3-opencv python3 python3-pip || { echo -e "[!]\tFailed to install required packages"; exit 1; }
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
    echo -e "[i]\tInstalling OpenCV, Python"
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
elif [ -f /etc/SuSE-release ] || [ -f /etc/SUSE-brand ]; then
    echo -e "[i]\tDetected openSUSE system."
    install_opensuse
elif [ "$(uname)" == "Darwin" ]; then
    echo -e "[i]\tDetected macOS."
    install_macos
else
    echo -e "[!]\tYour system is not supported by this script."
    exit 1
fi

# Verify Python version before proceeding
if ! check_python_version; then
    echo -e "[!]\tSetup cannot continue without Python 3.12"
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

# Upgrade pip
echo -e "[i]\tUpgrading pip..."
pip install --upgrade pip || { echo -e "[!]\tFailed to upgrade pip"; exit 1; }

# Install packages from requirements.txt
if [ -f "requirements.txt" ]; then
    echo -e "[i]\tInstalling packages from requirements.txt..."
    pip install -r requirements.txt || { echo -e "[!]\tFailed to install packages from requirements.txt"; exit 1; }
else
    echo -e "[!]\trequirements.txt not found. Skipping package installation."
fi

echo -e "[i]\tVerifying core dependencies..."
if python -c "import cv2; print('OpenCV version:', cv2.__version__)" 2>/dev/null; then
    echo -e "[✓]\tOpenCV installed successfully"
else
    echo -e "[!]\tOpenCV installation verification failed"
    exit 1
fi

echo -e "[i]\tVerifying Operation Telescope dependencies..."

# Verify psutil (system monitoring)
if python -c "import psutil; print('psutil version:', psutil.__version__)" 2>/dev/null; then
    echo -e "[✓]\tpsutil installed successfully"
else
    echo -e "[!]\tpsutil installation verification failed"
    exit 1
fi

# Verify PIL/Pillow (enhanced image validation)
if python -c "import PIL; print('Pillow version:', PIL.__version__)" 2>/dev/null; then
    echo -e "[✓]\tPillow installed successfully"
else
    echo -e "[!]\tPillow installation verification failed"
    exit 1
fi

# Verify other key dependencies
echo -e "[i]\tVerifying additional dependencies..."

if python -c "import requests, bs4, moviepy, numpy" 2>/dev/null; then
    echo -e "[✓]\tCore Python packages verified"
else
    echo -e "[!]\tSome core Python packages failed verification"
    exit 1
fi

echo -e "[✓]\tAll Operation Telescope dependencies verified"

# ===== STATUS API SERVICE (Linux only) =====
install_status_api_service() {
  local unit_name="hourglass-status.service"
  local unit_template="${SCRIPT_DIR}/hourglass-status.service"
  local unit_dest="/etc/systemd/system/${unit_name}"
  local tmp_unit="/tmp/${unit_name}.tmp"

  if [[ ! -f "$unit_template" ]]; then
    echo -e "[!]\t${unit_template} not found, skipping service install"
    return 0
  fi

  local venv_abs
  venv_abs="$(cd "${SCRIPT_DIR}" && realpath venv)"
  local repo_abs
  repo_abs="$(cd "${SCRIPT_DIR}" && pwd)"
  local run_user
  run_user="$(whoami)"

  # Generate unit file with actual paths
  sed -e "s|%USER%|${run_user}|g" \
      -e "s|%VENV%|${venv_abs}|g" \
      -e "s|%REPO%|${repo_abs}|g" \
      "$unit_template" > "$tmp_unit"

  # Compare with installed version — skip if unchanged
  if [[ -f "$unit_dest" ]] && diff -q "$tmp_unit" "$unit_dest" >/dev/null 2>&1; then
    echo -e "[i]\tStatus API service unchanged, skipping"
    rm -f "$tmp_unit"
    # Ensure it's running
    if ! systemctl is-active --quiet "$unit_name"; then
      echo -e "[i]\tStarting status API service..."
      sudo systemctl start "$unit_name"
    fi
    return 0
  fi

  echo -e "[i]\tInstalling status API systemd service..."
  if ! sudo cp "$tmp_unit" "$unit_dest" 2>/dev/null; then
    echo -e "[!]\tFailed to install service (sudo required). Skipping."
    echo -e "[i]\tTo install manually: sudo cp ${tmp_unit} ${unit_dest} && sudo systemctl daemon-reload && sudo systemctl enable --now ${unit_name}"
    rm -f "$tmp_unit"
    return 0
  fi
  rm -f "$tmp_unit"
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$unit_name"
  echo -e "[✓]\tStatus API service installed and started"
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "$(uname)" != "Darwin" ]]; then
  if command -v systemctl &>/dev/null; then
    install_status_api_service
  else
    echo -e "[i]\tsystemd not found — skipping status API service install"
  fi
else
  echo -e "[i]\tmacOS detected — skipping status API service install (server-side only)"
fi

echo -e "[i]\tInstallation complete. Virtual environment and packages are installed."
echo -e "[i]\tYou can now run: ./hourglass.sh or python main.py"