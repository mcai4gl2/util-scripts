import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).parent


def load_sysdiff_module():
    mod_path = HERE / "latency_sysdiff.py"
    spec = importlib.util.spec_from_file_location("latency_sysdiff_module", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


class TestLatencySysdiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_sysdiff_module()

    def test_flatten(self):
        f = self.mod.flatten({"a": {"b": 1}, "c": [2, {"d": 3}]})
        self.assertEqual(f["a.b"], 1)
        self.assertEqual(f["c[0]"], 2)
        self.assertEqual(f["c[1].d"], 3)

    def test_severity_of_core(self):
        sev, note = self.mod.severity_of("kernel.uname.release", "5.10", "6.1", {})
        self.assertEqual(sev, "CRITICAL")
        sev, note = self.mod.severity_of("timekeeping.clocksource_current", "tsc", "hpet", {})
        self.assertEqual(sev, "CRITICAL")
        sev, note = self.mod.severity_of("cpu_topology.per_cpu_governors.cpu0", "performance", "powersave", {})
        self.assertEqual(sev, "CRITICAL")
        sev, note = self.mod.severity_of("cpu_topology.per_cpu_governors.cpu0", "powersave", "performance", {})
        self.assertEqual(sev, "WARNING")

    def test_diff_nic_features(self):
        old = {
            "network": {
                "interfaces": {
                    "eth0": {
                        "ethtool": {"features": {"tcp-segmentation-offload": True}}
                    }
                }
            }
        }
        new = {
            "network": {
                "interfaces": {
                    "eth0": {
                        "ethtool": {"features": {"tcp-segmentation-offload": False}}
                    }
                }
            }
        }
        diffs = self.mod.diff_dumps(old, new, only_changed=True)
        found = False
        for it in diffs.get("network", []):
            if it["path"].endswith("tcp-segmentation-offload"):
                self.assertEqual(it["severity"], "CRITICAL")
                found = True
        self.assertTrue(found)

    def test_category_and_fmt(self):
        self.assertEqual(self.mod.category_of("network.interfaces.eth0.mtu"), "network")
        val = "a" * 200
        s = self.mod.fmt_value(val, maxlen=40)
        self.assertTrue(s.endswith("..."))
        self.assertEqual(len(s), 40)


if __name__ == "__main__":
    unittest.main()

