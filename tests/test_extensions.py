import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest
from cloudos.models import Process, ProcessState, ResourceVector, SchedulerAlgorithm, SystemCapacity
from cloudos.scheduler import CPUScheduler
from cloudos.banker import is_safe, explain_safety, detect_deadlock
from cloudos.memory import PagingMemoryManager
from cloudos.engine import CloudOSEngine


class TestExtensions(unittest.TestCase):
    def test_sjf_and_srtf_scheduling(self):
        p1 = Process(1, "Long", ResourceVector(1, 1, 0, 0), ResourceVector(1, 1, 0, 0), burst_time=10, remaining_burst=10, arrival_tick=0)
        p2 = Process(2, "Short", ResourceVector(1, 1, 0, 0), ResourceVector(1, 1, 0, 0), burst_time=2, remaining_burst=2, arrival_tick=1)

        # SJF picks shorter burst
        sched_sjf = CPUScheduler(SchedulerAlgorithm.SJF)
        pick = sched_sjf.pick_next([p1, p2], None, 1)
        self.assertEqual(pick.pid, 2)

        # SRTF preempts when remaining burst of new ready process is shorter
        sched_srtf = CPUScheduler(SchedulerAlgorithm.SRTF)
        p1.remaining_burst = 8
        p2.remaining_burst = 2
        self.assertTrue(sched_srtf.should_preempt(p1, 2, 1, [p1, p2]))

    def test_preemptive_priority(self):
        p1 = Process(1, "LowPrio", ResourceVector(1, 1, 0, 0), ResourceVector(1, 1, 0, 0), priority=5)
        p2 = Process(2, "HighPrio", ResourceVector(1, 1, 0, 0), ResourceVector(1, 1, 0, 0), priority=1)

        sched = CPUScheduler(SchedulerAlgorithm.PRIORITY_PREEMPTIVE)
        self.assertTrue(sched.should_preempt(p1, 1, 1, [p1, p2]))
        pick = sched.pick_next([p1, p2], None, 1)
        self.assertEqual(pick.pid, 2)

    def test_explain_safety(self):
        p1 = Process(1, "A", ResourceVector(2, 2, 0, 0), ResourceVector(1, 1, 0, 0))
        avail = ResourceVector(1, 1, 0, 0)
        res = explain_safety([p1], avail)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["safe_sequence"], [1])
        self.assertEqual(len(res["steps"]), 1)

    def test_memory_paging_fifo_and_lru(self):
        mem = PagingMemoryManager(num_frames=2, policy="FIFO")
        # Load page 0 of P1
        r1 = mem.access_page(1, "P1", 0, 1)
        self.assertFalse(r1["hit"])
        self.assertEqual(r1["frame_id"], 0)

        # Hit page 0 of P1
        r2 = mem.access_page(1, "P1", 0, 2)
        self.assertTrue(r2["hit"])

        # Load page 1 of P1 into free frame 1
        r3 = mem.access_page(1, "P1", 1, 3)
        self.assertFalse(r3["hit"])
        self.assertEqual(r3["frame_id"], 1)

        # Page fault: should evict frame 0 under FIFO (loaded at tick 1 vs tick 3)
        r4 = mem.access_page(2, "P2", 0, 4)
        self.assertFalse(r4["hit"])
        self.assertEqual(r4["frame_id"], 0)

    def test_engine_multicore_and_metrics(self):
        engine = CloudOSEngine(SystemCapacity(cpu=4, ram_gb=16, gpu=1, storage_gb=500))
        engine.set_active_cores(2)
        engine.set_scheduler("FCFS")
        engine.add_process("Task1", 1, 2, 0, 10, burst_time=4, priority=3)
        engine.add_process("Task2", 1, 2, 0, 10, burst_time=4, priority=3)

        # Run 4 ticks
        engine.run_ticks(4)
        # In 2-core mode, both Task1 and Task2 run concurrently and should terminate around tick 4!
        m = engine.calculate_metrics()
        self.assertEqual(m["completed_count"], 2)
        self.assertGreater(m["cpu_utilization"], 0)

    def test_banker_avoidance_toggle_and_deadlock_trap(self):
        engine = CloudOSEngine()
        engine.load_scenario("deadlock_trap")
        # With deadlock avoidance enabled, safety is reported
        snap = engine.snapshot()
        self.assertFalse(snap.deadlock_detected)

        # Disable avoidance and verify detection
        engine.set_deadlock_avoidance(False)
        engine.step()
        snap2 = engine.snapshot()
        self.assertTrue(snap2.deadlock_detected)

    def test_round_robin_quantum_enforcement(self):
        engine = CloudOSEngine()
        engine.set_active_cores(1)
        engine.set_scheduler("round_robin", quantum=3)
        res = ResourceVector(1, 1, 0, 10)
        engine.add_process("P1", 1, 1, 0, 10, burst_time=6, priority=1, start_allocated=res)
        engine.add_process("P2", 1, 1, 0, 10, burst_time=6, priority=1, start_allocated=res)

        p1 = engine.processes[0]
        p2 = engine.processes[1]

        # Run 3 ticks - P1 should run for all 3 ticks because quantum=3
        for _ in range(3):
            engine.step()
        self.assertEqual(p1.remaining_burst, 3)
        self.assertEqual(p2.remaining_burst, 6)

        # At tick 4, P1 preempts and P2 should run for 3 ticks (ticks 4, 5, 6)
        for _ in range(3):
            engine.step()
        self.assertEqual(p1.remaining_burst, 3)
        self.assertEqual(p2.remaining_burst, 3)

    def test_update_capacity_live(self):
        engine = CloudOSEngine()
        # Initial default capacity is 16 cores, 32GB RAM, 2 GPU, 1000GB storage
        self.assertEqual(engine.capacity.ram_gb, 32)
        
        # Update capacity live
        res = engine.update_capacity(cpu=24, ram_gb=64, gpu=4, storage_gb=2000)
        self.assertTrue(res["ok"])
        self.assertEqual(engine.capacity.cpu, 24)
        self.assertEqual(engine.capacity.ram_gb, 64)
        self.assertEqual(engine.available.ram_gb, 64)

        # Allocate some resources
        engine.add_process("AllocTask", 2, 10, 1, 20, burst_time=5, start_allocated=ResourceVector(2, 10, 1, 20))
        # Cannot reduce capacity below current allocation (10 GB RAM)
        res_fail = engine.update_capacity(cpu=24, ram_gb=5, gpu=4, storage_gb=2000)
        self.assertFalse(res_fail["ok"])
        self.assertIn("RAM cannot be less than currently allocated", res_fail["error"])


if __name__ == "__main__":
    unittest.main()
