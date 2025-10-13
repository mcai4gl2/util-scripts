#!/usr/bin/env python3
# pidinfo.py — Detailed CPU/memory/IO/threads/affinity/cgroups + FD/socket info for a PID
# Usage examples:
#   ./pidinfo.py 1234
#   ./pidinfo.py --json 1234
#   ./pidinfo.py --watch 1234 0.5
#   ./pidinfo.py --watch --json 1234         # NDJSON stream
#   ./pidinfo.py --fds 1234
#   ./pidinfo.py --fds-all 1234

import argparse
import os
import sys
import time
import json
import pwd
import grp
import stat as pystat
from pathlib import Path
from typing import Dict, Any, List, Tuple

# ---------------- util ----------------

def read_text(path: Path, default: str = "", max_bytes: int = 1_000_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception:
        return default

def read_first_line(path: Path, default: str = "") -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.readline().rstrip("\n")
    except Exception:
        return default

def file_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False

def human_uptime(secs: float) -> str:
    s = int(max(secs, 0))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{d}d {h:02d}h {m:02d}m {s:02d}s"

def print_clear():
    # harmless if not a TTY
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()

# ---------------- sampling helpers ----------------

def read_stat_total_ticks() -> int:
    # Sum of all cpu time fields from /proc/stat "cpu " line
    try:
        with open("/proc/stat", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()
                    return sum(int(x) for x in parts[1:])
    except Exception:
        pass
    return 0

def read_pid_ticks(pid: int) -> int:
    # /proc/<pid>/stat fields: 14=utime, 15=stime
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as f:
            parts = f.read().split()
            utime = int(parts[13])
            stime = int(parts[14])
            return utime + stime
    except Exception:
        return 0

def read_io_bytes(pid: int) -> Tuple[int, int]:
    # /proc/<pid>/io read_bytes: & write_bytes:
    rb = 0
    wb = 0
    try:
        with open(f"/proc/{pid}/io", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("read_bytes:"):
                    rb = int(line.split()[1])
                elif line.startswith("write_bytes:"):
                    wb = int(line.split()[1])
    except Exception:
        pass
    return rb, wb

# ---------------- FD / sockets decoding ----------------

TCP_STATE = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}

def decode_ipv4(ap: str) -> str:
    # "0100007F:1F90" => 127.0.0.1:8080 (little-endian addr)
    try:
        addr_hex, port_hex = ap.split(":")
        a = int(addr_hex[6:8], 16)
        b = int(addr_hex[4:6], 16)
        c = int(addr_hex[2:4], 16)
        d = int(addr_hex[0:2], 16)
        port = int(port_hex, 16)
        return f"{a}.{b}.{c}.{d}:{port}"
    except Exception:
        return f"ipv4:{ap}"

def build_sock_maps(pid: int) -> Dict[str, str]:
    """Return inode->detail string for tcp,udp,tcp6,udp6,unix within the PID's net ns."""
    maps: Dict[str, str] = {}

    def add(inode: str, value: str):
        if inode and inode != "0":
            maps[inode] = value

    # tcp (IPv4)
    p = Path(f"/proc/{pid}/net/tcp")
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            next(f)  # header
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    la, ra, st, inode = parts[1], parts[2], parts[3], parts[9]
                    add(inode, f"TCP {TCP_STATE.get(st,'UNKNOWN')} {decode_ipv4(la)} {decode_ipv4(ra)}")
    except Exception:
        pass

    # udp (IPv4)
    p = Path(f"/proc/{pid}/net/udp")
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    la, ra, inode = parts[1], parts[2], parts[9]
                    add(inode, f"UDP {decode_ipv4(la)} {decode_ipv4(ra)}")
    except Exception:
        pass

    # tcp6 / udp6 (leave hex to avoid heavy formatting)
    p = Path(f"/proc/{pid}/net/tcp6")
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    la, ra, st, inode = parts[1], parts[2], parts[3], parts[9]
                    add(inode, f"TCP6 {TCP_STATE.get(st,'UNKNOWN')} ipv6:{la} ipv6:{ra}")
    except Exception:
        pass

    p = Path(f"/proc/{pid}/net/udp6")
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    la, ra, inode = parts[1], parts[2], parts[9]
                    add(inode, f"UDP6 ipv6:{la} ipv6:{ra}")
    except Exception:
        pass

    # unix: columns: Num RefCount Protocol Flags Type St Inode Path
    p = Path(f"/proc/{pid}/net/unix")
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                parts = line.split(None, 7)
                if len(parts) >= 7:
                    inode = parts[6]
                    path = parts[7].rstrip() if len(parts) >= 8 else "-"
                    add(inode, f"UNIX {path}")
    except Exception:
        pass

    return maps

def collect_fds(pid: int, cap: int) -> Tuple[List[Dict[str, Any]], int]:
    """Return (list_of_fd_objects, total_fd_count)."""
    fd_dir = Path(f"/proc/{pid}/fd")
    fdinfo_dir = Path(f"/proc/{pid}/fdinfo")
    sock_maps = build_sock_maps(pid)
    results: List[Dict[str, Any]] = []
    total = 0

    try:
        entries = sorted(fd_dir.iterdir(), key=lambda p: int(p.name))
    except Exception:
        entries = []

    for entry in entries:
        try:
            n = int(entry.name)
        except Exception:
            continue

        total += 1
        # target
        try:
            target = os.readlink(str(entry))
        except Exception:
            target = "???"

        # flags/pos for mode decode
        flags_oct = None
        pos = None
        try:
            info = read_text(fdinfo_dir / entry.name)
            for line in info.splitlines():
                if line.startswith("flags:"):
                    flags_oct = line.split()[1]
                elif line.startswith("pos:"):
                    pos = int(line.split()[1])
        except Exception:
            pass

        mode = None
        if flags_oct:
            try:
                fdec = int(flags_oct, 8)
                m = fdec & 3
                mode = {0: "RDONLY", 1: "WRONLY", 2: "RDWR"}.get(m, "UNK")
            except Exception:
                mode = "UNK"

        ftype = "file"
        detail = target
        if target.startswith("socket:["):
            ftype = "socket"
            inode = target.split("[", 1)[1].rstrip("]")
            detail = sock_maps.get(inode, f"socket inode={inode}")
        elif target.startswith("pipe:["):
            ftype = "pipe"
        elif target.startswith("anon_inode:"):
            ftype = "anon_inode"

        obj = {
            "fd": n,
            "type": ftype,
            "mode": mode,
            "pos": pos if pos is not None else 0,
            "target": target,
            "detail": detail,
        }
        if len(results) < cap:
            results.append(obj)

    return results, total

# ---------------- core sample ----------------

def one_sample(pid: int, interval: float, hz: int, ncpu: int, need_fds: bool, fds_cap: int) -> Dict[str, Any]:
    # Pre
    t0_sys = read_stat_total_ticks()
    t0_pid = read_pid_ticks(pid)
    t0_rb, t0_wb = read_io_bytes(pid)

    time.sleep(interval)

    if not file_exists(Path(f"/proc/{pid}")):
        raise RuntimeError(f"pidinfo: PID {pid} exited.")

    # Post
    t1_sys = read_stat_total_ticks()
    t1_pid = read_pid_ticks(pid)
    t1_rb, t1_wb = read_io_bytes(pid)

    d_sys = max(t1_sys - t0_sys, 0)
    d_pid = max(t1_pid - t0_pid, 0)
    cpu_pct = None
    if d_sys > 0:
        cpu_pct = (d_pid / d_sys) * 100.0 * max(ncpu, 1)

    drb = max(t1_rb - t0_rb, 0)
    dwb = max(t1_wb - t0_wb, 0)
    r_bps = (drb / interval) if interval > 0 else 0.0
    w_bps = (dwb / interval) if interval > 0 else 0.0

    # Static-ish process info
    proc_path = Path(f"/proc/{pid}")
    comm = read_first_line(proc_path / "comm")
    exe = ""
    try:
        exe = os.readlink(str(proc_path / "exe"))
    except Exception:
        pass

    # cmdline: '\0'-separated
    raw_cmd = read_text(proc_path / "cmdline")
    cmd = " ".join([x for x in raw_cmd.split("\0") if x]) if raw_cmd else comm

    # uid/gid -> names
    try:
        st = os.stat(proc_path)
        uid, gid = st.st_uid, st.st_gid
        user = pwd.getpwuid(uid).pw_name if uid is not None else str(uid)
        group = grp.getgrgid(gid).gr_name if gid is not None else str(gid)
    except Exception:
        user = "?"
        group = "?"

    # status fields
    state = threads = vmsize = vmrss = vmswap = None
    status_txt = read_text(proc_path / "status")
    for line in status_txt.splitlines():
        if line.startswith("State:"):
            state = line.split(":", 1)[1].strip()
        elif line.startswith("Threads:"):
            threads = int(line.split(":", 1)[1].strip())
        elif line.startswith("VmSize:"):
            vmsize = line.split(":", 1)[1].strip()
        elif line.startswith("VmRSS:"):
            vmrss = line.split(":", 1)[1].strip()
        elif line.startswith("VmSwap:"):
            vmswap = line.split(":", 1)[1].strip()

    # smaps_rollup
    rss = anon = filem = shmem = pss = swap = pssswap = None
    sm_roll = proc_path / "smaps_rollup"
    if file_exists(sm_roll):
        for line in read_text(sm_roll).splitlines():
            parts = line.split()
            if not parts:
                continue
            k = parts[0]
            val = " ".join(parts[1:]) if len(parts) > 1 else ""
            if k == "Rss:":
                rss = val
            elif k == "Pss:":
                pss = val
            elif k == "RssAnon:":
                anon = val
            elif k == "RssFile:":
                filem = val
            elif k == "RssShmem:":
                shmem = val
            elif k == "Swap:":
                swap = val
            elif k == "SwapPss:":
                pssswap = val

    # affinity (Cpus_allowed_list)
    cpus_allowed_list = None
    for line in status_txt.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            cpus_allowed_list = line.split(":", 1)[1].strip()

    # fds, maps
    try:
        fdcount = len(list((proc_path / "fd").iterdir()))
    except Exception:
        fdcount = None
    try:
        with (proc_path / "maps").open("r", encoding="utf-8", errors="replace") as f:
            maps_count = sum(1 for _ in f)
    except Exception:
        maps_count = None

    # cwd, root
    cwd = rootdir = ""
    try:
        cwd = os.path.realpath(str(proc_path / "cwd"))
    except Exception:
        pass
    try:
        rootdir = os.path.realpath(str(proc_path / "root"))
    except Exception:
        rootdir = "/"

    # uptime math
    try:
        with open("/proc/uptime", "r", encoding="utf-8", errors="replace") as f:
            boot_uptime = float(f.read().split()[0])
    except Exception:
        boot_uptime = 0.0

    start_ticks = 0
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as f:
            parts = f.read().split()
            start_ticks = int(parts[21])
    except Exception:
        pass
    start_secs = start_ticks / float(hz) if hz > 0 else 0.0
    proc_uptime = max(boot_uptime - start_secs, 0.0)

    # cgroups
    cgroups_lines = []
    try:
        with open(f"/proc/{pid}/cgroup", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # strip "N:controllers:" prefix and leading '/'
                if ":" in line:
                    cg = line.split(":", 2)[-1].lstrip("/")
                    cgroups_lines.append(cg or "/")
    except Exception:
        pass
    cgroups = " | ".join(cgroups_lines) if cgroups_lines else None

    # limits (header + a few interesting rows)
    key_limits: List[str] = []
    try:
        with open(f"/proc/{pid}/limits", "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx == 0 or "Max open files" in line or "Max address space" in line or "Max locked memory" in line:
                    key_limits.append(line.rstrip("\n"))
    except Exception:
        pass

    fds_list: List[Dict[str, Any]] = []
    total_fds = 0
    if need_fds:
        fds_list, total_fds = collect_fds(pid, fds_cap)

    return {
        "pid": pid,
        "interval_sec": interval,
        "cpu": {
            "percent": round(cpu_pct, 2) if cpu_pct is not None else None,
            "ncpu": ncpu,
            "affinity": cpus_allowed_list or "",
        },
        "memory": {
            "VmRSS": vmrss or "",
            "VmSize": vmsize or "",
            "VmSwap": vmswap or "",
            "Rss": rss or "",
            "Anon": anon or "",
            "File": filem or "",
            "Shmem": shmem or "",
            "Pss": pss or "",
            "Swap": swap or "",
        },
        "io": {
            "read_bytes_total": t1_rb,
            "write_bytes_total": t1_wb,
            "read_Bps": round(r_bps, 1),
            "write_Bps": round(w_bps, 1),
        },
        "proc": {
            "user": user,
            "group": group,
            "state": state or "",
            "threads": threads,
            "cmd": cmd,
            "comm": comm,
            "exe": exe or "",
            "cwd": cwd or "",
            "root": rootdir or "/",
            "uptime_human": human_uptime(proc_uptime),
        },
        "cgroups": cgroups or "",
        "limits": "\n".join(key_limits) if key_limits else "",
        "fd_summary": {
            "open_count": fdcount,
            "maps_count": maps_count,
            "shown": len(fds_list),
            "total": total_fds,
        } if need_fds else None,
        "fds": fds_list if need_fds else None,
    }

# ---------------- printing ----------------

def print_human(d: Dict[str, Any], show_fds: bool, show_fds_all: bool):
    print_clear()
    pid = d["pid"]
    interval = d["interval_sec"]
    cpu = d["cpu"]
    mem = d["memory"]
    io = d["io"]
    proc = d["proc"]
    print("────────────────────────────────────────────────────────")
    print(f"PID:            {pid}")
    print(f"User/Group:     {proc['user']} / {proc['group']}")
    print(f"Command:        {proc['cmd']}")
    print(f"Exe:            {proc['exe'] or 'N/A'}")
    print(f"CWD:            {proc['cwd'] or 'N/A'}")
    print(f"Root:           {proc['root'] or '/'}")
    print()
    print(f"State:          {proc['state'] or 'N/A'}")
    print(f"Threads:        {proc.get('threads') if proc.get('threads') is not None else 'N/A'}")
    print(f"CPU(s):         {cpu['ncpu']}")
    print(f"Affinity:       {cpu['affinity'] or 'N/A'}")
    pct = f"{cpu['percent']:.2f}%" if cpu['percent'] is not None else "N/A"
    print(f"CPU% (~{interval}s):  {pct}")
    print()
    print(f"Memory (status): VmRSS={mem['VmRSS'] or 'N/A'} | VmSize={mem['VmSize'] or 'N/A'} | VmSwap={mem['VmSwap'] or '0 kB'}")
    # Show smaps_rollup if present
    if any(mem.get(k) for k in ("Rss","Anon","File","Shmem","Pss","Swap")):
        print(f"Memory (smaps_rollup): Rss={mem['Rss'] or 'N/A'} | Anon={mem['Anon'] or 'N/A'} | File={mem['File'] or 'N/A'} | Shmem={mem['Shmem'] or 'N/A'} | Pss={mem['Pss'] or 'N/A'} | Swap={mem['Swap'] or '0 kB'}")
    print()
    print(f"I/O totals:     read_bytes={io['read_bytes_total']:,}  write_bytes={io['write_bytes_total']:,}")
    print(f"I/O rates:      read/s={io['read_Bps']:.1f} B/s  write/s={io['write_Bps']:.1f} B/s  (avg over {interval}s)")
    print()
    # fd summary/maps
    fd_summary = d.get("fd_summary")
    if fd_summary:
        print(f"FDs open:       {fd_summary.get('open_count', 'N/A')}")
        print(f"VMAs (maps):    {fd_summary.get('maps_count','N/A')}")
    else:
        # fallback if not gathered
        print("FDs open:       N/A")
        print("VMAs (maps):    N/A")
    print()
    print(f"Started:        ~{proc['uptime_human']} ago  (proc uptime)")
    print(f"Cgroups:        {d.get('cgroups') or 'N/A'}")
    print()
    print("Key limits:")
    print(d.get("limits") or "N/A")

    if show_fds and d.get("fds") is not None:
        print()
        print("FD details: (fd  type      mode    position     detail)")
        print("----------- ---------------------------------------------------------------")
        for fd in d["fds"]:
            fdn = fd["fd"]
            typ = (fd["type"] or "")[:10]
            mode = fd["mode"] or "?"
            pos = fd["pos"] if fd["pos"] is not None else 0
            detail = fd["detail"]
            print(f"{fdn:4d}  {typ:<8}  {mode:<6}  pos={pos:<10}  {detail}")
        total = d["fd_summary"]["total"]
        shown = d["fd_summary"]["shown"]
        if not show_fds_all and total and shown and total > shown:
            print(f"… ({total} total; showing first {shown}) — use --fds-all to show all.")

    print("────────────────────────────────────────────────────────")

def print_json(d: Dict[str, Any], ndjson: bool):
    if ndjson:
        # one line per sample
        sys.stdout.write(json.dumps(d, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        json.dump(d, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        sys.stdout.flush()

# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(description="pidinfo — per-PID CPU/mem/IO/affinity/cgroups + FD/socket inspector")
    ap.add_argument("pid", type=int, help="PID to inspect")
    ap.add_argument("interval", nargs="?", type=float, default=1.0, help="sampling interval seconds (default: 1)")
    ap.add_argument("--json", action="store_true", help="output JSON (NDJSON if combined with --watch)")
    ap.add_argument("--watch", action="store_true", help="repeat indefinitely")
    ap.add_argument("--fds", action="store_true", help="include FD table (human) / embed fds array (json); caps at 50/200")
    ap.add_argument("--fds-all", action="store_true", help="include ALL FDs (no cap in human; json still capped at 200)")
    args = ap.parse_args()

    pid = args.pid
    if not Path(f"/proc/{pid}").is_dir():
        print(f"PID {pid} not found (no /proc/{pid})", file=sys.stderr)
        return 1

    try:
        hz = os.sysconf("SC_CLK_TCK")
    except Exception:
        hz = 100
    ncpu = os.cpu_count() or 1

    show_fds = args.fds or args.fds_all
    fds_cap_human = 50 if not args.fds_all else 1_000_000
    fds_cap_json = 200  # keep JSON reasonable in size

    try:
        if args.watch:
            while True:
                sample = one_sample(
                    pid=pid,
                    interval=args.interval,
                    hz=hz,
                    ncpu=ncpu,
                    need_fds=show_fds or args.json,  # collect fds if requested or json wants embedding
                    fds_cap=(fds_cap_json if args.json else fds_cap_human),
                )
                if args.json:
                    print_json(sample, ndjson=True)
                else:
                    print_human(sample, show_fds=show_fds, show_fds_all=args.fds_all)
        else:
            sample = one_sample(
                pid=pid,
                interval=args.interval,
                hz=hz,
                ncpu=ncpu,
                need_fds=show_fds or args.json,
                fds_cap=(fds_cap_json if args.json else fds_cap_human),
            )
            if args.json:
                print_json(sample, ndjson=False)
            else:
                print_human(sample, show_fds=show_fds, show_fds_all=args.fds_all)
    except KeyboardInterrupt:
        return 130
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    return 0

if __name__ == "__main__":
    sys.exit(main())
