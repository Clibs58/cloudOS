import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloudos.config import ConfigStore, validate_config


class TestConfig(unittest.TestCase):
    def test_validate_rejects_bad_capacity(self):
        errors = validate_config({"capacity": {"cpu": 0, "ram_gb": 32, "gpu": 1, "storage_gb": 100}})
        self.assertTrue(any("capacity.cpu" in e for e in errors))

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            store = ConfigStore(path)
            data = store.get()
            data["capacity"]["cpu"] = 8
            store.save(data)
            reloaded = ConfigStore(path).get()
            self.assertEqual(reloaded["capacity"]["cpu"], 8)
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["capacity"]["cpu"], 8)


if __name__ == "__main__":
    unittest.main()
