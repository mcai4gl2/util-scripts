# Latency System Dump & Diff Utilities

Tools to capture and compare latency-relevant Linux system settings for low-latency C++/HFT environments. Pure Python (stdlib only). No root required; best-effort collection with graceful degradation when tools are missing.

## What It Collects
- Kernel/OS: `uname`, `/etc/os-release`, `/proc/cmdline`, CPU vulnerability mitigations, first 5KB of `/boot/config-$(uname -r)`, dmesg snippets (`tsc|clocksource|timekeeping`).
- CPU/NUMA: `lscpu`, `lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE`, SMT active, per-CPU `scaling_governor`, Intel P-state status, `cpupower frequency-info` (if available), `numactl -H`.
- Affinity/Isolation: current process `Cpus_allowed_list`, kernel params `isolcpus`, `nohz_full`, `rcu_nocbs`.
- Timekeeping: `clocksource` current/available, `timedatectl`, `chronyc sources/tracking` (if available), `/dev/ptp*` listing, dmesg timekeeping snippets.
- Memory: `/proc/meminfo`, THP (enabled/defrag), explicit HugePages (`/proc/sys/vm/nr_hugepages`, size via meminfo), swap (`/proc/swaps`, `swapon --show`), `overcommit_memory`, `swappiness`, KSM knobs.
- Networking: per-interface MAC/MTU/speed/queue dirs; `ethtool -i/-k/-g/-l/-c/-a/-S`; routing tables (`ip route show`, `ip -6 route show`); `lspci -nn`.
- IRQs: `/proc/interrupts` parsed, per-IRQ `smp_affinity_list`.
- Toolchain: `ldd --version`, libstdc++ max `GLIBCXX_*` (extracted directly from library file), `gcc/g++/clang/ld/cmake/ninja/bazel` versions.
- Services/Sysctls: `irqbalance` state, `tuned-adm active`, selected sysctls (`kernel.sched_*`, `kernel.timer_migration`, `kernel.numa_balancing`, `net.core.*`, `net.ipv4.tcp_*`), ASLR, SELinux/AppArmor.
- Containers: `docker info`/`podman info` if present, `systemctl is-active docker`, cgroup v1/v2 hints, WSL hint.

## Usage
Run a system dump:

```
python3 latency_sysdump.py
python3 latency_sysdump.py --out /tmp/sysdump
```

The tool creates `latency_sysdump_<timestamp>/` containing:
- `report.md`: human-readable summary.
- `dump.json`: full structured dump for machine processing.
- `raw/*.txt`: selected raw command outputs for offline inspection.

Compare two dumps for drift:

```
python3 latency_sysdiff.py /path/to/old/dump.json /path/to/new/dump.json \
  --only-changed --md diff.md --json diff.json --exit-on-critical
```

Console output shows items like:
```
[CRITICAL] kernel.cmdline: isolcpus=1-3 -> (absent)
[CRITICAL] timekeeping.clocksource_current: tsc -> hpet
[CRITICAL] network.eth0.features.tcp-segmentation-offload: true -> false
[WARNING ] memory.transparent_hugepage.enabled: [always] -> [madvise]
[INFO    ] toolchain.gcc_version: gcc (Debian 13.2) -> gcc (Debian 13.3)
```

## Dev Container
A reproducible environment is provided under `.devcontainer/`:
- `Dockerfile`: Debian 12 with GCC/Clang, perf, ethtool, iproute2, numactl, pciutils, hwloc.
- `devcontainer.json`: suitable defaults; set `--cpuset-cpus`, caps, and devices as needed to mirror production.

### Knobs to Mirror Production
- CPU governors: target `performance`; disable scaling.
- THP vs HugePages: prefer THP=never or explicit HugePages for determinism; ensure `nr_hugepages`/`Hugepagesize` set appropriately.
- Kernel isolation: `isolcpus`, `nohz_full`, `rcu_nocbs` tuned for isolated latency cores.
- IRQ pinning: bind device IRQs to isolated cores; avoid `irqbalance` if pinning is used.
- Clocksource: prefer `tsc` when stable on platform; verify `clocksource_current`.
- NUMA locality: bind processes and memory to target NUMA node; check `numactl -H`.
- NIC settings: offloads (GRO/LRO/TSO/CSUM) and coalescing tuned; ring/channels sized for workload; MTU consistent.

## Notes
- The dump tool is best-effort: missing commands or permissions degrade gracefully.
- The diff tool classifies changes by severity using simple, conservative heuristics.

## License
CC0-1.0 / Public Domain. Do as you wish.

