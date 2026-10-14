"""CPU scheduling algorithms (FCFS, Round Robin, Priority)."""

from __future__ import annotations

from typing import List, Optional

from .models import Process, ProcessState, SchedulerAlgorithm


class CPUScheduler:
    def __init__(self, algorithm: SchedulerAlgorithm, quantum: int = 2):
        self.algorithm = algorithm
        self.quantum = quantum
        self._rr_index = 0
        self._fcfs_order: List[int] = []

    def set_algorithm(self, algorithm: SchedulerAlgorithm) -> None:
        self.algorithm = algorithm
        self._rr_index = 0
        self._fcfs_order = []

    def set_quantum(self, quantum: int) -> None:
        self.quantum = max(1, quantum)

    def pick_next(
        self,
        ready: List[Process],
        current: Optional[Process],
        tick: int,
    ) -> Optional[Process]:
        if not ready:
            return None

        if self.algorithm == SchedulerAlgorithm.FCFS:
            ready_sorted = sorted(ready, key=lambda p: (p.arrival_tick, p.pid))
            return ready_sorted[0]

        if self.algorithm in (SchedulerAlgorithm.PRIORITY, SchedulerAlgorithm.PRIORITY_PREEMPTIVE):
            ready_sorted = sorted(ready, key=lambda p: (p.priority, p.arrival_tick, p.pid))
            return ready_sorted[0]

        if self.algorithm == SchedulerAlgorithm.SJF:
            # Non-preemptive: if current is still running and in ready, let it continue
            if current and current in ready and current.remaining_burst > 0:
                return current
            ready_sorted = sorted(ready, key=lambda p: (p.remaining_burst, p.arrival_tick, p.pid))
            return ready_sorted[0]

        if self.algorithm == SchedulerAlgorithm.SRTF:
            # Preemptive shortest remaining time first
            ready_sorted = sorted(ready, key=lambda p: (p.remaining_burst, p.arrival_tick, p.pid))
            return ready_sorted[0]

        # Round Robin: If current has not been preempted yet, continue its quantum slice!
        if current and current in ready and current.remaining_burst > 0:
            return current
        self._rr_index %= len(ready)
        chosen = ready[self._rr_index]
        self._rr_index = (self._rr_index + 1) % len(ready)
        return chosen

    def pick_next_n(
        self,
        ready: List[Process],
        current_running: List[Process],
        tick: int,
        n: int,
    ) -> List[Process]:
        """Pick up to n processes to run on multi-core CPU."""
        if not ready or n <= 0:
            return []

        if n == 1:
            curr = current_running[0] if current_running else None
            p = self.pick_next(ready, curr, tick)
            return [p] if p else []

        if self.algorithm == SchedulerAlgorithm.FCFS:
            ready_sorted = sorted(ready, key=lambda p: (p.arrival_tick, p.pid))
            return ready_sorted[:n]

        if self.algorithm in (SchedulerAlgorithm.PRIORITY, SchedulerAlgorithm.PRIORITY_PREEMPTIVE):
            ready_sorted = sorted(ready, key=lambda p: (p.priority, p.arrival_tick, p.pid))
            return ready_sorted[:n]

        if self.algorithm == SchedulerAlgorithm.SJF:
            running_keep = [p for p in current_running if p in ready and p.remaining_burst > 0]
            remaining_needed = n - len(running_keep)
            other_ready = [p for p in ready if p not in running_keep]
            other_sorted = sorted(other_ready, key=lambda p: (p.remaining_burst, p.arrival_tick, p.pid))
            return (running_keep + other_sorted)[:n]

        if self.algorithm == SchedulerAlgorithm.SRTF:
            ready_sorted = sorted(ready, key=lambda p: (p.remaining_burst, p.arrival_tick, p.pid))
            return ready_sorted[:n]

        # Round Robin multi-core: Keep active slices first, then allocate remaining cores in cyclic order
        running_keep = [p for p in current_running if p in ready and p.remaining_burst > 0]
        needed = n - len(running_keep)
        chosen = list(running_keep)
        if needed > 0:
            other_ready = [p for p in ready if p not in chosen]
            for _ in range(min(needed, len(other_ready))):
                if not other_ready:
                    break
                idx = self._rr_index % len(other_ready)
                chosen.append(other_ready.pop(idx))
                self._rr_index = (self._rr_index + 1) % max(1, len(ready))
        return chosen


    def should_preempt(
        self,
        current: Optional[Process],
        tick: int,
        slice_used: int,
        ready: Optional[List[Process]] = None,
    ) -> bool:
        if not current:
            return False

        if self.algorithm == SchedulerAlgorithm.ROUND_ROBIN:
            return slice_used >= self.quantum

        if self.algorithm == SchedulerAlgorithm.PRIORITY_PREEMPTIVE:
            if ready:
                # Preempt if any waiting ready process has strictly higher priority (lower priority number)
                return any(p.pid != current.pid and p.priority < current.priority for p in ready)
            return False

        if self.algorithm == SchedulerAlgorithm.SRTF:
            if ready:
                # Preempt if any waiting ready process has strictly shorter remaining burst
                return any(p.pid != current.pid and p.remaining_burst < current.remaining_burst for p in ready)
            return False

        return False

