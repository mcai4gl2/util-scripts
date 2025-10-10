#!/usr/bin/env python3
"""
latency_sysdiff.py

Compare two latency_sysdump dump.json files and highlight drift in
latency-critical settings.

Usage:
  python3 latency_sysdiff.py /path/to/old/dump.json /path/to/new/dump.json \
      [--md out.md] [--json out.json] [--only-changed] [--exit-on-critical]

Outputs:
- Console: human-friendly list with severities.
- --md: Markdown report with sections.
- --json: Machine-readable diff {category: [{path, old, new, severity, note}]}.

Rules (simplified, best-effort):
- critical: kernel release/cmdline; clocksource; THP mode; SMT toggle; governor not performance;
            irqbalance state when IRQ pinning used; NIC offloads; ring/channel size reductions;
            coalescing drastic; lscpu hash; libstdc++/glibc ABI level changed.
- warning: swappiness/overcommit; KSM; MTU; toolchain minor bumps; routes.
- info: NIC added/removed; PTP device added; new sysctls.

Python 3.8+; stdlib only.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


SEV_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as f:
        return json.load(f)


def flatten(d: Any, prefix: str = "") -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            res.update(flatten(v, key))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            key = f"{prefix}[{i}]"
            res.update(flatten(v, key))
    else:
        res[prefix] = d
    return res


def fmt_value(v: Any, maxlen: int = 120) -> str:
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    if len(s) > maxlen:
        return s[:maxlen - 3] + "..."
    return s


def extract_first_line(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    try:
        return s.strip().splitlines()[0]
    except Exception:
        return s


def value_changed(a: Any, b: Any) -> bool:
    return a != b


def parse_int(v: Any) -> Optional[int]:
    try:
        return int(str(v).strip(), 0)
    except Exception:
        return None


def severity_of(path: str, old: Any, new: Any, context: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    p = path
    # Critical
    if p == "kernel.uname.release":
        return "CRITICAL", None
    if p == "kernel.cmdline":
        return "CRITICAL", None
    if p == "timekeeping.clocksource_current":
        return "CRITICAL", None
    if p == "cpu_topology.smt_active":
        return "CRITICAL", None
    if p.startswith("cpu_topology.per_cpu_governors."):
        # non-performance governor is critical, otherwise warning
        newv = (str(new).lower() if new is not None else "")
        if newv and newv != "performance":
            return "CRITICAL", "governor != performance"
        return "WARNING", None
    if p == "cpu_topology.lscpu_hash":
        return "CRITICAL", "CPU topology changed"
    if p == "memory.transparent_hugepage.enabled":
        return "CRITICAL", None
    if p.startswith("irq.smp_affinity_list."):
        return "CRITICAL", None
    if p.startswith("network.interfaces.") and ".ethtool.features." in p:
        # NIC offloads toggled
        feat = p.split(".ethtool.features.", 1)[1]
        crit_feats = {
            "generic-receive-offload", "large-receive-offload", "tcp-segmentation-offload",
            "tso", "gso", "lro", "rx-checksumming", "tx-checksumming", "scatter-gather",
        }
        if any(f in feat for f in crit_feats):
            return "CRITICAL", None
        return "WARNING", None
    if p.startswith("network.interfaces.") and ".ethtool.rings." in p:
        # ring size reductions are critical
        o, n = parse_int(old), parse_int(new)
        if o is not None and n is not None and n < o:
            return "CRITICAL", "ring size reduced"
        return "INFO", None
    if p.startswith("network.interfaces.") and ".ethtool.channels." in p:
        o, n = parse_int(old), parse_int(new)
        if o is not None and n is not None and n < o:
            return "CRITICAL", "channels reduced"
        return "INFO", None
    if p.startswith("network.interfaces.") and ".ethtool.coalesce." in p:
        # drastic coalesce change
        o, n = parse_int(old), parse_int(new)
        if o is not None and n is not None and abs(n - o) >= 32:
            return "CRITICAL", "coalesce changed drastically"
        return "WARNING", None
    if p == "toolchain.libstdcxx_max_glibcxx":
        return "CRITICAL", "libstdc++ ABI level changed"
    # irqbalance
    if p == "services_sysctl.irqbalance.state":
        if context.get("irq_affinity_present"):
            return "CRITICAL", "irqbalance change with IRQ pinning"
        return "WARNING", None
    # Warnings
    if p in ("memory.overcommit_memory", "memory.swappiness"):
        return "WARNING", None
    if p.startswith("memory.ksm."):
        return "WARNING", None
    if p.endswith(".mtu") and p.startswith("network.interfaces."):
        return "WARNING", None
    if p.startswith("toolchain."):
        # generic toolchain changes as warning (unless ABI above)
        return "WARNING", None
    if p.startswith("network.routes."):
        return "WARNING", None
    if p.startswith("services_sysctl.sysctl."):
        return "WARNING", None
    # Infos
    if p.startswith("timekeeping.ptp_devices"):
        return "INFO", None
    if p.startswith("network.interfaces."):
        return "INFO", None
    if p.startswith("containers."):
        return "INFO", None
    # default
    return "INFO", None


def category_of(path: str) -> str:
    return path.split(".", 1)[0] if "." in path else path


def compute_irq_affinity_present(d: Dict[str, Any]) -> bool:
    try:
        aff = ((d.get("irq") or {}).get("smp_affinity_list") or {})
        return bool(aff)
    except Exception:
        return False


def diff_dumps(old: Dict[str, Any], new: Dict[str, Any], only_changed: bool) -> Dict[str, List[Dict[str, Any]]]:
    # Build flatten maps
    f_old = flatten(old)
    f_new = flatten(new)
    keys = set(f_old.keys()) | set(f_new.keys())
    context = {"irq_affinity_present": compute_irq_affinity_present(old) or compute_irq_affinity_present(new)}
    diffs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # Track NIC add/remove
    old_ifaces = set(((old.get("network") or {}).get("interfaces") or {}).keys())
    new_ifaces = set(((new.get("network") or {}).get("interfaces") or {}).keys())
    for iface in sorted(old_ifaces - new_ifaces):
        diffs["network"].append({
            "path": f"network.interfaces.{iface}",
            "old": "present",
            "new": "absent",
            "severity": "INFO",
            "note": "interface removed",
        })
    for iface in sorted(new_ifaces - old_ifaces):
        diffs["network"].append({
            "path": f"network.interfaces.{iface}",
            "old": "absent",
            "new": "present",
            "severity": "INFO",
            "note": "interface added",
        })

    for k in sorted(keys):
        a = f_old.get(k, None)
        b = f_new.get(k, None)
        if not value_changed(a, b):
            continue
        sev, note = severity_of(k, a, b, context)
        cat = category_of(k)
        diffs[cat].append({
            "path": k,
            "old": a,
            "new": b,
            "severity": sev,
            "note": note,
        })

    if only_changed:
        diffs = {k: v for k, v in diffs.items() if v}
    return diffs


def print_console(diffs: Dict[str, List[Dict[str, Any]]]) -> int:
    ncrit = 0
    # Order by severity then path
    items: List[Tuple[str, Dict[str, Any]]] = []
    for cat, lst in diffs.items():
        for it in lst:
            items.append((cat, it))
    items.sort(key=lambda x: (SEV_ORDER.get(x[1]["severity"], 99), x[1]["path"]))
    for cat, it in items:
        sev = it["severity"].upper().ljust(8)
        note = f" ({it['note']})" if it.get("note") else ""
        old = fmt_value(it["old"]) if it["old"] is not None else "(absent)"
        new = fmt_value(it["new"]) if it["new"] is not None else "(absent)"
        print(f"[{sev}] {it['path']}: {old} -> {new}{note}")
        if it["severity"] == "CRITICAL":
            ncrit += 1
    if not items:
        print("No differences detected.")
    return ncrit


def write_md(path: Path, diffs: Dict[str, List[Dict[str, Any]]]) -> None:
    lines: List[str] = []
    lines.append("# Latency Sysdiff Report")
    cats = sorted(diffs.keys())
    for cat in cats:
        lines.append("")
        lines.append(f"## {cat}")
        # sort by severity
        items = sorted(diffs[cat], key=lambda it: (SEV_ORDER.get(it["severity"], 99), it["path"]))
        for it in items:
            note = f" ({it['note']})" if it.get("note") else ""
            old = fmt_value(it["old"]) if it["old"] is not None else "(absent)"
            new = fmt_value(it["new"]) if it["new"] is not None else "(absent)"
            lines.append(f"- [{it['severity']}] `{it['path']}`: {old} -> {new}{note}")
    path.write_text("\n".join(lines))


def write_json(path: Path, diffs: Dict[str, List[Dict[str, Any]]]) -> None:
    with path.open("w") as f:
        json.dump(diffs, f, indent=2, sort_keys=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare two latency_sysdump JSON dumps and report latency-relevant drift")
    ap.add_argument("old", help="Path to old dump.json")
    ap.add_argument("new", help="Path to new dump.json")
    ap.add_argument("--md", dest="md", help="Write Markdown report to this file")
    ap.add_argument("--json", dest="jout", help="Write JSON diff to this file")
    ap.add_argument("--only-changed", action="store_true", help="Suppress unchanged categories")
    ap.add_argument("--exit-on-critical", action="store_true", help="Exit non-zero if critical drift detected")
    args = ap.parse_args()

    old = load_json(Path(args.old))
    new = load_json(Path(args.new))
    diffs = diff_dumps(old, new, args.only_changed)
    ncrit = print_console(diffs)

    if args.md:
        write_md(Path(args.md), diffs)
    if args.jout:
        write_json(Path(args.jout), diffs)

    if args.exit_on_critical and ncrit > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()

