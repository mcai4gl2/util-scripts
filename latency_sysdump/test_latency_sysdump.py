import os
import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).parent


def load_sysdump_module():
    mod_path = HERE / "latency_sysdump.py"
    spec = importlib.util.spec_from_file_location("latency_sysdump_module", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


class TestLatencySysdump(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_sysdump_module()

    def test_parse_cmdline(self):
        pc = self.mod.parse_cmdline("isolcpus=1-3 nohz_full=2-7 rcu_nocbs=2-7 fooflag")
        self.assertEqual(pc.get("isolcpus"), "1-3")
        self.assertEqual(pc.get("nohz_full"), "2-7")
        self.assertEqual(pc.get("rcu_nocbs"), "2-7")
        self.assertIn("fooflag", pc)
        self.assertEqual(pc["fooflag"], "")

    def test_thp_mode(self):
        self.assertEqual(self.mod.thp_mode("always madvise [never]"), "never")
        self.assertEqual(self.mod.thp_mode("[always] madvise never"), "always")
        self.assertIsNone(self.mod.thp_mode(None))

    def test_parse_ethtool_features(self):
        text = """
generic-receive-offload: on
tcp-segmentation-offload: off
feature-x: maybe
"""
        feats = self.mod.parse_ethtool_features(text)
        self.assertIs(feats.get("generic-receive-offload"), True)
        self.assertIs(feats.get("tcp-segmentation-offload"), False)
        self.assertEqual(feats.get("feature-x"), "maybe")

    def test_parse_numeric_map(self):
        text = """
rx: 512
tx: 0x100
name: eth0
"""
        m = self.mod.parse_numeric_map(text)
        self.assertEqual(m.get("rx"), 512)
        self.assertEqual(m.get("tx"), 256)
        self.assertEqual(m.get("name"), "eth0")

    def test_parse_interrupts(self):
        sample = """
           CPU0       CPU1
  24:          5          7   PCI-MSI  eth0-rx-0
  25:         10          0   PCI-MSI  eth0-tx-0
"""
        res = self.mod.parse_interrupts(sample)
        self.assertIn("24", res)
        self.assertEqual(res["24"]["total"], 12)
        self.assertIn("25", res)
        self.assertEqual(res["25"]["total"], 10)

    def test_generate_report_minimal(self):
        data = {
            "meta": {"timestamp": "20240101_000000"},
            "kernel": {"uname": {"release": "6.1.0"}, "cmdline": "", "vulnerabilities": {}},
            "cpu_topology": {"smt_active": False, "per_cpu_governors": {}},
            "timekeeping": {"clocksource_current": "tsc", "clocksource_available": "tsc hpet", "ptp_devices": []},
            "memory": {"transparent_hugepage": {"enabled": "never", "defrag": "never"}, "nr_hugepages": "0", "hugepagesize": "2048 kB", "overcommit_memory": "0", "swappiness": "60", "ksm": {}},
            "network": {"interfaces": {}},
            "irq": {"smp_affinity_list": {}},
            "toolchain": {"gcc_version": "gcc (Debian) 13.2"},
            "services_sysctl": {"irqbalance": {"state": "inactive"}, "tuned_adm": None, "aslr": "2", "selinux": None, "apparmor": None},
            "containers": {"docker_systemd_state": None, "cgroup": {"mode": "v2"}, "wsl": False},
        }
        report = self.mod.generate_report(data)
        self.assertIsInstance(report, str)
        self.assertIn("Latency System Dump", report)
        self.assertIn("Release: 6.1.0", report)


if __name__ == "__main__":
    unittest.main()

