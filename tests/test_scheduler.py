import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloudos.models import Process, ProcessState, ResourceVector, SchedulerAlgorithm
from cloudos.scheduler import CPUScheduler


def _proc(pid, arrival, priority=5):
    return Process(
        pid=pid,
        name=f"P{pid}",
        max_need=ResourceVector(1, 1, 0, 0),
        allocated=ResourceVector(1, 0, 0, 0),
        arrival_tick=arrival,
        priority=priority,
        state=ProcessState.READY,
    )


import unittest


class TestScheduler(unittest.TestCase):
    def test_fcfs_picks_earliest_arrival(self):
        sched = CPUScheduler(SchedulerAlgorithm.FCFS)
        ready = [_proc(2, 5), _proc(1, 1)]
        pick = sched.pick_next(ready, None, 10)
        self.assertEqual(pick.pid, 1)

    def test_priority_picks_lowest_number(self):
        sched = CPUScheduler(SchedulerAlgorithm.PRIORITY)
        ready = [_proc(1, 0, priority=5), _proc(2, 0, priority=1)]
        pick = sched.pick_next(ready, None, 0)
        self.assertEqual(pick.pid, 2)


if __name__ == "__main__":
    unittest.main()
