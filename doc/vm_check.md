# VM Check - Hardware & Performance Benchmarking Tool

A comprehensive Python script for checking cloud VM hardware specifications and running performance benchmarks. No external dependencies required (except for optional GPU benchmarks).

## Features

- **Hardware Detection**: CPU, memory, disks, network, and GPU information
- **CPU Benchmarks**: SHA-256 hash operations to test computational performance
- **Memory Benchmarks**: Random access operations and sequential copy bandwidth
- **Disk Benchmarks**: Random 4KiB read/write IOPS testing
- **GPU Benchmarks**: Matrix multiplication tests using PyTorch or CuPy (if available)
- **Multiple Output Formats**: Console output, JSON, and CSV exports

## Usage

```bash
cd infra
python3 vm_check.py [options]
```

### Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--server-name` | hostname | Logical name for this server |
| `--duration` | 5 | Seconds per benchmark section |
| `--threads` | min(4, cpu_count) | Workers for CPU/memory benchmarks |
| `--disk-path` | system temp | Directory for disk test file |
| `--disk-size-mb` | 1024 | Disk test file size in MB |
| `--mem-size-mb` | 256 | Memory test working set in MB |
| `--skip-gpu` | false | Skip GPU benchmark |
| `--json` | false | Print JSON to stdout |
| `--out-json` | none | Save full report to JSON file |
| `--out-csv` | none | Save flattened report to CSV file |

### Examples

Basic hardware check and benchmark:
```bash
python3 vm_check.py
```

Extended benchmark with custom parameters:
```bash
python3 vm_check.py --duration 10 --threads 8 --mem-size-mb 512 --disk-size-mb 2048
```

Save results to files:
```bash
python3 vm_check.py --out-json results.json --out-csv results.csv
```

## Output Information

### Hardware Detection
- **CPU**: Model, core count (logical/physical), frequency, instruction flags
- **Memory**: Total RAM, swap space, detailed memory information
- **Storage**: Block devices with sizes, types, and mount points
- **Network**: Hostname and IP addresses
- **GPU**: NVIDIA GPU details via nvidia-smi (if available)

### Benchmark Results
- **CPU Performance**: Hash operations per second using SHA-256
- **Memory Performance**: Random access operations and sequential copy bandwidth
- **Disk Performance**: Random 4KiB read/write IOPS and throughput
- **GPU Performance**: Matrix multiplication TFLOPS (requires PyTorch or CuPy)

## Requirements

- Python 3.6+
- Standard library only (no pip dependencies)
- Optional: PyTorch or CuPy for GPU benchmarks
- Optional: nvidia-smi for GPU information

## Output Formats

### Console Output
Human-readable summary with key metrics and performance results.

### JSON Export
Complete structured data including all hardware details and benchmark results.

### CSV Export
Single-row flattened format suitable for dashboards and spreadsheet analysis.