import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloudos.banker import can_allocate, is_safe
from cloudos.models import Process, ResourceVector


import unittest


class TestBanker(unittest.TestCase):
    def test_safe_sequence_simple(self):
        p1 = Process(1, "A", ResourceVector(1, 1, 0, 10), ResourceVector(1, 1, 0, 5))
        p2 = Process(2, "B", ResourceVector(1, 1, 0, 10), ResourceVector(0, 0, 0, 0))
        available = ResourceVector(1, 1, 0, 5)
        safe, seq = is_safe([p1, p2], available)
        self.assertTrue(safe)
        self.assertIn(1, seq)
        self.assertIn(2, seq)

    def test_unsafe_when_needs_exceed_work(self):
        p1 = Process(1, "A", ResourceVector(4, 4, 0, 0), ResourceVector(2, 2, 0, 0))
        p2 = Process(2, "B", ResourceVector(4, 4, 0, 0), ResourceVector(2, 2, 0, 0))
        available = ResourceVector(0, 0, 0, 0)
        safe, _ = is_safe([p1, p2], available)
        self.assertFalse(safe)

    def test_can_allocate_rejects_over_request(self):
        p = Process(1, "X", ResourceVector(2, 2, 0, 0), ResourceVector(0, 0, 0, 0))
        ok = can_allocate(p, ResourceVector(3, 0, 0, 0), ResourceVector(4, 4, 0, 0), [p])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
