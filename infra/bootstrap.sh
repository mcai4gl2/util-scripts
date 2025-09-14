#!/bin/bash

# Ubuntu VM Bootstrap Script
# One-click setup for Ubuntu cloud VMs with essential development tools
# Author: Generated with Claude Code
# Version: 1.0

set -euo pipefail

# Configuration
SCRIPT_NAME="Ubuntu VM Bootstrap"
VERSION="1.0"
LOG_FILE="/tmp/bootstrap.log"

# Detect the actual user (in case script is run with sudo)
if [ -n "${SUDO_USER:-}" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_HOME=$(eval echo "~$SUDO_USER")
else
    ACTUAL_USER=$(whoami)
    ACTUAL_HOME="$HOME"
fi

VENV_DIR="$ACTUAL_HOME/venv/bootstrap"
TMUX_CONF="$ACTUAL_HOME/.tmux.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    log "INFO: $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
    log "SUCCESS: $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    log "WARNING: $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log "ERROR: $1"
}

# Error handler
error_exit() {
    error "Script failed at line $1"
    error "Check log file: $LOG_FILE"
    exit 1
}

trap 'error_exit $LINENO' ERR

# Progress tracking
TOTAL_STEPS=8
CURRENT_STEP=0

step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    echo
    echo -e "${BLUE}=== Step $CURRENT_STEP/$TOTAL_STEPS: $1 ===${NC}"
    log "Starting step $CURRENT_STEP/$TOTAL_STEPS: $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if package is installed
package_installed() {
    dpkg -l | grep -qw "$1" 2>/dev/null
}

# Main script starts here
main() {
    # Initialize log file
    echo "=== $SCRIPT_NAME v$VERSION ===" > "$LOG_FILE"
    echo "Started at: $(date)" >> "$LOG_FILE"
    echo "Current user: $(whoami)" >> "$LOG_FILE"
    echo "Actual user: $ACTUAL_USER" >> "$LOG_FILE"
    echo "Target home: $ACTUAL_HOME" >> "$LOG_FILE"
    echo "System: $(uname -a)" >> "$LOG_FILE"
    echo >> "$LOG_FILE"

    echo -e "${BLUE}=== $SCRIPT_NAME v$VERSION ===${NC}"
    info "Starting bootstrap process..."
    info "Target user: $ACTUAL_USER (home: $ACTUAL_HOME)"
    info "Log file: $LOG_FILE"

    # Step 1: Pre-flight checks
    step "Pre-flight Checks"
    
    # Check if running on Ubuntu
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        error "This script is designed for Ubuntu systems only"
        exit 1
    fi
    
    UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null || echo "unknown")
    info "Detected Ubuntu $UBUNTU_VERSION"
    
    # Check sudo privileges
    if ! sudo -n true 2>/dev/null; then
        error "This script requires sudo privileges"
        exit 1
    fi
    success "Sudo privileges confirmed"
    
    # Check internet connectivity
    if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        error "No internet connectivity detected"
        exit 1
    fi
    success "Internet connectivity confirmed"

    # Step 2: System Updates
    step "System Updates"
    info "Updating package lists..."
    sudo apt update -qq
    
    info "Upgrading system packages..."
    sudo apt upgrade -y -qq
    success "System packages updated"

    # Step 3: Install Python Environment
    step "Python Environment Setup"
    
    PYTHON_PACKAGES="python3 python3-pip python3-venv python3-dev"
    info "Installing Python packages: $PYTHON_PACKAGES"
    sudo apt install -y $PYTHON_PACKAGES
    
    # Create python symlink if it doesn't exist
    if [ ! -f "/usr/bin/python" ]; then
        info "Creating python -> python3 symlink"
        sudo ln -sf /usr/bin/python3 /usr/bin/python
        success "Python symlink created"
    else
        info "Python symlink already exists"
    fi
    
    # Verify Python installation
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    success "Python $PYTHON_VERSION installed and configured"

    # Step 4: Install Development Tools
    step "Development Tools Installation"
    
    DEV_PACKAGES="git jq curl wget build-essential software-properties-common unzip tree"
    info "Installing development tools: $DEV_PACKAGES"
    sudo apt install -y $DEV_PACKAGES
    
    # Verify installations
    for tool in git jq curl wget; do
        if command_exists "$tool"; then
            success "$tool installed successfully"
        else
            warning "$tool installation may have failed"
        fi
    done

    # Step 5: Install and Configure tmux
    step "Tmux Installation and Configuration"
    
    if ! package_installed tmux; then
        info "Installing tmux..."
        sudo apt install -y tmux
    else
        info "tmux already installed"
    fi
    
    # Backup existing tmux config if it exists
    if [ -f "$TMUX_CONF" ]; then
        cp "$TMUX_CONF" "$TMUX_CONF.backup.$(date +%Y%m%d_%H%M%S)"
        info "Backed up existing tmux configuration"
    fi
    
    # Create tmux configuration
    info "Creating tmux configuration with Ctrl+A prefix at: $TMUX_CONF"
    cat > "$TMUX_CONF" << 'EOF'
# Ubuntu VM Bootstrap tmux configuration
# Prefix changed from Ctrl+B to Ctrl+A

# Change prefix from Ctrl+B to Ctrl+A
unbind C-b
set-option -g prefix C-a
bind-key C-a send-prefix

# Enable mouse support
set -g mouse on

# Improve colors
set -g default-terminal "screen-256color"

# Start window numbering at 1
set -g base-index 1
set -g pane-base-index 1

# Renumber windows when one is closed
set -g renumber-windows on

# Increase scrollback buffer size
set -g history-limit 10000

# More intuitive split commands
bind | split-window -h
bind - split-window -v

# Easy config reload
bind r source-file ~/.tmux.conf \; display-message "Config reloaded!"

# Status bar customization
set -g status-bg colour234
set -g status-fg colour137
set -g status-interval 1
EOF
    
    chmod 644 "$TMUX_CONF"
    
    # Verify tmux config was created
    if [ -f "$TMUX_CONF" ] && [ -s "$TMUX_CONF" ]; then
        success "tmux configured with Ctrl+A prefix ($(wc -l < "$TMUX_CONF") lines written)"
    else
        error "Failed to create tmux configuration file at $TMUX_CONF"
        exit 1
    fi

    # Step 6: Create Python Virtual Environment
    step "Python Virtual Environment Setup"
    
    if [ -d "$VENV_DIR" ]; then
        warning "Virtual environment already exists at $VENV_DIR"
        rm -rf "$VENV_DIR"
        info "Removed existing virtual environment"
    fi
    
    info "Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    
    # Activate virtual environment and install packages
    source "$VENV_DIR/bin/activate"
    
    info "Upgrading pip in virtual environment..."
    pip install --upgrade pip -q
    
    info "Installing useful packages in virtual environment..."
    pip install requests urllib3 -q
    
    deactivate
    success "Virtual environment created with useful packages installed"

    # Step 7: Validation Tests
    step "Validation Tests"
    
    # Test Python
    if python --version >/dev/null 2>&1; then
        success "Python command working: $(python --version 2>&1)"
    else
        error "Python command not working"
    fi
    
    # Test pip
    if pip --version >/dev/null 2>&1; then
        success "pip working: $(pip --version | cut -d' ' -f1-2)"
    else
        warning "pip may not be working correctly"
    fi
    
    # Test essential tools
    for tool in git jq curl wget tmux; do
        if command_exists "$tool"; then
            version_info=""
            case "$tool" in
                git) version_info=$(git --version | cut -d' ' -f3) ;;
                jq) version_info=$(jq --version | cut -d'-' -f2) ;;
                tmux) version_info=$(tmux -V | cut -d' ' -f2) ;;
                *) version_info="installed" ;;
            esac
            success "$tool: $version_info"
        else
            warning "$tool not found in PATH"
        fi
    done
    
    # Test tmux configuration
    if [ -f "$TMUX_CONF" ] && grep -q "prefix C-a" "$TMUX_CONF" 2>/dev/null; then
        success "tmux configuration validated (Ctrl+A prefix configured)"
    else
        warning "tmux configuration file missing or incomplete"
    fi
    
    # Test virtual environment
    if [ -f "$VENV_DIR/bin/activate" ]; then
        # Test that packages are installed in venv and pathlib touch works
        source "$VENV_DIR/bin/activate"
        if python -c "import requests, urllib3; from pathlib import Path; Path('/tmp/test_touch').touch()" 2>/dev/null; then
            success "Virtual environment with packages validated (pathlib touch works)"
            rm -f /tmp/test_touch
        else
            warning "Virtual environment exists but package validation failed"
        fi
        deactivate
    else
        warning "Virtual environment validation failed"
    fi

    # Step 8: Final Summary
    step "Bootstrap Complete"
    
    echo
    echo -e "${GREEN}=== Installation Summary ===${NC}"
    echo -e "Python: $(python --version 2>&1) (symlinked)"
    echo -e "tmux: Prefix remapped to ${YELLOW}Ctrl+A${NC}"
    echo -e "Virtual Environment: ${BLUE}$VENV_DIR${NC} (with requests, urllib3)"
    echo -e "Development Tools: git, jq, curl, wget, build-essential"
    echo
    echo -e "${BLUE}Usage Examples:${NC}"
    echo -e "  Activate venv: ${YELLOW}source $VENV_DIR/bin/activate${NC}"
    echo -e "  Start tmux: ${YELLOW}tmux${NC} (use Ctrl+A as prefix)"
    echo -e "  Check installations: ${YELLOW}git --version && jq --version${NC}"
    echo
    echo -e "${GREEN}Bootstrap completed successfully!${NC}"
    echo -e "Log file: ${BLUE}$LOG_FILE${NC}"
    
    # Final log entry
    log "Bootstrap completed successfully at $(date)"
    log "Total steps completed: $TOTAL_STEPS"
}

# Handle script interruption
cleanup() {
    echo
    warning "Script interrupted by user"
    log "Script interrupted at $(date)"
    exit 130
}

trap cleanup SIGINT SIGTERM

# Print usage information
usage() {
    echo "Usage: $0"
    echo
    echo "Ubuntu VM Bootstrap Script v$VERSION"
    echo "Sets up essential development tools and configurations."
    echo
    echo "This script will:"
    echo "  - Update system packages"
    echo "  - Install Python 3 with pip and venv"
    echo "  - Create python -> python3 symlink"
    echo "  - Install development tools (git, jq, curl, wget, etc.)"
    echo "  - Configure tmux with Ctrl+A prefix"
    echo "  - Create Python virtual environment with touch package"
    echo
    echo "Requirements:"
    echo "  - Ubuntu 18.04, 20.04, 22.04, or 24.04"
    echo "  - sudo privileges"
    echo "  - Internet connection"
    echo
    echo "Log file: $LOG_FILE"
}

# Handle command line arguments
case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
    -v|--version)
        echo "$SCRIPT_NAME v$VERSION"
        exit 0
        ;;
    "")
        main
        ;;
    *)
        echo "Unknown option: $1"
        usage
        exit 1
        ;;
esac