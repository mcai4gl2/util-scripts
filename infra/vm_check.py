#!/usr/bin/env python3
# vm_check.py
import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ----------------------------
# Helpers
# ----------------------------
def sh(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=10)
        return out.strip()
    except Exception:
        return ""

def which(prog):
    return shutil.which(prog) is not None

def human_bytes(n):
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.1f} {units[i]}"

def read_first(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except:
        return ""

def json_print(obj):
    print(json.dumps(obj, indent=2, sort_keys=False))

def flatten(obj, parent_key="", out=None):
    """
    Flatten nested dict/list into dotted keys suitable for CSV rows.
    Lists are indexed: key.0.foo, key.1.bar
    """
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = f"{parent_key}.{k}" if parent_key else str(k)
            flatten(v, nk, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            nk = f"{parent_key}.{i}" if parent_key else str(i)
            flatten(v, nk, out)
    else:
        out[parent_key] = obj
    return out

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(path)

def write_csv(path, data):
    """
    Writes a single-row CSV from the flattened report (good for dashboards).
    If you prefer multiple CSVs (e.g., per-disk, per-gpu), we can add that too.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flat = flatten(data)
    # Ensure deterministic column order
    cols = sorted(flat.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerow({k: flat.get(k, "") for k in cols})
    return str(path)

# ----------------------------
# System / Hardware info
# ----------------------------
def get_cpu_info():
    info = {
        "model": "",
        "cores_logical": os.cpu_count() or 0,
        "cores_physical": None,
        "mhz": None,
        "flags": None,
    }
    if Path("/proc/cpuinfo").exists():
        txt = read_first("/proc/cpuinfo")
        model = ""
        mhz = None
        flags = None
        phys = set()
        for blk in txt.split("\n\n"):
            lines = dict([tuple(map(str.strip, l.split(":",1))) for l in blk.splitlines() if ":" in l])
            if not model and ("model name" in lines or "Hardware" in lines):
                model = lines.get("model name") or lines.get("Hardware","")
            if "cpu MHz" in lines and mhz is None:
                try: mhz = float(lines["cpu MHz"])
                except: pass
            if "flags" in lines and flags is None:
                flags = lines["flags"].split()
            if "physical id" in lines and "core id" in lines:
                phys.add((lines["physical id"], lines["core id"]))
        info["model"] = model
        info["mhz"] = mhz
        info["flags"] = flags
        info["cores_physical"] = len(phys) if phys else None
    # lscpu for cross-check
    out = sh("LC_ALL=C lscpu")
    if out:
        for line in out.splitlines():
            if line.startswith("Model name:") and not info["model"]:
                info["model"] = line.split(":",1)[1].strip()
            if line.startswith("CPU(s):") and not info["cores_logical"]:
                try: info["cores_logical"] = int(line.split(":",1)[1])
                except: pass
            if line.startswith("Thread(s) per core:") and info["cores_physical"] is None:
                try:
                    tpc = int(line.split(":",1)[1])
                    if info["cores_logical"] and tpc:
                        info["cores_physical"] = info["cores_logical"] // tpc
                except: pass
    return info

def get_mem_info():
    meminfo = {}
    if Path("/proc/meminfo").exists():
        for line in read_first("/proc/meminfo").splitlines():
            if ":" in line:
                k,v = line.split(":",1)
                meminfo[k.strip()] = v.strip()
    total = meminfo.get("MemTotal","").split()
    total_kb = int(total[0]) if total else None
    swap_total = meminfo.get("SwapTotal","").split()
    swap_kb = int(swap_total[0]) if swap_total else None
    return {
        "total": total_kb*1024 if total_kb else None,
        "swap_total": swap_kb*1024 if swap_kb else None,
        "meminfo_raw": meminfo
    }

def get_disk_info():
    disks = []
    lsblk = sh("lsblk -o NAME,SIZE,TYPE,MOUNTPOINT -J")
    try:
        data = json.loads(lsblk)
        for blk in data.get("blockdevices", []):
            disks.append({
                "name": blk.get("name"),
                "size": blk.get("size"),
                "type": blk.get("type"),
                "mountpoint": blk.get("mountpoint")
            })
    except:
        pass
    return disks

def get_net_info():
    host = socket.gethostname()
    try:
        ips = list({ai[4][0] for ai in socket.getaddrinfo(host, None)})
    except:
        ips = []
    return {"hostname": host, "ips": ips}

def get_gpu_info():
    info = {"nvidia_smi": False, "gpus": []}
    if which("nvidia-smi"):
        info["nvidia_smi"] = True
        q = "index,name,uuid,memory.total,memory.free,driver_version,pstate,pcie.link.gen.current,pcie.link.width.current,temperature.gpu,clocks.sm,clocks.mem,utilization.gpu"
        out = sh(f"nvidia-smi --query-gpu={q} --format=csv,noheader,nounits")
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 13:
                info["gpus"].append({
                    "index": parts[0],
                    "name": parts[1],
                    "uuid": parts[2],
                    "mem_total_MB": parts[3],
                    "mem_free_MB": parts[4],
                    "driver": parts[5],
                    "pstate": parts[6],
                    "pcie_gen": parts[7],
                    "pcie_width": parts[8],
                    "temp_C": parts[9],
                    "sm_clock_MHz": parts[10],
                    "mem_clock_MHz": parts[11],
                    "util_percent": parts[12],
                })
    return info

def get_os_python_info():
    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "distro": sh("lsb_release -ds") or read_first('/etc/os-release')
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable
        }
    }

# ----------------------------
# Benchmarks
# ----------------------------
def bench_cpu_hash(duration, threads):
    """
    CPU "IOPS-like": count how many SHA-256 operations we can do.
    Parallelized with processes (if threads>1) for CPU-bound work.
    """
    def worker(stop_at, seed):
        rnd = random.Random(seed)
        ops = 0
        payload = bytearray(1024)  # 1 KiB blocks
        while time.time() < stop_at:
            for i in range(len(payload)):
                payload[i] = rnd.randrange(256)
            hashlib.sha256(payload).digest()
            ops += 1
        return ops

    stop_at = time.time() + duration
    seeds = [random.randrange(1<<30) for _ in range(threads)]
    with cf.ProcessPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(worker, stop_at, s) for s in seeds]
        ops = sum(f.result() for f in futs)
    ops_per_sec = ops / duration
    return {"ops": ops, "ops_per_sec": ops_per_sec, "block_size_bytes": 1024, "duration_s": duration, "workers": threads}

def bench_memory(duration, size_mb, threads):
    """
    Memory random-access ops + copy bandwidth on bytearray(s) without external deps.
    """
    size_bytes = size_mb * 1024 * 1024
    per_worker = max(1, size_bytes // threads)

    def rand_access(stop_at, sz, seed):
        rnd = random.Random(seed)
        buf = bytearray(sz)
        n = len(buf)
        ops = 0
        while time.time() < stop_at:
            for _ in range(64):
                i = rnd.randrange(n)
                buf[i] = (buf[i] + 1) & 0xFF
                ops += 1
        return ops

    def seq_copy_bandwidth(sz):
        a = bytearray(sz)
        b = bytearray(sz)
        start = time.time()
        chunk = 1 << 20  # 1 MiB
        for i in range(0, sz, chunk):
            b[i:i+chunk] = a[i:i+chunk]
        dt = time.time() - start
        return (sz / (1024*1024)) / dt if dt > 0 else float('inf')

    stop_at = time.time() + duration
    seeds = [random.randrange(1<<30) for _ in range(threads)]
    with cf.ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(rand_access, stop_at, per_worker, s) for s in seeds]
        ops = sum(f.result() for f in futs)
    ops_per_sec = ops / duration

    copy_size = min(size_bytes // 2, 512 * 1024 * 1024)
    copy_bw_mibs = seq_copy_bandwidth(copy_size) if copy_size > 0 else None

    return {
        "rand_ops_per_sec": ops_per_sec,
        "rand_total_ops": ops,
        "payload_per_worker_bytes": per_worker,
        "duration_s": duration,
        "workers": threads,
        "seq_copy_bandwidth_MiB_s": copy_bw_mibs
    }

def bench_disk(tmpdir, file_size_mb, duration, rw_ratio=0.5, block_size=4096):
    """
    Simple random 4KiB read/write IOPS benchmark on a temp file.
    Buffered I/O (not O_DIRECT) but indicative.
    """
    file_size = file_size_mb * 1024 * 1024
    test_path = Path(tmpdir) / "disk_bench.dat"

    with open(test_path, "wb") as f:
        f.truncate(file_size)

    blocks = file_size // block_size
    if blocks == 0:
        return {"error": "file too small"}
    rnd = random.Random(1234)
    read_ops = write_ops = 0
    read_bytes = write_bytes = 0
    stop_at = time.time() + duration
    data = os.urandom(block_size)

    with open(test_path, "r+b", buffering=0) as f:
        while time.time() < stop_at:
            off = rnd.randrange(blocks) * block_size
            if rnd.random() < rw_ratio:
                f.seek(off)
                f.write(data)
                write_ops += 1
                write_bytes += block_size
            else:
                f.seek(off)
                _ = f.read(block_size)
                read_ops += 1
                read_bytes += block_size

    try:
        test_path.unlink()
    except:
        pass

    total_ops = read_ops + write_ops
    dt = duration
    return {
        "duration_s": dt,
        "block_size": block_size,
        "file_size_mb": file_size_mb,
        "read_ops": read_ops,
        "write_ops": write_ops,
        "total_ops": total_ops,
        "iops": total_ops / dt if dt > 0 else None,
        "throughput_MB_s": (read_bytes + write_bytes) / (1024*1024) / dt if dt > 0 else None
    }

def bench_gpu():
    """
    Try PyTorch (CUDA) or CuPy for a matmul benchmark.
    Returns info + benchmark metrics if possible.
    """
    result = {
        "available": False,
        "using": None,
        "cuda": False,
        "matmul_size": None,
        "matmul_time_s": None,
        "approx_tflops": None,
        "notes": ""
    }

    # Prefer torch if available and CUDA
    try:
        import torch
        if torch.cuda.is_available():
            result["available"] = True
            result["using"] = "torch"
            result["cuda"] = True
            device = torch.device("cuda:0")
            n = 4096
            a = torch.randn((n,n), device=device, dtype=torch.float16)
            b = torch.randn((n,n), device=device, dtype=torch.float16)
            for _ in range(3):
                (a @ b)
            torch.cuda.synchronize()
            start = time.time()
            _ = a @ b
            torch.cuda.synchronize()
            dt = time.time() - start
            flops = 2.0 * (n**3)
            tflops = (flops / dt) / 1e12
            result.update({
                "matmul_size": n,
                "matmul_time_s": dt,
                "approx_tflops": tflops
            })
            return result
        else:
            result["notes"] = "torch present but CUDA not available"
    except Exception as e:
        result["notes"] = f"torch not usable: {e}"

    try:
        import cupy as cp
        _ = cp.cuda.runtime.getDeviceCount()
        result["available"] = True
        result["using"] = "cupy"
        result["cuda"] = True
        n = 4096
        a = cp.random.randn(n, n, dtype=cp.float16)
        b = cp.random.randn(n, n, dtype=cp.float16)
        for _ in range(3):
            a @ b
        cp.cuda.Device().synchronize()
        start = time.time()
        _ = a @ b
        cp.cuda.Device().synchronize()
        dt = time.time() - start
        flops = 2.0 * (n**3)
        tflops = (flops / dt) / 1e12
        result.update({
                "matmul_size": n,
                "matmul_time_s": dt,
                "approx_tflops": tflops
        })
        return result
    except Exception as e:
        result["notes"] += f" | cupy not usable: {e}"

    if which("nvidia-smi"):
        result["available"] = True
        result["using"] = "nvidia-smi info only"
        result["cuda"] = True
        result["notes"] += " | No GPU Python libs; only reporting info"
    return result

# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser(description="Cloud VM hardware & perf check (no-deps, optional GPU libs).")
    ap.add_argument("--server-name", type=str, default=None, help="Logical name for this server (default: hostname)")
    ap.add_argument("--duration", type=int, default=5, help="Seconds per benchmark section (default: 5)")
    ap.add_argument("--threads", type=int, default=min(4, os.cpu_count() or 1), help="Workers for CPU/memory benchmarks")
    ap.add_argument("--disk-path", type=str, default=None, help="Directory to place temp disk test file (default: fastest tmp)")
    ap.add_argument("--disk-size-mb", type=int, default=1024, help="Disk test file size in MB (default: 1024)")
    ap.add_argument("--mem-size-mb", type=int, default=256, help="Memory test working set in MB (default: 256)")
    ap.add_argument("--skip-gpu", action="store_true", help="Skip GPU benchmark")
    ap.add_argument("--json", action="store_true", help="Also print JSON to stdout")
    ap.add_argument("--out-json", type=str, default=None, help="Write full report to this JSON file")
    ap.add_argument("--out-csv", type=str, default=None, help="Write flattened single-row CSV to this path")
    args = ap.parse_args()

    hostname = socket.gethostname()
    server_name = args.server_name or hostname
    capture_time_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    report = {
        "capture_time_utc": capture_time_utc,
        "server_name": server_name,
        "hostname": hostname,
        "system": get_os_python_info(),
        "cpu": get_cpu_info(),
        "memory": get_mem_info(),
        "disks": get_disk_info(),
        "network": get_net_info(),
        "gpu": get_gpu_info(),
        "benchmarks": {}
    }

    print("== Hardware Info ==")
    print(f"Server: {server_name} (hostname: {hostname})")
    print(f"Captured (UTC): {capture_time_utc}")
    print(f"OS: {report['system']['os']['system']} {report['system']['os']['release']} ({report['system']['os']['machine']})")
    print(f"Python: {report['system']['python']['version']}")
    print(f"CPU: {report['cpu']['model']} | logical={report['cpu']['cores_logical']} physical={report['cpu']['cores_physical']}")
    if report['memory']['total']:
        print(f"RAM: {human_bytes(report['memory']['total'])}")
    if report['gpu'].get("gpus"):
        for g in report['gpu']['gpus']:
            print(f"GPU[{g['index']}]: {g['name']} | mem={g['mem_total_MB']}MB free={g['mem_free_MB']}MB | drv={g['driver']} | util={g['util_percent']}%")

    print("\n== CPU (SHA-256) ==")
    cpu_res = bench_cpu_hash(duration=args.duration, threads=args.threads)
    report["benchmarks"]["cpu_hash"] = cpu_res
    print(f"Workers={cpu_res['workers']} | {cpu_res['ops_per_sec']:.0f} ops/s (1KiB hashes)")

    print("\n== Memory ==")
    mem_res = bench_memory(duration=args.duration, size_mb=args.mem_size_mb, threads=args.threads)
    report["benchmarks"]["memory"] = mem_res
    print(f"Random ops: {mem_res['rand_ops_per_sec']:.0f} ops/s across {args.mem_size_mb} MiB "
          f"(workers={mem_res['workers']}, per-worker={human_bytes(mem_res['payload_per_worker_bytes'])})")
    if mem_res["seq_copy_bandwidth_MiB_s"] is not None:
        print(f"Seq copy: {mem_res['seq_copy_bandwidth_MiB_s']:.1f} MiB/s")

    print("\n== Disk (random 4KiB R/W) ==")
    tmpdir = args.disk_path or tempfile.gettempdir()
    disk_res = bench_disk(tmpdir, file_size_mb=args.disk_size_mb, duration=args.duration, rw_ratio=0.5)
    report["benchmarks"]["disk_random_4k"] = disk_res
    if "error" in disk_res:
        print(f"Disk test error: {disk_res['error']}")
    else:
        print(f"IOPS: {disk_res['iops']:.0f} | Throughput: {disk_res['throughput_MB_s']:.1f} MB/s "
              f"(file={args.disk_size_mb} MB at {tmpdir})")

    if not args.skip_gpu:
        print("\n== GPU ==")
        gpu_bench = bench_gpu()
        report["benchmarks"]["gpu"] = gpu_bench
        if gpu_bench["available"] and gpu_bench["using"] in ("torch","cupy"):
            print(f"Using {gpu_bench['using']} | size {gpu_bench['matmul_size']} | "
                  f"time {gpu_bench['matmul_time_s']:.3f}s | ~{gpu_bench['approx_tflops']:.2f} TFLOPS")
        elif gpu_bench["available"]:
            print(f"GPU present but no Python GPU libs for benchmarking. {gpu_bench['notes']}")
        else:
            print("No GPU or tools available for GPU benchmark.")

    # ---- Save outputs if requested ----
    saved = []
    if args.out_json:
        p = write_json(args.out_json, report)
        saved.append(f"JSON → {p}")
    if args.out_csv:
        p = write_csv(args.out_csv, report)
        saved.append(f"CSV  → {p}")
    if saved:
        print("\nSaved:\n  " + "\n  ".join(saved))

    if args.json:
        print("\n== JSON ==")
        json_print(report)

if __name__ == "__main__":
    main()
