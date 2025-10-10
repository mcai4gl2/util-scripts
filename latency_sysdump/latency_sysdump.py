#!/usr/bin/env python3
"""
latency_sysdump.py

Best-effort Linux system diagnostics focused on low-latency C++ environments.

Features:
- Collects latency-relevant system information without requiring root (graceful fallback).
- Uses only Python standard library and external commands if available.
- Saves:
  - dump.json: structured machine-readable data
  - report.md: human-readable summary
  - raw/*.txt: selected raw command outputs

Usage:
  python3 latency_sysdump.py
  python3 latency_sysdump.py --out /tmp/sysdump

Outputs to a directory named latency_sysdump_<timestamp>/ inside the given --out
directory (or current working directory by default) and prints its path.

Python 3.8+ only, no external dependencies.
"""

import argparse
import datetime as _dt
import glob
import gzip
import hashlib
import json
import os
import platform
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


SCRIPT_VERSION = "1.0.0"


def sh(cmd: List[str], timeout: int = 5, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run a shell command with timeout; return dict with stdout/stderr/rc/ok/duration.

    The function is robust: missing executables or permission errors are handled gracefully.
    """
    ts0 = time.time()
    try:
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env, text=True, check=False
        )
        out = p.stdout or ""
        err = p.stderr or ""
        rc = p.returncode
        ok = (rc == 0)
    except FileNotFoundError as e:
        out = ""
        err = f"executable not found: {cmd[0]}"
        rc = 127
        ok = False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout.decode() if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or ""))
        err = (e.stderr.decode() if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or ""))
        rc = 124
        ok = False
    except Exception as e:
        out = ""
        err = f"error: {type(e).__name__}: {e}"
        rc = 1
        ok = False
    dur = time.time() - ts0
    return {
        "cmd": cmd,
        "returncode": rc,
        "stdout": out,
        "stderr": err,
        "ok": ok,
        "duration": dur,
    }


def read_text(path: Path, max_bytes: Optional[int] = None) -> Optional[str]:
    try:
        if max_bytes is None:
            return path.read_text(errors="replace")
        else:
            with path.open("rb") as f:
                data = f.read(max_bytes)
            return data.decode(errors="replace")
    except Exception:
        return None


def read_first_line(path: Path) -> Optional[str]:
    try:
        with path.open("r", errors="replace") as f:
            return f.readline().strip()
    except Exception:
        return None


def listdir(path: Path) -> List[str]:
    try:
        return sorted(os.listdir(str(path)))
    except Exception:
        return []


def parse_key_values(text: str) -> Dict[str, str]:
    """Parse simple 'key: value' lines into a dict."""
    res: Dict[str, str] = {}
    for line in (text or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            res[k.strip()] = v.strip()
    return res


def parse_cmdline(cmdline: str) -> Dict[str, str]:
    res: Dict[str, str] = {}
    for token in shlex.split(cmdline.strip()):
        if "=" in token:
            k, v = token.split("=", 1)
        else:
            k, v = token, ""
        res[k] = v
    return res


def thp_mode(text: Optional[str]) -> Optional[str]:
    # THP files show: always madvise [never], where [] marks current.
    if not text:
        return None
    # extract [value]
    m = re.search(r"\[(\w+)\]", text)
    if m:
        return m.group(1)
    return text.strip()


def detect_cgroup_mode() -> Dict[str, Any]:
    mode = "unknown"
    unified_path = Path("/sys/fs/cgroup/cgroup.controllers")
    if unified_path.exists():
        mode = "v2"
    else:
        if Path("/sys/fs/cgroup").exists():
            mode = "v1"
    return {
        "mode": mode,
        "self_cgroup": read_text(Path("/proc/self/cgroup")),
    }


def find_libstdcxx_versions() -> Dict[str, Any]:
    """Scan common libstdc++ locations and extract GLIBCXX_* versions (no external tools)."""
    candidates: List[Path] = []
    for pat in ["/usr/lib*/**/libstdc++.so.6*", 
                "/lib*/**/libstdc++.so.6*"]:
        for p in glob.glob(pat, recursive=True):
            try:
                pp = Path(p)
                if pp.is_file() and pp.stat().st_size > 0:
                    candidates.append(pp)
            except Exception:
                continue
    seen = set()
    versions: List[str] = []
    for path in candidates[:10]:  # cap effort
        try:
            data = path.read_bytes()
        except Exception:
            continue
        for m in re.finditer(br"GLIBCXX_([0-9]+\.[0-9]+(?:\.[0-9]+)?)", data):
            ver = m.group(0).decode(errors="ignore")
            if ver not in seen:
                seen.add(ver)
                versions.append(ver)
    def ver_key(s: str) -> Tuple[int, ...]:
        nums = s.split("_")[1].split(".")
        return tuple(int(x) for x in nums)
    versions.sort(key=ver_key)
    max_ver = versions[-1] if versions else None
    return {"versions": versions, "max": max_ver}


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode(errors="replace")).hexdigest()


def parse_cpufreq_default_from_config_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse kernel config text to detect default CPUFREQ governor.

    Returns (governor_name_lower, symbol) if found, else (None, None).
    Matches lines like: CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE=y
    """
    if not text:
        return None, None
    # Generic regex to capture any DEFAULT_GOV_XXX set to y
    for line in text.splitlines():
        m = re.match(r"^CONFIG_CPU_FREQ_DEFAULT_GOV_([A-Z0-9_]+)=y\s*$", line)
        if m:
            tag = m.group(1)
            sym = f"CONFIG_CPU_FREQ_DEFAULT_GOV_{tag}"
            gov_map = {
                "PERFORMANCE": "performance",
                "POWERSAVE": "powersave",
                "USERSPACE": "userspace",
                "ONDEMAND": "ondemand",
                "CONSERVATIVE": "conservative",
                "SCHEDUTIL": "schedutil",
            }
            name = gov_map.get(tag, tag.lower())
            return name, sym
    return None, None


def collect_kernel(raw: Dict[str, str]) -> Dict[str, Any]:
    uname = platform.uname()
    os_release: Dict[str, str] = {}
    osr = read_text(Path("/etc/os-release"))
    if osr:
        for line in osr.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os_release[k.strip()] = v.strip().strip('"')
        raw["os-release.txt"] = osr
    cmdline = read_text(Path("/proc/cmdline")) or ""
    raw["proc-cmdline.txt"] = cmdline
    vulns: Dict[str, str] = {}
    vdir = Path("/sys/devices/system/cpu/vulnerabilities")
    if vdir.exists():
        for name in listdir(vdir):
            vulns[name] = (read_text(vdir / name) or "").strip()
    boot_cfg_head = None
    try:
        krel = uname.release
        boot_cfg_path = Path(f"/boot/config-{krel}")
        if boot_cfg_path.exists():
            boot_cfg_head = read_text(boot_cfg_path, max_bytes=5 * 1024)
            if boot_cfg_head is not None:
                raw["boot-config-head.txt"] = boot_cfg_head
    except Exception:
        pass
    # dmesg snippets
    dm = sh(["dmesg", "--color=never"]) if shutil_which("dmesg") else {"stdout": "", "ok": False}
    dmesg_txt = dm.get("stdout", "") if dm else ""
    if not dmesg_txt:
        dm = sh(["dmesg"]) if shutil_which("dmesg") else {"stdout": "", "ok": False}
        dmesg_txt = dm.get("stdout", "") if dm else ""
    dmesg_lines = []
    for line in dmesg_txt.splitlines():
        if re.search(r"\b(tsc|clocksource|timekeeping)\b", line, re.IGNORECASE):
            dmesg_lines.append(line)
    raw["dmesg.txt"] = dmesg_txt
    return {
        "uname": {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor,
        },
        "os_release": os_release,
        "cmdline": cmdline.strip(),
        "cmdline_params": parse_cmdline(cmdline),
        "vulnerabilities": vulns,
        "boot_config_head": boot_cfg_head,
        "dmesg_snippets": dmesg_lines[:500],
    }


def shutil_which(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def collect_cpu_numa(raw: Dict[str, str]) -> Dict[str, Any]:
    lscpu_full = sh(["lscpu", "-J"]) if shutil_which("lscpu") else {"ok": False, "stdout": ""}
    if not lscpu_full.get("ok"):
        lscpu_full = sh(["lscpu"]) if shutil_which("lscpu") else {"ok": False, "stdout": ""}
    lscpu_e = sh(["lscpu", "-e=CPU,CORE,SOCKET,NODE,ONLINE"]) if shutil_which("lscpu") else {"ok": False, "stdout": ""}
    raw["lscpu.txt"] = lscpu_full.get("stdout", "")
    raw["lscpu-e.txt"] = lscpu_e.get("stdout", "")
    # SMT active: derive from lscpu text
    smt_active: Optional[bool] = None
    for line in lscpu_full.get("stdout", "").splitlines():
        if "Thread(s) per core:" in line:
            try:
                n = int(line.split(":", 1)[1].strip())
                smt_active = n > 1
            except Exception:
                pass
    # governors
    govs: Dict[str, Optional[str]] = {}
    for cpu_dir in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*")):
        gpath = Path(cpu_dir) / "cpufreq" / "scaling_governor"
        govs[Path(cpu_dir).name] = read_first_line(gpath)
    intel_pstate_status = read_first_line(Path("/sys/devices/system/cpu/intel_pstate/status"))
    cpupower_info = sh(["cpupower", "frequency-info"]) if shutil_which("cpupower") else {"ok": False, "stdout": ""}
    raw["cpupower-frequency-info.txt"] = cpupower_info.get("stdout", "")
    numactl = sh(["numactl", "-H"]) if shutil_which("numactl") else {"ok": False, "stdout": ""}
    raw["numactl-H.txt"] = numactl.get("stdout", "")
    lscpu_hash = hash_text(lscpu_full.get("stdout", "")) if lscpu_full.get("stdout") else None
    # Kernel default CPUFREQ governor (from /boot/config-<release>)
    kernel_default_governor = None
    kernel_default_symbol = None
    kernel_default_source = None
    try:
        krel = platform.uname().release
        cfgp = Path(f"/boot/config-{krel}")
        if cfgp.exists():
            cfg_text = read_text(cfgp)
            if cfg_text:
                gov, sym = parse_cpufreq_default_from_config_text(cfg_text)
                kernel_default_governor = gov
                kernel_default_symbol = sym
                kernel_default_source = str(cfgp)
        # Fallback: /proc/config.gz
        if kernel_default_governor is None and Path("/proc/config.gz").exists():
            try:
                with gzip.open("/proc/config.gz", "rt", errors="replace") as f:
                    cfg_text = f.read()
                gov, sym = parse_cpufreq_default_from_config_text(cfg_text)
                kernel_default_governor = gov
                kernel_default_symbol = sym
                kernel_default_source = "/proc/config.gz"
            except Exception:
                pass
    except Exception:
        pass
    return {
        "lscpu_raw": lscpu_full.get("stdout"),
        "lscpu_e": lscpu_e.get("stdout"),
        "lscpu_hash": lscpu_hash,
        "smt_active": smt_active,
        "per_cpu_governors": govs,
        "intel_pstate_status": intel_pstate_status,
        "cpupower_frequency_info": cpupower_info.get("stdout"),
        "numactl_H": numactl.get("stdout"),
        "kernel_cpufreq_default_governor": kernel_default_governor,
        "kernel_cpufreq_default_symbol": kernel_default_symbol,
        "kernel_cpufreq_default_source": kernel_default_source,
    }


def collect_affinity_isolation(kernel: Dict[str, Any]) -> Dict[str, Any]:
    # Current process allowed cpus
    cpus_allowed_list = None
    try:
        with open("/proc/self/status", "r", errors="replace") as f:
            for line in f:
                if line.startswith("Cpus_allowed_list:"):
                    cpus_allowed_list = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    params = kernel.get("cmdline_params", {})
    return {
        "process_cpus_allowed_list": cpus_allowed_list,
        "isolcpus": params.get("isolcpus"),
        "nohz_full": params.get("nohz_full"),
        "rcu_nocbs": params.get("rcu_nocbs"),
    }


def collect_timekeeping(raw: Dict[str, str]) -> Dict[str, Any]:
    clk_cur = read_first_line(Path("/sys/devices/system/clocksource/clocksource0/current_clocksource"))
    clk_avail = read_first_line(Path("/sys/devices/system/clocksource/clocksource0/available_clocksource"))
    timedate = sh(["timedatectl"]) if shutil_which("timedatectl") else {"ok": False, "stdout": ""}
    raw["timedatectl.txt"] = timedate.get("stdout", "")
    chronyc_sources = sh(["chronyc", "sources"]) if shutil_which("chronyc") else {"ok": False, "stdout": ""}
    chronyc_tracking = sh(["chronyc", "tracking"]) if shutil_which("chronyc") else {"ok": False, "stdout": ""}
    raw["chronyc-sources.txt"] = chronyc_sources.get("stdout", "")
    raw["chronyc-tracking.txt"] = chronyc_tracking.get("stdout", "")
    ptp_devs = sorted([p for p in glob.glob("/dev/ptp*") if os.path.exists(p)])
    # dmesg snippets handled in kernel section; also present here as reference
    return {
        "clocksource_current": clk_cur,
        "clocksource_available": clk_avail,
        "timedatectl": timedate.get("stdout"),
        "chronyc_sources": chronyc_sources.get("stdout"),
        "chronyc_tracking": chronyc_tracking.get("stdout"),
        "ptp_devices": ptp_devs,
    }


def collect_memory(raw: Dict[str, str]) -> Dict[str, Any]:
    meminfo_txt = read_text(Path("/proc/meminfo")) or ""
    raw["proc-meminfo.txt"] = meminfo_txt
    meminfo: Dict[str, Any] = {}
    for line in meminfo_txt.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meminfo[k.strip()] = v.strip()
    thp_enabled = read_text(Path("/sys/kernel/mm/transparent_hugepage/enabled"))
    thp_defrag = read_text(Path("/sys/kernel/mm/transparent_hugepage/defrag"))
    nr_hugepages = read_first_line(Path("/proc/sys/vm/nr_hugepages"))
    overcommit_memory = read_first_line(Path("/proc/sys/vm/overcommit_memory"))
    swappiness = read_first_line(Path("/proc/sys/vm/swappiness"))
    # KSM
    ksm_dir = Path("/sys/kernel/mm/ksm")
    ksm = {}
    if ksm_dir.exists():
        for name in ["run", "pages_to_scan", "sleep_millisecs"]:
            ksm[name] = read_first_line(ksm_dir / name)
    swaps_txt = read_text(Path("/proc/swaps")) or ""
    raw["proc-swaps.txt"] = swaps_txt
    swapon_show = sh(["swapon", "--show"]) if shutil_which("swapon") else {"ok": False, "stdout": ""}
    raw["swapon-show.txt"] = swapon_show.get("stdout", "")
    return {
        "meminfo": meminfo,
        "transparent_hugepage": {
            "enabled": thp_mode(thp_enabled),
            "enabled_raw": thp_enabled,
            "defrag": thp_mode(thp_defrag),
            "defrag_raw": thp_defrag,
        },
        "nr_hugepages": nr_hugepages,
        "hugepagesize": meminfo.get("Hugepagesize"),
        "swap": {
            "proc_swaps": swaps_txt,
            "swapon_show": swapon_show.get("stdout"),
        },
        "overcommit_memory": overcommit_memory,
        "swappiness": swappiness,
        "ksm": ksm,
    }


def parse_ethtool_features(text: str) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().replace(" ", "_")
            v = v.strip()
            val = None
            if v.startswith("on"):
                val = True
            elif v.startswith("off"):
                val = False
            res[k] = val if val is not None else v
    return res


def parse_numeric_map(text: str) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().replace(" ", "_")
            v = v.strip()
            try:
                if v.lower().startswith("0x"):
                    res[k] = int(v, 16)
                else:
                    res[k] = int(v)
            except Exception:
                res[k] = v
    return res


def collect_network(raw: Dict[str, str]) -> Dict[str, Any]:
    interfaces: Dict[str, Any] = {}
    for iface in sorted(listdir(Path("/sys/class/net"))):
        ipath = Path("/sys/class/net") / iface
        mac = read_first_line(ipath / "address")
        mtu = read_first_line(ipath / "mtu")
        speed = read_first_line(ipath / "speed")
        queues = listdir(ipath / "queues")
        et: Dict[str, Any] = {}
        if shutil_which("ethtool"):
            # driver info
            di = sh(["ethtool", "-i", iface])
            et["driver"] = parse_key_values(di.get("stdout", ""))
            # features
            fk = sh(["ethtool", "-k", iface])
            et["features"] = parse_ethtool_features(fk.get("stdout", ""))
            # ring sizes
            rg = sh(["ethtool", "-g", iface])
            et["rings"] = parse_numeric_map(rg.get("stdout", ""))
            # channels
            ch = sh(["ethtool", "-l", iface])
            et["channels"] = parse_numeric_map(ch.get("stdout", ""))
            # coalesce
            co = sh(["ethtool", "-c", iface])
            et["coalesce"] = parse_numeric_map(co.get("stdout", ""))
            # pause
            pa = sh(["ethtool", "-a", iface])
            et["pause"] = parse_ethtool_features(pa.get("stdout", ""))
            # stats (raw, large)
            st = sh(["ethtool", "-S", iface])
            et["stats_raw"] = st.get("stdout", "")
            # raw save
            raw[f"ethtool-i-{iface}.txt"] = di.get("stdout", "")
            raw[f"ethtool-k-{iface}.txt"] = fk.get("stdout", "")
            raw[f"ethtool-g-{iface}.txt"] = rg.get("stdout", "")
            raw[f"ethtool-l-{iface}.txt"] = ch.get("stdout", "")
            raw[f"ethtool-c-{iface}.txt"] = co.get("stdout", "")
            raw[f"ethtool-a-{iface}.txt"] = pa.get("stdout", "")
            raw[f"ethtool-S-{iface}.txt"] = st.get("stdout", "")
        interfaces[iface] = {
            "mac": mac,
            "mtu": mtu,
            "speed": speed,
            "sys_queues": queues,
            "ethtool": et,
        }
    ip_route = sh(["ip", "route", "show"]) if shutil_which("ip") else {"ok": False, "stdout": ""}
    ip_route6 = sh(["ip", "-6", "route", "show"]) if shutil_which("ip") else {"ok": False, "stdout": ""}
    raw["ip-route-show.txt"] = ip_route.get("stdout", "")
    raw["ip6-route-show.txt"] = ip_route6.get("stdout", "")
    lspci = sh(["lspci", "-nn"]) if shutil_which("lspci") else {"ok": False, "stdout": ""}
    raw["lspci-nn.txt"] = lspci.get("stdout", "")
    return {
        "interfaces": interfaces,
        "routes": {
            "v4": ip_route.get("stdout"),
            "v6": ip_route6.get("stdout"),
        },
        "lspci_nn": lspci.get("stdout"),
    }


def parse_interrupts(text: str) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    lines = (text or "").splitlines()
    cpus: List[str] = []
    for i, line in enumerate(lines):
        if line.startswith(" ") and line.strip().startswith("CPU0"):
            cpus = line.split()
            continue
        if re.match(r"^\s*\d+:", line):
            parts = line.split()
            irq = parts[0].rstrip(":")
            # counts distributed across CPUs; sum
            counts = []
            for p in parts[1:1+len(cpus)]:
                try:
                    counts.append(int(p))
                except Exception:
                    break
            desc = " ".join(parts[1+len(cpus):])
            res[irq] = {
                "total": sum(counts) if counts else None,
                "desc": desc,
            }
    return res


def collect_irqs(raw: Dict[str, str]) -> Dict[str, Any]:
    proc_interrupts = read_text(Path("/proc/interrupts")) or ""
    raw["proc-interrupts.txt"] = proc_interrupts
    parsed = parse_interrupts(proc_interrupts)
    affinity: Dict[str, Optional[str]] = {}
    for irq in parsed.keys():
        path = Path("/proc/irq") / irq / "smp_affinity_list"
        if path.exists():
            affinity[irq] = read_first_line(path)
    return {
        "interrupts": parsed,
        "smp_affinity_list": affinity,
    }


def collect_toolchain(raw: Dict[str, str]) -> Dict[str, Any]:
    ldd_v = sh(["ldd", "--version"]) if shutil_which("ldd") else {"ok": False, "stdout": ""}
    gcc_v = sh(["gcc", "--version"]) if shutil_which("gcc") else {"ok": False, "stdout": ""}
    gxx_v = sh(["g++", "--version"]) if shutil_which("g++") else {"ok": False, "stdout": ""}
    clang_v = sh(["clang", "--version"]) if shutil_which("clang") else {"ok": False, "stdout": ""}
    ld_v = sh(["ld", "--version"]) if shutil_which("ld") else {"ok": False, "stdout": ""}
    cmake_v = sh(["cmake", "--version"]) if shutil_which("cmake") else {"ok": False, "stdout": ""}
    ninja_v = sh(["ninja", "--version"]) if shutil_which("ninja") else {"ok": False, "stdout": ""}
    bazel_v = sh(["bazel", "--version"]) if shutil_which("bazel") else {"ok": False, "stdout": ""}
    raw["ldd-version.txt"] = ldd_v.get("stdout", "")
    raw["gcc-version.txt"] = gcc_v.get("stdout", "")
    raw["gxx-version.txt"] = gxx_v.get("stdout", "")
    raw["clang-version.txt"] = clang_v.get("stdout", "")
    raw["ld-version.txt"] = ld_v.get("stdout", "")
    raw["cmake-version.txt"] = cmake_v.get("stdout", "")
    raw["ninja-version.txt"] = ninja_v.get("stdout", "")
    raw["bazel-version.txt"] = bazel_v.get("stdout", "")
    libstdcxx = find_libstdcxx_versions()
    return {
        "ldd_version": ldd_v.get("stdout"),
        "gcc_version": gcc_v.get("stdout"),
        "gxx_version": gxx_v.get("stdout"),
        "clang_version": clang_v.get("stdout"),
        "ld_version": ld_v.get("stdout"),
        "cmake_version": cmake_v.get("stdout"),
        "ninja_version": ninja_v.get("stdout"),
        "bazel_version": bazel_v.get("stdout"),
        "libstdcxx_max_glibcxx": libstdcxx.get("max"),
        "libstdcxx_glibcxx_versions": libstdcxx.get("versions"),
    }


def read_sysctl_path(path: Path) -> Optional[str]:
    try:
        if path.is_file():
            return path.read_text(errors="replace").strip()
    except Exception:
        return None
    return None


def collect_services_sysctls(raw: Dict[str, str]) -> Dict[str, Any]:
    # irqbalance state
    irqbalance_state = None
    if shutil_which("systemctl"):
        s = sh(["systemctl", "is-active", "irqbalance"], timeout=5)
        if s.get("ok"):
            irqbalance_state = s.get("stdout", "").strip()
    tuned_active = None
    if shutil_which("tuned-adm"):
        t = sh(["tuned-adm", "active"])  # outputs current profile
        tuned_active = t.get("stdout", "").strip()
    # Sysctls: read select keys from /proc/sys
    def read_glob(pat: str) -> Dict[str, str]:
        found: Dict[str, str] = {}
        for p in glob.glob(pat):
            val = read_sysctl_path(Path(p))
            if val is not None:
                found[p] = val
        return found
    sysctls: Dict[str, Any] = {}
    # kernel.sched_*
    for p, v in read_glob("/proc/sys/kernel/sched_*").items():
        sysctls[p.replace("/proc/sys/", "").replace("/", ".")] = v
    # specific kernel.*
    for key in ["kernel/timer_migration", "kernel/numa_balancing", "kernel/randomize_va_space"]:
        p = Path("/proc/sys") / key
        val = read_sysctl_path(p)
        if val is not None:
            sysctls[str(key).replace("/", ".")] = val
    # net.core.*
    for p, v in read_glob("/proc/sys/net/core/*").items():
        sysctls[p.replace("/proc/sys/", "").replace("/", ".")] = v
    # net.ipv4.tcp_*
    for p, v in read_glob("/proc/sys/net/ipv4/tcp_*").items():
        sysctls[p.replace("/proc/sys/", "").replace("/", ".")] = v
    aslr = sysctls.get("kernel.randomize_va_space")
    # SELinux / AppArmor
    selinux = None
    if Path("/sys/fs/selinux/enforce").exists():
        selinux = read_first_line(Path("/sys/fs/selinux/enforce"))
    apparmor = None
    if Path("/sys/module/apparmor/parameters/enabled").exists():
        apparmor = read_first_line(Path("/sys/module/apparmor/parameters/enabled"))
    return {
        "irqbalance": {"state": irqbalance_state},
        "tuned_adm": tuned_active,
        "sysctl": sysctls,
        "aslr": aslr,
        "selinux": selinux,
        "apparmor": apparmor,
    }


def collect_containers(raw: Dict[str, str]) -> Dict[str, Any]:
    docker_info = sh(["docker", "info"]) if shutil_which("docker") else {"ok": False, "stdout": ""}
    podman_info = sh(["podman", "info"]) if shutil_which("podman") else {"ok": False, "stdout": ""}
    docker_active = None
    if shutil_which("systemctl"):
        st = sh(["systemctl", "is-active", "docker"])  # noqa: S603
        if st.get("ok"):
            docker_active = st.get("stdout", "").strip()
    raw["docker-info.txt"] = docker_info.get("stdout", "")
    raw["podman-info.txt"] = podman_info.get("stdout", "")
    # cgroup hints
    cgroup = detect_cgroup_mode()
    # WSL hint
    wsl = False
    osrel = read_text(Path("/proc/sys/kernel/osrelease")) or ""
    if "microsoft" in osrel.lower() or "wsl" in osrel.lower():
        wsl = True
    return {
        "docker_info": docker_info.get("stdout"),
        "podman_info": podman_info.get("stdout"),
        "docker_systemd_state": docker_active,
        "cgroup": cgroup,
        "wsl": wsl,
    }


def generate_report(d: Dict[str, Any]) -> str:
    # Compact human-readable summary
    k = d.get("kernel", {})
    c = d.get("cpu_topology", {})
    t = d.get("timekeeping", {})
    m = d.get("memory", {})
    n = d.get("network", {})
    s = d.get("services_sysctl", {})
    i = d.get("irq", {})
    lines: List[str] = []
    lines.append(f"# Latency System Dump — {d['meta']['timestamp']}")
    lines.append("")
    lines.append("## Kernel")
    lines.append(f"- Release: {k.get('uname', {}).get('release')}")
    lines.append(f"- Cmdline: {k.get('cmdline')}")
    lines.append(f"- Mitigations: {', '.join([f'{kk}={vv}' for kk, vv in (k.get('vulnerabilities') or {}).items()])}")
    lines.append("")
    lines.append("## CPU/NUMA")
    lines.append(f"- SMT active: {c.get('smt_active')}")
    # governor summary
    govs = c.get("per_cpu_governors") or {}
    bad_govs = sorted([cpu for cpu, g in govs.items() if g and g.lower() != 'performance'])
    if govs:
        lines.append(f"- Governors: performance={len(govs)-len(bad_govs)} non-performance={len(bad_govs)}")
        if bad_govs:
            lines.append(f"  - Non-performance CPUs: {', '.join(bad_govs[:32])}{'...' if len(bad_govs)>32 else ''}")
    intel_p = c.get("intel_pstate_status")
    if intel_p is not None:
        lines.append(f"- Intel P-state: {intel_p}")
    # Always show kernel default governor line for visibility
    kdef = c.get("kernel_cpufreq_default_governor")
    ksym = c.get("kernel_cpufreq_default_symbol")
    ksrc = c.get("kernel_cpufreq_default_source")
    disp = kdef if kdef is not None else "unknown"
    extra = []
    if ksym:
        extra.append(ksym)
    if ksrc:
        extra.append(f"src={ksrc}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    lines.append(f"- Kernel cpufreq default governor: {disp}{suffix}")
    lines.append("")
    lines.append("## Timekeeping")
    lines.append(f"- Clocksource: {t.get('clocksource_current')} (avail: {t.get('clocksource_available')})")
    lines.append(f"- PTP devices: {', '.join(t.get('ptp_devices') or [])}")
    lines.append("")
    lines.append("## Memory")
    thp = (m.get('transparent_hugepage') or {})
    lines.append(f"- THP enabled: {thp.get('enabled')} defrag: {thp.get('defrag')}")
    lines.append(f"- Hugepages: nr={m.get('nr_hugepages')} size={m.get('hugepagesize')}")
    lines.append(f"- Overcommit: {m.get('overcommit_memory')} swappiness: {m.get('swappiness')}")
    ksm = m.get('ksm') or {}
    if ksm:
        lines.append(f"- KSM run={ksm.get('run')} pages_to_scan={ksm.get('pages_to_scan')} sleep_millisecs={ksm.get('sleep_millisecs')}")
    lines.append("")
    lines.append("## Networking")
    ifaces = (n.get('interfaces') or {})
    lines.append(f"- Interfaces: {', '.join(sorted(ifaces.keys()))}")
    for name, info in sorted(ifaces.items()):
        lines.append(f"  - {name}: MAC={info.get('mac')} MTU={info.get('mtu')} speed={info.get('speed')}")
        et = info.get('ethtool') or {}
        drv = (et.get('driver') or {}).get('driver')
        fw = (et.get('driver') or {}).get('firmware-version')
        if drv or fw:
            lines.append(f"    driver={drv} fw={fw}")
        feats = et.get('features') or {}
        # Highlight some important offloads
        for key in ["generic-receive-offload", "large-receive-offload", "tcp-segmentation-offload", "tx-checksumming", "rx-checksumming"]:
            if key in feats:
                lines.append(f"    {key}={feats.get(key)}")
    lines.append("")
    lines.append("## IRQs")
    aff = i.get('smp_affinity_list') or {}
    lines.append(f"- IRQs with affinity entries: {len(aff)}")
    lines.append("")
    lines.append("## Toolchain")
    tc = d.get('toolchain', {})
    lines.append(f"- gcc: {first_line(tc.get('gcc_version'))}")
    lines.append(f"- clang: {first_line(tc.get('clang_version'))}")
    lines.append(f"- ldd: {first_line(tc.get('ldd_version'))}")
    lines.append(f"- libstdc++ max GLIBCXX: {tc.get('libstdcxx_max_glibcxx')}")
    lines.append("")
    lines.append("## Services/Sysctls")
    lines.append(f"- irqbalance: {(s.get('irqbalance') or {}).get('state')}")
    lines.append(f"- tuned-adm: {s.get('tuned_adm')}")
    lines.append(f"- ASLR: {s.get('aslr')} SELinux: {s.get('selinux')} AppArmor: {s.get('apparmor')}")
    lines.append("")
    lines.append("## Containers")
    cont = d.get('containers', {})
    lines.append(f"- Docker active: {cont.get('docker_systemd_state')} cgroups: {(cont.get('cgroup') or {}).get('mode')} WSL: {cont.get('wsl')}")
    return "\n".join(lines)


def first_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return text.strip().splitlines()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Latency-focused Linux system dump (no root required)")
    ap.add_argument("--out", default=".", help="Output base directory (default: current directory)")
    args = ap.parse_args()

    ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = Path(args.out).resolve()
    outdir = base / f"latency_sysdump_{ts}"
    rawdir = outdir / "raw"
    outdir.mkdir(parents=True, exist_ok=True)
    rawdir.mkdir(parents=True, exist_ok=True)

    raw_blobs: Dict[str, str] = {}

    data: Dict[str, Any] = {
        "meta": {
            "timestamp": ts,
            "host": socket.gethostname(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME"),
            "python": sys.version.split(" ")[0],
            "script_version": SCRIPT_VERSION,
            "cwd": str(Path.cwd()),
        }
    }

    # Sections
    kernel = collect_kernel(raw_blobs)
    data["kernel"] = kernel
    data["cpu_topology"] = collect_cpu_numa(raw_blobs)
    data["affinity_isolation"] = collect_affinity_isolation(kernel)
    data["timekeeping"] = collect_timekeeping(raw_blobs)
    data["memory"] = collect_memory(raw_blobs)
    data["network"] = collect_network(raw_blobs)
    data["irq"] = collect_irqs(raw_blobs)
    data["toolchain"] = collect_toolchain(raw_blobs)
    data["services_sysctl"] = collect_services_sysctls(raw_blobs)
    data["containers"] = collect_containers(raw_blobs)

    # Save raw blobs
    for name, txt in raw_blobs.items():
        try:
            (rawdir / name).write_text(txt or "", errors="replace")
        except Exception:
            pass

    # Save dump.json
    with (outdir / "dump.json").open("w") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    # Save report.md
    report = generate_report(data)
    (outdir / "report.md").write_text(report)

    print(str(outdir))


if __name__ == "__main__":
    main()
