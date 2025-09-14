# Utility Scripts

A collection of utility scripts for system administration and infrastructure management.

## Scripts

### Infrastructure Tools
- **[vm_check.py](infra/vm_check.py)** - Hardware & performance benchmarking tool for cloud VMs
  - [Documentation](doc/vm_check.md)
- **[bootstrap.sh](infra/bootstrap.sh)** - One-click Ubuntu VM setup script with development tools
  - [Documentation](doc/bootstrap.md)

## Documentation

All detailed documentation is located in the [`doc/`](doc/) folder:

- [VM Check Documentation](doc/vm_check.md)
- [Bootstrap Documentation](doc/bootstrap.md)

## Usage

Navigate to the appropriate directory and run the scripts directly:

```bash
# Example: Run VM check
cd infra
python3 vm_check.py --help

# Example: Bootstrap Ubuntu VM
cd infra
./bootstrap.sh
```