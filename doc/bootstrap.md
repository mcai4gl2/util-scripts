# Ubuntu VM Bootstrap Requirements

A comprehensive one-click setup script for Ubuntu cloud VMs with essential development tools and configurations.

## Overview

The bootstrap script provides automated setup for fresh Ubuntu VMs, installing and configuring all necessary tools for development and system administration work.

## System Requirements

- **OS**: Ubuntu 18.04, 20.04, 22.04, or 24.04 LTS
- **Architecture**: x86_64 (amd64) or ARM64
- **Privileges**: sudo access required
- **Network**: Internet connection for package downloads

## Components to Install

### 1. Python Environment

**Requirements:**
- Python 3 (system default version)
- pip (Python package manager)
- python3-venv (virtual environment support)
- python3-dev (development headers)

**Configuration:**
- Create symlink: `/usr/bin/python` → `/usr/bin/python3`
- Verify pip is working and up-to-date
- Create a virtual environment in `~/venv/bootstrap` with `touch` package installed

**Rationale:**
- Many scripts expect `python` command to work
- Virtual environments prevent system package conflicts
- `touch` package provides file manipulation utilities

### 2. Terminal Multiplexer (tmux)

**Requirements:**
- Install latest available tmux package
- Create custom configuration file

**Configuration File (`~/.tmux.conf`):**
```bash
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
```

**Rationale:**
- Ctrl+A is more ergonomic than Ctrl+B
- Mouse support improves usability
- Better defaults for development work

### 3. Essential Development Tools

**Core Tools:**
- `git` - Version control system
- `jq` - JSON processor and parser
- `curl` - HTTP client for API calls
- `wget` - File downloader
- `build-essential` - Compilation tools (gcc, make, etc.)
- `software-properties-common` - Repository management

**System Tools:**
- `awk` - Text processing (usually pre-installed)
- `sed` - Stream editor (usually pre-installed)
- `grep` - Text search (usually pre-installed)
- `unzip` - Archive extraction
- `tree` - Directory structure visualization

**Rationale:**
- Essential for most development and automation tasks
- Commonly expected to be available on dev systems
- Minimal overhead but maximum utility

## Implementation Approach

### 1. Pre-flight Checks

- Verify running on Ubuntu
- Check for sudo privileges
- Test internet connectivity
- Check available disk space

### 2. System Updates

```bash
sudo apt update
sudo apt upgrade -y
```

### 3. Package Installation

- Install all packages in a single apt command for efficiency
- Use `-y` flag for non-interactive installation
- Install recommended packages but skip suggested ones

### 4. Configuration Setup

- Create configuration files with proper permissions
- Backup existing configurations before overwriting
- Use idempotent operations (safe to run multiple times)

### 5. Validation

- Test each installed tool
- Verify configurations are working
- Report any issues or missing components

### 6. Python Virtual Environment

```bash
python3 -m venv ~/venv/bootstrap
source ~/venv/bootstrap/bin/activate
pip install --upgrade pip
pip install touch
```

## Error Handling Strategy

### Logging
- All operations logged with timestamps
- Separate log levels: INFO, WARNING, ERROR
- Log file: `/tmp/bootstrap.log`

### Error Recovery
- Continue on non-critical errors
- Abort on critical failures (network, permissions)
- Provide clear error messages with suggested solutions

### Idempotency
- Check if tools are already installed before installing
- Safe to run multiple times without side effects
- Skip configurations that are already correct

## Security Considerations

- Use official Ubuntu repositories only
- Verify package signatures
- Set appropriate file permissions (644 for configs, 755 for scripts)
- Don't run as root unnecessarily
- Clean up temporary files

## Output Format

### Progress Indicators
- Clear step-by-step progress messages
- Success/failure indicators for each component
- Final summary with installation results

### Example Output:
```
=== Ubuntu VM Bootstrap Script ===
[INFO] Checking system requirements...
[INFO] Updating package lists...
[INFO] Installing Python environment...
[OK] Python 3.10.12 installed successfully
[INFO] Configuring tmux...
[OK] tmux configuration created at ~/.tmux.conf
[INFO] Installing development tools...
[OK] All development tools installed
[INFO] Creating Python virtual environment...
[OK] Virtual environment created with touch package
[INFO] Running validation tests...
[OK] All components validated successfully

=== Bootstrap Complete ===
Python: /usr/bin/python3 -> /usr/bin/python
Tmux: Prefix remapped to Ctrl+A
Virtual Env: ~/venv/bootstrap (with touch package)
Tools: git, jq, curl, wget, build-essential

Total time: 2m 34s
Log file: /tmp/bootstrap.log
```

## Usage Modes

### 1. Direct Execution
```bash
cd infra
chmod +x bootstrap.sh
./bootstrap.sh
```

### 2. Remote Execution
```bash
curl -sSL https://raw.githubusercontent.com/user/repo/main/infra/bootstrap.sh | bash
```

### 3. With Custom Options
```bash
./bootstrap.sh --skip-venv --tmux-prefix C-b
```

## Maintenance

- Regular testing on fresh Ubuntu VMs
- Update package lists as new Ubuntu versions are released
- Monitor for deprecated packages or configuration options
- Version the script for reproducible deployments