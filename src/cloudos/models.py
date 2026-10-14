from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ProcessState(str, Enum):
    RUNNING = "RUNNING"
    READY = "READY"
    WAITING = "WAITING"
    TERMINATED = "TERMINATED"


class SchedulerAlgorithm(str, Enum):
    FCFS = "FCFS"
    ROUND_ROBIN = "Round Robin"
    PRIORITY = "Priority"
    PRIORITY_PREEMPTIVE = "Priority (Preemptive)"
    SJF = "SJF"
    SRTF = "SRTF"


@dataclass
class ResourceVector:
    cpu: int = 0
    ram_gb: int = 0
    gpu: int = 0
    storage_gb: int = 0

    def as_list(self) -> List[int]:
        return [self.cpu, self.ram_gb, self.gpu, self.storage_gb]

    def __add__(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            self.cpu + other.cpu,
            self.ram_gb + other.ram_gb,
            self.gpu + other.gpu,
            self.storage_gb + other.storage_gb,
        )

    def __sub__(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            self.cpu - other.cpu,
            self.ram_gb - other.ram_gb,
            self.gpu - other.gpu,
            self.storage_gb - other.storage_gb,
        )

    def le(self, other: ResourceVector) -> bool:
        return all(a <= b for a, b in zip(self.as_list(), other.as_list()))

    def copy(self) -> ResourceVector:
        return ResourceVector(self.cpu, self.ram_gb, self.gpu, self.storage_gb)


@dataclass
class SystemCapacity:
    cpu: int = 16
    ram_gb: int = 32
    gpu: int = 2
    storage_gb: int = 1000

    def to_vector(self) -> ResourceVector:
        return ResourceVector(self.cpu, self.ram_gb, self.gpu, self.storage_gb)


@dataclass
class Process:
    pid: int
    name: str
    max_need: ResourceVector
    allocated: ResourceVector = field(default_factory=ResourceVector)
    burst_time: int = 10
    remaining_burst: int = 10
    priority: int = 5
    state: ProcessState = ProcessState.WAITING
    arrival_tick: int = 0
    start_tick: Optional[int] = None
    finish_tick: Optional[int] = None
    waiting_ticks: int = 0
    executed_ticks: int = 0
    base_priority: int = 5
    io_remaining: int = 0
    wait_reason: str = "resources"
    pages: List[int] = field(default_factory=list)

    def __post_init__(self):
        if self.base_priority is None or self.base_priority == 5 and self.priority != 5:
            self.base_priority = self.priority

    def need(self) -> ResourceVector:
        return ResourceVector(
            max(0, self.max_need.cpu - self.allocated.cpu),
            max(0, self.max_need.ram_gb - self.allocated.ram_gb),
            max(0, self.max_need.gpu - self.allocated.gpu),
            max(0, self.max_need.storage_gb - self.allocated.storage_gb),
        )

    def response_time(self) -> Optional[int]:
        if self.start_tick is not None:
            return max(0, self.start_tick - self.arrival_tick)
        return None

    def turnaround_time(self, current_tick: int) -> int:
        if self.finish_tick is not None:
            return max(0, self.finish_tick - self.arrival_tick)
        return max(0, current_tick - self.arrival_tick)


@dataclass
class SimulationSnapshot:
    tick: int
    capacity: SystemCapacity
    available: ResourceVector
    allocated_total: ResourceVector
    processes: List[Dict]
    scheduler: str
    deadlock_safe: bool
    memory_status: str
    log: List[str]
    safe_sequence: List[int] = field(default_factory=list)
    safe_sequence_names: List[str] = field(default_factory=list)
    deadlock_detected: bool = False
    deadlocked_pids: List[int] = field(default_factory=list)
    deadlock_avoidance: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)
    gantt: List[Dict[str, Any]] = field(default_factory=list)
    active_cores: int = 1
    aging_enabled: bool = False
    paging_stats: Dict[str, Any] = field(default_factory=dict)
    memory_frames: List[Dict[str, Any]] = field(default_factory=list)
    quantum: int = 2


