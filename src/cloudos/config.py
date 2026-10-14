"""Load and persist CloudOS configuration from config.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_CONFIG: Dict[str, Any] = {
    "capacity": {
        "cpu": 16,
        "ram_gb": 32,
        "gpu": 2,
        "storage_gb": 1000,
    },
    "scheduler": {
        "default_algorithm": "Round Robin",
        "round_robin_quantum": 2,
    },
    "memory": {
        "high_threshold": 0.75,
        "critical_threshold": 0.9,
    },
    "demo": {
        "load_on_startup": True,
        "workloads": [
            {
                "name": "Web Server",
                "cpu": 4,
                "ram_gb": 8,
                "gpu": 0,
                "storage_gb": 120,
                "burst_time": 12,
                "priority": 3,
            },
            {
                "name": "ML Training",
                "cpu": 6,
                "ram_gb": 12,
                "gpu": 1,
                "storage_gb": 200,
                "burst_time": 20,
                "priority": 1,
            },
            {
                "name": "Database",
                "cpu": 2,
                "ram_gb": 4,
                "gpu": 0,
                "storage_gb": 150,
                "burst_time": 15,
                "priority": 2,
            },
            {
                "name": "Analytics",
                "cpu": 2,
                "ram_gb": 4,
                "gpu": 0,
                "storage_gb": 150,
                "burst_time": 10,
                "priority": 4,
            },
        ],
    },
}

WORKLOAD_KEYS = (
    "name",
    "cpu",
    "ram_gb",
    "gpu",
    "storage_gb",
    "burst_time",
    "priority",
)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        if self.path.is_file():
            self.load()

    def load(self) -> Dict[str, Any]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config.json root must be an object")
        self._data = _deep_merge(DEFAULT_CONFIG, raw)
        return copy.deepcopy(self._data)

    def get(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        errors = validate_config(data)
        if errors:
            raise ValueError("; ".join(errors))
        merged = _deep_merge(DEFAULT_CONFIG, data)
        self._data = merged
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        return copy.deepcopy(self._data)


def validate_config(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    cap = data.get("capacity", {})
    for key in ("cpu", "ram_gb", "gpu", "storage_gb"):
        val = cap.get(key)
        if not isinstance(val, int) or val < 1:
            errors.append(f"capacity.{key} must be a positive integer")

    sched = data.get("scheduler", {})
    alg = sched.get("default_algorithm", "Round Robin")
    valid_algs = ("FCFS", "Round Robin", "Priority", "Priority (Preemptive)", "SJF", "SRTF")
    if alg not in valid_algs:
        errors.append(f"scheduler.default_algorithm must be one of: {', '.join(valid_algs)}")

    q = sched.get("round_robin_quantum", 2)
    if not isinstance(q, int) or q < 1:
        errors.append("scheduler.round_robin_quantum must be a positive integer")

    mem = data.get("memory", {})
    for key in ("high_threshold", "critical_threshold"):
        val = mem.get(key, 0.75)
        if not isinstance(val, (int, float)) or not (0 < float(val) < 1):
            errors.append(f"memory.{key} must be between 0 and 1")
    high = float(mem.get("high_threshold", 0.75))
    crit = float(mem.get("critical_threshold", 0.9))
    if high >= crit:
        errors.append("memory.high_threshold must be less than critical_threshold")

    demo = data.get("demo", {})
    if "load_on_startup" in demo and not isinstance(demo["load_on_startup"], bool):
        errors.append("demo.load_on_startup must be true or false")

    workloads = demo.get("workloads", [])
    if not isinstance(workloads, list):
        errors.append("demo.workloads must be an array")
    else:
        for i, w in enumerate(workloads):
            if not isinstance(w, dict):
                errors.append(f"demo.workloads[{i}] must be an object")
                continue
            for key in WORKLOAD_KEYS:
                if key not in w:
                    errors.append(f"demo.workloads[{i}] missing '{key}'")
            if "name" in w and not str(w["name"]).strip():
                errors.append(f"demo.workloads[{i}].name must not be empty")
            for num_key in ("cpu", "ram_gb", "gpu", "storage_gb", "burst_time", "priority"):
                if num_key in w and (not isinstance(w[num_key], int) or w[num_key] < 0):
                    errors.append(f"demo.workloads[{i}].{num_key} must be a non-negative integer")
            if "cpu" in w and isinstance(w["cpu"], int) and w["cpu"] < 1:
                errors.append(f"demo.workloads[{i}].cpu must be at least 1")

    return errors


def workload_tuples(workloads: List[Dict[str, Any]]) -> List[Tuple]:
    rows = []
    for w in workloads:
        rows.append(
            (
                str(w["name"]),
                int(w["cpu"]),
                int(w["ram_gb"]),
                int(w["gpu"]),
                int(w["storage_gb"]),
                int(w["burst_time"]),
                int(w["priority"]),
            )
        )
    return rows
