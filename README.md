# Utility Scripts

A collection of utility scripts for system administration and infrastructure management.

## Scripts

### Infrastructure Tools
- **[vm_check.py](infra/vm_check.py)** - Hardware & performance benchmarking tool for cloud VMs
  - [Documentation](doc/vm_check.md)
- **[bootstrap.sh](infra/bootstrap.sh)** - One-click Ubuntu VM setup script with development tools
  - [Documentation](doc/bootstrap.md)

### Low-Latency Diagnostics
- **Latency System Dump & Diff** (`latency_sysdump/`)
  - `latency_sysdump.py`: Collects latency-relevant Linux system data (no root required).
  - `latency_sysdiff.py`: Compares two dumps and highlights drift (critical/warning/info).
  - [Details & Usage](latency_sysdump/README.md)

## Documentation

All detailed documentation is located in the [`doc/`](doc/) folder and subprojects:

- [VM Check Documentation](doc/vm_check.md)
- [Bootstrap Documentation](doc/bootstrap.md)
- [Latency Dump & Diff](latency_sysdump/README.md)

## Usage

Navigate to the appropriate directory and run the scripts directly:

```bash
# Example: Run VM check
cd infra
python3 vm_check.py --help

# Example: Bootstrap Ubuntu VM
cd infra
./bootstrap.sh

# Example: Latency system dump
cd latency_sysdump
python3 latency_sysdump.py --out /tmp/sysdump

# Example: Diff two dumps
python3 latency_sysdiff.py /path/old/dump.json /path/new/dump.json --only-changed --exit-on-critical

# Run tests for latency dump & diff
python3 -m unittest discover -s latency_sysdump -p "test_*.py"
```
