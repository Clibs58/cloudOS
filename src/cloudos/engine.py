"""Simulation engine: resource allocation, scheduling, performance metrics, and snapshots."""

from __future__ import annotations

import copy
import io
import csv
import random
from typing import Any, Dict, List, Optional, Tuple

from .banker import can_allocate, detect_deadlock, explain_safety, is_safe
from .config import workload_tuples
from .memory import PagingMemoryManager
from .models import (
    Process,
    ProcessState,
    ResourceVector,
    SchedulerAlgorithm,
    SimulationSnapshot,
    SystemCapacity,
)
from .scheduler import CPUScheduler


class CloudOSEngine:
    def __init__(self, capacity: Optional[SystemCapacity] = None):
        self.capacity = capacity or SystemCapacity()
        self.available = self.capacity.to_vector()
        self.processes: List[Process] = []
        self._next_pid = 1
        self.tick = 0
        self.scheduler = CPUScheduler(SchedulerAlgorithm.ROUND_ROBIN)
        self._current_pid: Optional[int] = None
        self._running_pids: List[int] = []
        self._slice_used: Dict[int, int] = {}  # pid -> slice_used
        self.log: List[str] = []
        self.demo_workloads: List[tuple] = []
        self.memory_high_threshold = 0.75
        self.memory_critical_threshold = 0.9
        self.default_scheduler = "Round Robin"

        # Extended Features
        self.deadlock_avoidance_enabled: bool = True
        self.active_cpu_cores: int = 1
        self.aging_enabled: bool = False
        self.aging_interval: int = 5
        self.io_simulation_enabled: bool = False
        self.gantt_log: List[Dict[str, Any]] = []
        self.history_snapshots: List[Dict[str, Any]] = []
        self.memory_manager = PagingMemoryManager(num_frames=8, policy="LRU")
        self.total_busy_core_ticks: int = 0

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "CloudOSEngine":
        cap = config.get("capacity", {})
        engine = cls(
            SystemCapacity(
                cpu=int(cap.get("cpu", 16)),
                ram_gb=int(cap.get("ram_gb", 32)),
                gpu=int(cap.get("gpu", 2)),
                storage_gb=int(cap.get("storage_gb", 1000)),
            )
        )
        engine.apply_runtime_config(config, reset_simulation=False)
        return engine

    def apply_runtime_config(self, config: Dict[str, Any], reset_simulation: bool = True) -> None:
        cap = config.get("capacity", {})
        self.capacity = SystemCapacity(
            cpu=int(cap.get("cpu", self.capacity.cpu)),
            ram_gb=int(cap.get("ram_gb", self.capacity.ram_gb)),
            gpu=int(cap.get("gpu", self.capacity.gpu)),
            storage_gb=int(cap.get("storage_gb", self.capacity.storage_gb)),
        )

        sched = config.get("scheduler", {})
        quantum = int(sched.get("round_robin_quantum", self.scheduler.quantum))
        self.scheduler.quantum = max(1, quantum)
        self.default_scheduler = str(sched.get("default_algorithm", self.default_scheduler))

        mem = config.get("memory", {})
        self.memory_high_threshold = float(mem.get("high_threshold", self.memory_high_threshold))
        self.memory_critical_threshold = float(
            mem.get("critical_threshold", self.memory_critical_threshold)
        )

        demo = config.get("demo", {})
        workloads = demo.get("workloads", [])
        self.demo_workloads = workload_tuples(workloads) if workloads else []

        if reset_simulation:
            self.reset()
            self.set_scheduler(self.default_scheduler)

    def reset(self) -> None:
        self.available = self.capacity.to_vector()
        self.processes.clear()
        self._next_pid = 1
        self.tick = 0
        self._current_pid = None
        self._running_pids.clear()
        self._slice_used.clear()
        self.log.clear()
        self.gantt_log.clear()
        self.history_snapshots.clear()
        self.memory_manager.reset()
        self.total_busy_core_ticks = 0

    def set_scheduler(self, name: str, quantum: Optional[int] = None) -> None:
        mapping = {
            "FCFS": SchedulerAlgorithm.FCFS,
            "Round Robin": SchedulerAlgorithm.ROUND_ROBIN,
            "Priority": SchedulerAlgorithm.PRIORITY,
            "Priority (Preemptive)": SchedulerAlgorithm.PRIORITY_PREEMPTIVE,
            "SJF": SchedulerAlgorithm.SJF,
            "SRTF": SchedulerAlgorithm.SRTF,
        }
        alg = mapping.get(name, SchedulerAlgorithm.ROUND_ROBIN)
        self.scheduler.set_algorithm(alg)
        if quantum is not None and int(quantum) > 0:
            self.scheduler.set_quantum(int(quantum))
        self._append_log(f"CPU scheduler set to {alg.value} (quantum={self.scheduler.quantum})")

    def set_quantum(self, quantum: int) -> None:
        self.scheduler.set_quantum(quantum)
        self._append_log(f"Round Robin quantum set to {self.scheduler.quantum} ticks")

    def update_capacity(
        self,
        cpu: int,
        ram_gb: int,
        gpu: int,
        storage_gb: int,
        high_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update system capacity dynamically while respecting currently allocated workloads."""
        allocated_total = ResourceVector()
        for p in self.processes:
            if p.state != ProcessState.TERMINATED:
                allocated_total = allocated_total + p.allocated

        if cpu < allocated_total.cpu:
            return {"ok": False, "error": f"CPU cannot be less than currently allocated ({allocated_total.cpu} cores)"}
        if ram_gb < allocated_total.ram_gb:
            return {"ok": False, "error": f"RAM cannot be less than currently allocated ({allocated_total.ram_gb} GB)"}
        if gpu < allocated_total.gpu:
            return {"ok": False, "error": f"GPU cannot be less than currently allocated ({allocated_total.gpu} units)"}
        if storage_gb < allocated_total.storage_gb:
            return {"ok": False, "error": f"Storage cannot be less than currently allocated ({allocated_total.storage_gb} GB)"}

        self.capacity = SystemCapacity(cpu=int(cpu), ram_gb=int(ram_gb), gpu=int(gpu), storage_gb=int(storage_gb))
        self.available = self.capacity.to_vector() - allocated_total

        if high_threshold is not None:
            self.memory_high_threshold = float(high_threshold)
        if critical_threshold is not None:
            self.memory_critical_threshold = float(critical_threshold)

        self._append_log(f"System capacity updated to [CPU: {cpu}, RAM: {ram_gb}GB, GPU: {gpu}, Storage: {storage_gb}GB]")
        self._try_allocate_all()
        return {"ok": True}


    def set_deadlock_avoidance(self, enabled: bool) -> None:
        self.deadlock_avoidance_enabled = enabled
        status = "ENABLED (Banker's Algorithm active)" if enabled else "DISABLED (Greedy allocation / Deadlock mode)"
        self._append_log(f"Deadlock Avoidance {status}")
        self._try_allocate_all()

    def set_active_cores(self, cores: int) -> None:
        self.active_cpu_cores = max(1, min(cores, self.capacity.cpu))
        self._append_log(f"Active CPU cores set to {self.active_cpu_cores}")

    def set_aging(self, enabled: bool, interval: int = 5) -> None:
        self.aging_enabled = enabled
        self.aging_interval = max(1, interval)
        self._append_log(f"Starvation aging {'ENABLED' if enabled else 'DISABLED'} (interval: {self.aging_interval} ticks)")

    def add_process(
        self,
        name: str,
        cpu: int,
        ram_gb: int,
        gpu: int,
        storage_gb: int,
        burst_time: int = 10,
        priority: int = 5,
        start_allocated: Optional[ResourceVector] = None,
    ) -> Dict[str, Any]:
        max_need = ResourceVector(cpu, ram_gb, gpu, storage_gb)
        if not max_need.le(self.capacity.to_vector()):
            return {"ok": False, "error": "Process demand exceeds system capacity"}

        alloc = start_allocated.copy() if start_allocated else ResourceVector()
        # Pages for virtual memory paging (1 page per 4 GB of RAM, minimum 1 page)
        num_pages = max(1, (ram_gb + 3) // 4)
        pages = list(range(num_pages))

        p = Process(
            pid=self._next_pid,
            name=name,
            max_need=max_need,
            allocated=alloc,
            burst_time=burst_time,
            remaining_burst=burst_time,
            priority=priority,
            base_priority=priority,
            state=ProcessState.WAITING,
            arrival_tick=self.tick,
            pages=pages,
            wait_reason="resources",
        )
        self._next_pid += 1
        self.processes.append(p)
        self._try_allocate_all()
        self._append_log(f"Admitted process {p.name} (PID {p.pid}, Priority {p.priority}, Burst {p.burst_time})")
        return {"ok": True, "pid": p.pid}

    def request_resources(
        self,
        pid: int,
        cpu: int = 0,
        ram_gb: int = 0,
        gpu: int = 0,
        storage_gb: int = 0,
    ) -> Dict[str, Any]:
        """Allow a process to request resources incrementally for Banker's test."""
        p = next((x for x in self.processes if x.pid == pid), None)
        if not p:
            return {"ok": False, "error": f"Process PID {pid} not found"}

        req = ResourceVector(cpu, ram_gb, gpu, storage_gb)
        need = p.need()

        if not req.le(need):
            return {"ok": False, "error": f"Request exceeds remaining need: request {req.as_list()} > need {need.as_list()}"}

        if not req.le(self.available):
            return {"ok": False, "error": f"Insufficient available resources: needed {req.as_list()}, available {self.available.as_list()}"}

        if self.deadlock_avoidance_enabled:
            if not can_allocate(p, req, self.available, self.processes):
                self._append_log(f"Banker's REFUSED request from {p.name} (+{req.as_list()}): Unsafe state!")
                return {
                    "ok": False,
                    "error": "Banker's algorithm rejected request: would result in an UNSAFE state with no guaranteed completion sequence.",
                }

        # Grant allocation
        p.allocated = p.allocated + req
        self.available = self.available - req
        self._append_log(f"Granted resource request to {p.name}: +{req.as_list()} (Available: {self.available.as_list()})")

        # Check if process is now ready to run (has at least 1 CPU core allocated)
        if p.allocated.cpu > 0 and p.state == ProcessState.WAITING and p.wait_reason == "resources":
            p.state = ProcessState.READY
            p.wait_reason = ""

        return {"ok": True, "pid": p.pid}

    def release_resources(
        self,
        pid: int,
        cpu: int = 0,
        ram_gb: int = 0,
        gpu: int = 0,
        storage_gb: int = 0,
    ) -> Dict[str, Any]:
        """Allow partial or full resource release."""
        p = next((x for x in self.processes if x.pid == pid), None)
        if not p:
            return {"ok": False, "error": f"Process PID {pid} not found"}

        rel = ResourceVector(cpu, ram_gb, gpu, storage_gb)
        if not rel.le(p.allocated):
            return {"ok": False, "error": "Cannot release more resources than currently allocated"}

        p.allocated = p.allocated - rel
        self.available = self.available + rel
        self._append_log(f"Released resources from {p.name}: -{rel.as_list()}")
        self._try_allocate_all()
        return {"ok": True, "pid": p.pid}

    def trigger_io(self, pid: int, duration: int = 3) -> Dict[str, Any]:
        """Transition a process to I/O wait state."""
        p = next((x for x in self.processes if x.pid == pid), None)
        if not p:
            return {"ok": False, "error": f"Process PID {pid} not found"}
        if p.state == ProcessState.TERMINATED:
            return {"ok": False, "error": "Process already terminated"}

        p.state = ProcessState.WAITING
        p.wait_reason = "io"
        p.io_remaining = max(1, duration)
        if p.pid in self._running_pids:
            self._running_pids.remove(p.pid)
        self._current_pid = self._running_pids[0] if self._running_pids else None
        self._append_log(f"Process {p.name} blocked for I/O ({duration} ticks)")
        return {"ok": True, "pid": p.pid}

    def _try_allocate_all(self) -> None:
        """Attempt to allocate resources to waiting processes."""
        for p in self.processes:
            if p.state == ProcessState.TERMINATED:
                continue

            need = p.need()
            # If all need is satisfied
            if need.cpu == 0 and need.ram_gb == 0 and need.gpu == 0 and need.storage_gb == 0:
                if p.allocated.cpu > 0:
                    if p.state == ProcessState.WAITING and p.wait_reason == "resources":
                        p.state = ProcessState.READY
                        p.wait_reason = ""
                continue

            # Check if resources are available
            if not need.le(self.available):
                continue

            if self.deadlock_avoidance_enabled:
                if can_allocate(p, need, self.available, self.processes):
                    p.allocated = p.allocated + need
                    self.available = self.available - need
                    p.state = ProcessState.READY
                    p.wait_reason = ""
                    self._append_log(f"Allocated resources to {p.name} (Banker's safe)")
            else:
                # Greedy allocation without safety check (Deadlock demo mode)
                p.allocated = p.allocated + need
                self.available = self.available - need
                p.state = ProcessState.READY
                p.wait_reason = ""
                self._append_log(f"Allocated resources to {p.name} (Greedy / Unsafe mode)")

    def _save_history(self) -> None:
        """Preserve state clone for Step Back / Undo."""
        if len(self.history_snapshots) >= 50:
            self.history_snapshots.pop(0)

        # Deepcopy key attributes
        state_clone = {
            "tick": self.tick,
            "available": self.available.copy(),
            "processes": [
                Process(
                    pid=p.pid,
                    name=p.name,
                    max_need=p.max_need.copy(),
                    allocated=p.allocated.copy(),
                    burst_time=p.burst_time,
                    remaining_burst=p.remaining_burst,
                    priority=p.priority,
                    state=p.state,
                    arrival_tick=p.arrival_tick,
                    start_tick=p.start_tick,
                    finish_tick=p.finish_tick,
                    waiting_ticks=p.waiting_ticks,
                    executed_ticks=p.executed_ticks,
                    base_priority=p.base_priority,
                    io_remaining=p.io_remaining,
                    wait_reason=p.wait_reason,
                    pages=list(p.pages),
                )
                for p in self.processes
            ],
            "_next_pid": self._next_pid,
            "_running_pids": list(self._running_pids),
            "_current_pid": self._current_pid,
            "_slice_used": dict(self._slice_used),
            "log": list(self.log),
            "gantt_log": [dict(g) for g in self.gantt_log],
            "total_busy_core_ticks": self.total_busy_core_ticks,
            "paging_state": {
                "hits": self.memory_manager.page_hits,
                "faults": self.memory_manager.page_faults,
                "refs": self.memory_manager.total_references,
                "frames": [
                    {
                        "frame_id": f.frame_id,
                        "pid": f.pid,
                        "process_name": f.process_name,
                        "page_num": f.page_num,
                        "loaded_tick": f.loaded_tick,
                        "last_accessed_tick": f.last_accessed_tick,
                    }
                    for f in self.memory_manager.frames
                ],
            },
        }
        self.history_snapshots.append(state_clone)

    def step_back(self) -> Optional[SimulationSnapshot]:
        """Step back one tick in time."""
        if not self.history_snapshots:
            return None

        state = self.history_snapshots.pop()
        self.tick = state["tick"]
        self.available = state["available"]
        self.processes = state["processes"]
        self._next_pid = state["_next_pid"]
        self._running_pids = state["_running_pids"]
        self._current_pid = state["_current_pid"]
        self._slice_used = state["_slice_used"]
        self.log = state["log"]
        self.gantt_log = state["gantt_log"]
        self.total_busy_core_ticks = state["total_busy_core_ticks"]

        p_state = state["paging_state"]
        self.memory_manager.page_hits = p_state["hits"]
        self.memory_manager.page_faults = p_state["faults"]
        self.memory_manager.total_references = p_state["refs"]
        for i, fd in enumerate(p_state["frames"]):
            f = self.memory_manager.frames[i]
            f.pid = fd["pid"]
            f.process_name = fd["process_name"]
            f.page_num = fd["page_num"]
            f.loaded_tick = fd["loaded_tick"]
            f.last_accessed_tick = fd["last_accessed_tick"]

        self._append_log("Stepped back 1 tick")
        return self.snapshot()

    def step(self) -> SimulationSnapshot:
        self._save_history()
        self.tick += 1

        # 1. Update I/O waiting processes
        self._update_io_states()

        # 2. Update ready process waiting time & apply Aging if enabled
        self._update_ready_and_aging()

        # 3. Schedule CPU cores
        self._run_cpu_cycle()

        # 4. Attempt resource allocation
        self._try_allocate_all()

        # 5. Clean up finished processes
        self._release_finished()

        # 6. Check for Deadlock
        self._check_deadlock()

        return self.snapshot()

    def run_ticks(self, n: int) -> List[SimulationSnapshot]:
        snaps = []
        for _ in range(max(0, n)):
            snaps.append(self.step())
        return snaps

    def _update_io_states(self) -> None:
        for p in self.processes:
            if p.state == ProcessState.WAITING and p.wait_reason == "io":
                p.io_remaining -= 1
                if p.io_remaining <= 0:
                    p.state = ProcessState.READY
                    p.wait_reason = ""
                    self._append_log(f"Process {p.name} finished I/O and moved to READY queue")

    def _update_ready_and_aging(self) -> None:
        ready_candidates = [
            p for p in self.processes
            if p.state in (ProcessState.READY, ProcessState.RUNNING)
            and p.remaining_burst > 0
            and p.allocated.cpu > 0
        ]
        for p in ready_candidates:
            # If not currently executing, it is waiting
            if p.pid not in self._running_pids:
                p.waiting_ticks += 1
                # Aging logic
                if self.aging_enabled and p.waiting_ticks > 0 and (p.waiting_ticks % self.aging_interval == 0):
                    if p.priority > 1:
                        p.priority -= 1
                        self._append_log(f"[Aging] {p.name} (PID {p.pid}) priority boosted to {p.priority} (waited {p.waiting_ticks} ticks)")

    def _ready_processes(self) -> List[Process]:
        return [
            p
            for p in self.processes
            if p.state in (ProcessState.READY, ProcessState.RUNNING)
            and p.remaining_burst > 0
            and p.allocated.cpu > 0
            and p.wait_reason != "io"
        ]

    def _run_cpu_cycle(self) -> None:
        ready = self._ready_processes()
        cores = self.active_cpu_cores
        currently_running = [p for p in self.processes if p.pid in self._running_pids and p in ready]

        # Handle Preemption
        still_running = []
        for p in currently_running:
            slice_used = self._slice_used.get(p.pid, 0)
            if self.scheduler.should_preempt(p, self.tick, slice_used, ready):
                p.state = ProcessState.READY
                self._slice_used[p.pid] = 0
                self._append_log(f"Preempted {p.name} under {self.scheduler.algorithm.value}")
            else:
                still_running.append(p)

        # Refresh ready pool after preemption
        ready = self._ready_processes()

        # Dispatch up to `cores` processes
        chosen = self.scheduler.pick_next_n(ready, still_running, self.tick, cores)

        self._running_pids = [p.pid for p in chosen]
        self._current_pid = self._running_pids[0] if self._running_pids else None

        # Update states
        for p in self.processes:
            if p.state == ProcessState.TERMINATED:
                continue
            if p.pid in self._running_pids:
                p.state = ProcessState.RUNNING
                if p.start_tick is None:
                    p.start_tick = self.tick
            elif p.state == ProcessState.RUNNING:
                p.state = ProcessState.READY

        # Execute running processes on CPU cores
        for core_idx in range(cores):
            if core_idx < len(chosen):
                p = chosen[core_idx]
                p.remaining_burst -= 1
                p.executed_ticks += 1
                self.total_busy_core_ticks += 1
                self._slice_used[p.pid] = self._slice_used.get(p.pid, 0) + 1

                # Simulate Memory Page Access
                if p.pages:
                    # Access virtual page cyclically or randomly
                    page_idx = (p.executed_ticks % len(p.pages))
                    page_res = self.memory_manager.access_page(p.pid, p.name, p.pages[page_idx], self.tick)
                    if not page_res["hit"] and page_res.get("evicted"):
                        self._append_log(f"[Paging] {page_res['msg']}")

                # Log to Gantt chart
                self.gantt_log.append({
                    "tick": self.tick,
                    "core": core_idx,
                    "pid": p.pid,
                    "name": p.name,
                })

                # Process completion check
                if p.remaining_burst <= 0:
                    p.finish_tick = self.tick
                    p.state = ProcessState.TERMINATED
                    self._release_process_resources(p)
                    self._slice_used.pop(p.pid, None)
                    if p.pid in self._running_pids:
                        self._running_pids.remove(p.pid)
                    self._append_log(f"Process {p.name} completed at t={self.tick}! (Turnaround: {p.turnaround_time(self.tick)}, Waiting: {p.waiting_ticks})")
            else:
                # Core was idle
                self.gantt_log.append({
                    "tick": self.tick,
                    "core": core_idx,
                    "pid": None,
                    "name": "IDLE",
                })

        # Cap Gantt log length to avoid unbounded memory
        if len(self.gantt_log) > 200:
            self.gantt_log = self.gantt_log[-200:]

    def _release_process_resources(self, p: Process) -> None:
        self.available = self.available + p.allocated
        p.allocated = ResourceVector()
        self.memory_manager.release_process_pages(p.pid)
        self._append_log(f"Released all resources and memory frames of {p.name}")

    def _release_finished(self) -> None:
        for p in self.processes:
            if p.state == ProcessState.TERMINATED and (
                p.allocated.cpu or p.allocated.ram_gb or p.allocated.gpu or p.allocated.storage_gb
            ):
                self._release_process_resources(p)

    def _check_deadlock(self) -> Tuple[bool, List[int], str]:
        if self.deadlock_avoidance_enabled:
            return False, [], "Banker's avoidance is active"
        is_dl, pids, msg = detect_deadlock(self.processes, self.available)
        if is_dl:
            self._append_log(f"CRITICAL: {msg}")
        return is_dl, pids, msg

    def _memory_status(self) -> str:
        used_ram = sum(p.allocated.ram_gb for p in self.processes if p.state != ProcessState.TERMINATED)
        ratio = used_ram / max(1, self.capacity.ram_gb)
        if ratio >= self.memory_critical_threshold:
            return "CRITICAL"
        if ratio >= self.memory_high_threshold:
            return "HIGH"
        return "NORMAL"

    def _append_log(self, msg: str) -> None:
        self.log.append(f"[t={self.tick}] {msg}")
        if len(self.log) > 60:
            self.log = self.log[-60:]

    def calculate_metrics(self) -> Dict[str, Any]:
        """Compute comprehensive performance metrics for compare view and dashboard."""
        all_procs = self.processes
        completed = [p for p in all_procs if p.state == ProcessState.TERMINATED]
        started = [p for p in all_procs if p.start_tick is not None]

        # Waiting time
        avg_wait = round(sum(p.waiting_ticks for p in all_procs) / max(1, len(all_procs)), 2) if all_procs else 0.0

        # Turnaround time (for completed)
        avg_turnaround = round(
            sum(p.turnaround_time(self.tick) for p in completed) / max(1, len(completed)), 2
        ) if completed else 0.0

        # Response time (for started)
        resp_times = [p.response_time() for p in started if p.response_time() is not None]
        avg_response = round(sum(resp_times) / max(1, len(resp_times)), 2) if resp_times else 0.0

        # CPU utilization
        total_slots = max(1, self.tick * self.active_cpu_cores)
        cpu_util = round(min(100.0, (self.total_busy_core_ticks / total_slots) * 100), 1) if self.tick > 0 else 0.0

        # Throughput
        throughput = round(len(completed) / max(1, self.tick), 4)

        return {
            "avg_waiting_time": avg_wait,
            "avg_turnaround_time": avg_turnaround,
            "avg_response_time": avg_response,
            "cpu_utilization": cpu_util,
            "throughput": throughput,
            "completed_count": len(completed),
            "total_count": len(all_procs),
        }

    def explain_banker_safety(self) -> Dict[str, Any]:
        active = [p for p in self.processes if p.state != ProcessState.TERMINATED]
        return explain_safety(active, self.available)

    def snapshot(self) -> SimulationSnapshot:
        allocated_total = ResourceVector()
        for p in self.processes:
            if p.state != ProcessState.TERMINATED:
                allocated_total = allocated_total + p.allocated

        active = [p for p in self.processes if p.state != ProcessState.TERMINATED]
        safe, safe_seq = is_safe(active, self.available) if active else (True, [])
        safe_names = []
        if safe_seq:
            pid_to_name = {p.pid: p.name for p in self.processes}
            safe_names = [pid_to_name.get(pid, f"P{pid}") for pid in safe_seq]

        is_dl, dl_pids, _ = self._check_deadlock()

        proc_rows = []
        for p in self.processes:
            proc_rows.append(
                {
                    "pid": p.pid,
                    "name": p.name,
                    "cpu": p.allocated.cpu,
                    "ram_gb": p.allocated.ram_gb,
                    "gpu": p.allocated.gpu,
                    "storage_gb": p.allocated.storage_gb,
                    "max_cpu": p.max_need.cpu,
                    "max_ram_gb": p.max_need.ram_gb,
                    "max_gpu": p.max_need.gpu,
                    "max_storage_gb": p.max_need.storage_gb,
                    "status": p.state.value,
                    "wait_reason": p.wait_reason,
                    "burst_time": p.burst_time,
                    "remaining_burst": p.remaining_burst,
                    "priority": p.priority,
                    "base_priority": p.base_priority,
                    "arrival_tick": p.arrival_tick,
                    "start_tick": p.start_tick,
                    "finish_tick": p.finish_tick,
                    "waiting_ticks": p.waiting_ticks,
                    "turnaround_time": p.turnaround_time(self.tick),
                    "response_time": p.response_time(),
                    "io_remaining": p.io_remaining,
                }
            )

        metrics = self.calculate_metrics()
        paging = self.memory_manager.snapshot()

        return SimulationSnapshot(
            tick=self.tick,
            capacity=self.capacity,
            available=self.available,
            allocated_total=allocated_total,
            processes=proc_rows,
            scheduler=self.scheduler.algorithm.value,
            deadlock_safe=safe,
            memory_status=self._memory_status(),
            log=list(self.log),
            safe_sequence=safe_seq,
            safe_sequence_names=safe_names,
            deadlock_detected=is_dl,
            deadlocked_pids=dl_pids,
            deadlock_avoidance=self.deadlock_avoidance_enabled,
            metrics=metrics,
            gantt=list(self.gantt_log),
            active_cores=self.active_cpu_cores,
            aging_enabled=self.aging_enabled,
            paging_stats=paging,
            memory_frames=paging["frames"],
            quantum=self.scheduler.quantum,
        )


    def load_demo(self) -> None:
        self.reset()
        demos = self.demo_workloads
        if not demos:
            self.set_scheduler(self.default_scheduler)
            return
        for row in demos:
            self.add_process(*row)
        self.set_scheduler(self.default_scheduler)

    def load_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Load curated educational scenarios demonstrating OS concepts."""
        self.reset()

        if scenario_name == "deadlock_trap":
            # Scenario: Two processes competing cyclically for CPU and GPU
            # System has 1 GPU, 8 CPU, fully allocated between P1 and P2
            self.capacity = SystemCapacity(cpu=8, ram_gb=16, gpu=1, storage_gb=500)
            self.available = self.capacity.to_vector()
            # Process 1: holds 5 CPU, needs 1 GPU
            p1_max = ResourceVector(5, 8, 1, 100)
            p1_alloc = ResourceVector(5, 8, 0, 100)
            # Process 2: holds 1 GPU and 3 CPU, needs 1 more CPU
            p2_max = ResourceVector(4, 8, 1, 100)
            p2_alloc = ResourceVector(3, 8, 1, 100)

            # Deduct initial allocations so available has 0 CPU and 0 GPU
            self.available = self.available - (p1_alloc + p2_alloc)

            p1 = Process(
                pid=1,
                name="P1 (Worker A)",
                max_need=p1_max,
                allocated=p1_alloc,
                burst_time=12,
                remaining_burst=12,
                priority=2,
                state=ProcessState.WAITING,
                wait_reason="resources",
            )
            p2 = Process(
                pid=2,
                name="P2 (Worker B)",
                max_need=p2_max,
                allocated=p2_alloc,
                burst_time=12,
                remaining_burst=12,
                priority=2,
                state=ProcessState.WAITING,
                wait_reason="resources",
            )
            self.processes = [p1, p2]
            self._next_pid = 3
            self._append_log("Loaded Deadlock Trap scenario: P1 holds 5 CPU (needs GPU), P2 holds GPU & 3 CPU (needs CPU). Available: 0 CPU, 0 GPU.")


        elif scenario_name == "overloaded":
            self.capacity = SystemCapacity(cpu=8, ram_gb=16, gpu=1, storage_gb=500)
            self.available = self.capacity.to_vector()
            workloads = [
                ("Batch Job A", 4, 8, 1, 100, 15, 3),
                ("Batch Job B", 4, 8, 1, 100, 15, 3),
                ("Stream Processing", 4, 6, 0, 50, 10, 2),
                ("Web Analytics", 2, 4, 0, 50, 8, 4),
            ]
            for w in workloads:
                self.add_process(*w)
            self._append_log("Loaded Overloaded System scenario: high demand on RAM and GPU.")

        elif scenario_name == "gpu_contention":
            self.capacity = SystemCapacity(cpu=16, ram_gb=32, gpu=2, storage_gb=1000)
            self.available = self.capacity.to_vector()
            workloads = [
                ("Deep Learning Train", 6, 12, 1, 200, 20, 2),
                ("LLM Fine-tuning", 6, 12, 1, 200, 25, 1),
                ("Computer Vision Eval", 4, 8, 1, 100, 12, 3),
            ]
            for w in workloads:
                self.add_process(*w)
            self._append_log("Loaded GPU Contention scenario: 3 workloads competing for 2 GPUs.")

        elif scenario_name == "convoy_effect":
            # Demonstrates FCFS Convoy Effect vs SJF/Round Robin
            self.capacity = SystemCapacity(cpu=8, ram_gb=16, gpu=1, storage_gb=500)
            self.available = self.capacity.to_vector()
            self.set_scheduler("FCFS")
            workloads = [
                ("Huge Monolith Job", 2, 4, 0, 50, 30, 3),
                ("Quick API Ping 1", 2, 2, 0, 20, 2, 3),
                ("Quick API Ping 2", 2, 2, 0, 20, 2, 3),
                ("Quick API Ping 3", 2, 2, 0, 20, 2, 3),
            ]
            for w in workloads:
                self.add_process(*w)
            self._append_log("Loaded Convoy Effect scenario: 30-tick giant job ahead of three 2-tick tiny jobs.")

        elif scenario_name == "priority_starvation":
            # Demonstrates Priority Starvation and Aging
            self.capacity = SystemCapacity(cpu=8, ram_gb=16, gpu=1, storage_gb=500)
            self.available = self.capacity.to_vector()
            self.set_scheduler("Priority")
            workloads = [
                ("Starved Batch Task", 2, 4, 0, 50, 25, 9),  # low priority
                ("VIP Task 1", 2, 2, 0, 20, 6, 1),
                ("VIP Task 2", 2, 2, 0, 20, 6, 1),
                ("VIP Task 3", 2, 2, 0, 20, 6, 1),
            ]
            for w in workloads:
                self.add_process(*w)
            self._append_log("Loaded Priority Starvation scenario: Low priority (9) batch job starved by VIP tasks (1).")

        elif scenario_name == "priority_inversion":
            # Demonstrates classic Priority Inversion
            self.capacity = SystemCapacity(cpu=8, ram_gb=16, gpu=1, storage_gb=500)
            self.available = self.capacity.to_vector()
            self.set_scheduler("Priority (Preemptive)")
            # Low priority task acquires GPU
            p_low_alloc = ResourceVector(2, 4, 1, 50)
            self.available = self.available - p_low_alloc
            p_low = Process(
                pid=1,
                name="P_Low (holds GPU)",
                max_need=ResourceVector(2, 4, 1, 50),
                allocated=p_low_alloc,
                burst_time=15,
                remaining_burst=15,
                priority=8,
                state=ProcessState.READY,
            )
            # Med priority task uses CPU only
            p_med = Process(
                pid=2,
                name="P_Med (CPU bound)",
                max_need=ResourceVector(2, 4, 0, 50),
                allocated=ResourceVector(2, 4, 0, 50),
                burst_time=15,
                remaining_burst=15,
                priority=4,
                state=ProcessState.READY,
            )
            self.available = self.available - ResourceVector(2, 4, 0, 50)
            # High priority task needs GPU
            p_high = Process(
                pid=3,
                name="P_High (needs GPU)",
                max_need=ResourceVector(2, 4, 1, 50),
                allocated=ResourceVector(0, 0, 0, 0),
                burst_time=8,
                remaining_burst=8,
                priority=1,
                state=ProcessState.WAITING,
                wait_reason="resources",
            )
            self.processes = [p_low, p_med, p_high]
            self._next_pid = 4
            self._append_log("Loaded Priority Inversion scenario: P_High waits for GPU held by P_Low, but P_Med preempts P_Low!")

        else:
            self.load_demo()

        return {"ok": True, "scenario": scenario_name}

    def generate_random_workload(self, count: int = 4) -> None:
        """Generate N random realistic cloud workloads."""
        self.reset()
        names = ["Auth Service", "Worker Queue", "Image Resizer", "ETL Pipeline", "Search Indexer", "Push Gateway", "Metrics Collector"]
        selected_names = random.sample(names, min(count, len(names)))

        for name in selected_names:
            cpu = random.randint(1, 4)
            ram = random.choice([2, 4, 8, 12])
            gpu = random.choice([0, 0, 0, 1])
            storage = random.randint(20, 150)
            burst = random.randint(5, 20)
            prio = random.randint(1, 7)
            self.add_process(name, cpu, ram, gpu, storage, burst, prio)

        self._append_log(f"Generated {len(selected_names)} random workloads")

    def compare_all_schedulers(self) -> Dict[str, Any]:
        """
        Run the exact current workload under all 6 scheduling algorithms in isolated clones,
        and return a complete side-by-side performance comparison.
        """
        algorithms = [
            ("FCFS", "FCFS"),
            ("Round Robin", "Round Robin"),
            ("Priority", "Priority (Non-Preemptive)"),
            ("Priority (Preemptive)", "Preemptive Priority"),
            ("SJF", "Shortest Job First"),
            ("SRTF", "Shortest Remaining Time First"),
        ]

        # Extract current workload definitions
        workload_defs = [
            {
                "name": p.name,
                "cpu": p.max_need.cpu,
                "ram_gb": p.max_need.ram_gb,
                "gpu": p.max_need.gpu,
                "storage_gb": p.max_need.storage_gb,
                "burst_time": p.burst_time,
                "priority": p.base_priority,
            }
            for p in self.processes
        ]

        if not workload_defs:
            return {"ok": False, "error": "No workloads available to compare"}

        results = []
        max_simulation_ticks = 200

        for alg_key, alg_label in algorithms:
            sim = CloudOSEngine(capacity=self.capacity.copy() if hasattr(self.capacity, 'copy') else SystemCapacity(
                cpu=self.capacity.cpu,
                ram_gb=self.capacity.ram_gb,
                gpu=self.capacity.gpu,
                storage_gb=self.capacity.storage_gb,
            ))
            sim.deadlock_avoidance_enabled = self.deadlock_avoidance_enabled
            sim.active_cpu_cores = self.active_cpu_cores
            sim.set_scheduler(alg_key)

            for w in workload_defs:
                sim.add_process(
                    name=w["name"],
                    cpu=w["cpu"],
                    ram_gb=w["ram_gb"],
                    gpu=w["gpu"],
                    storage_gb=w["storage_gb"],
                    burst_time=w["burst_time"],
                    priority=w["priority"],
                )

            # Step until all processes terminate or max ticks reached
            while sim.tick < max_simulation_ticks:
                active = [p for p in sim.processes if p.state != ProcessState.TERMINATED]
                if not active:
                    break
                sim.step()

            m = sim.calculate_metrics()
            results.append({
                "algorithm": alg_key,
                "label": alg_label,
                "total_ticks": sim.tick,
                "avg_turnaround_time": m["avg_turnaround_time"],
                "avg_waiting_time": m["avg_waiting_time"],
                "avg_response_time": m["avg_response_time"],
                "cpu_utilization": m["cpu_utilization"],
                "throughput": m["throughput"],
                "completed": m["completed_count"],
                "total": m["total_count"],
            })

        # Rank winner based on lowest avg turnaround time
        valid_results = [r for r in results if r["completed"] == r["total"]]
        best = min(valid_results or results, key=lambda r: (r["avg_turnaround_time"], r["avg_waiting_time"]))

        return {
            "ok": True,
            "comparison": results,
            "winner": best["label"],
            "winner_reason": f"{best['label']} achieved the best combination of low turnaround ({best['avg_turnaround_time']} ticks) and low waiting time ({best['avg_waiting_time']} ticks).",
        }

    def export_metrics_csv(self) -> str:
        """Export process metrics as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "PID",
            "Name",
            "Priority",
            "Burst Time",
            "Arrival Tick",
            "Start Tick",
            "Finish Tick",
            "Turnaround Time",
            "Waiting Time",
            "Response Time",
            "Status",
        ])
        for p in self.processes:
            writer.writerow([
                p.pid,
                p.name,
                p.priority,
                p.burst_time,
                p.arrival_tick,
                p.start_tick if p.start_tick is not None else "N/A",
                p.finish_tick if p.finish_tick is not None else "N/A",
                p.turnaround_time(self.tick),
                p.waiting_ticks,
                p.response_time() if p.response_time() is not None else "N/A",
                p.state.value,
            ])
        return output.getvalue()

    def export_gantt_csv(self) -> str:
        """Export Gantt chart timeline log as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Tick", "Core", "PID", "Process Name"])
        for g in self.gantt_log:
            writer.writerow([
                g.get("tick", 0),
                g.get("core", 0),
                g.get("pid") if g.get("pid") is not None else "IDLE",
                g.get("name", "IDLE"),
            ])
        return output.getvalue()
