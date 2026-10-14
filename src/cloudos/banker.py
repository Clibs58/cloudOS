"""Banker's algorithm for multi-resource deadlock avoidance."""

from __future__ import annotations

from typing import List, Tuple

from .models import Process, ProcessState, ResourceVector



def is_safe(
    processes: List[Process],
    available: ResourceVector,
) -> Tuple[bool, List[int]]:
    """
    Return (is_safe, safe_sequence) using Banker's algorithm.
    Only considers processes that have been allocated at least one resource
    or are fully waiting for initial allocation.
    """
    n = len(processes)
    if n == 0:
        return True, []

    work = available.copy()
    finish = [False] * n
    safe_seq: List[int] = []

    for _ in range(n):
        found = False
        for i, p in enumerate(processes):
            if finish[i]:
                continue
            need = p.need()
            if need.le(work):
                work = work + p.allocated
                finish[i] = True
                safe_seq.append(p.pid)
                found = True
                break
        if not found:
            return False, []

    return True, safe_seq


def can_allocate(
    process: Process,
    request: ResourceVector,
    available: ResourceVector,
    processes: List[Process],
) -> bool:
    """Check request against need and available, then simulate safety."""
    need = process.need()
    if not request.le(need):
        return False
    if not request.le(available):
        return False

    # Try allocation
    process.allocated = process.allocated + request
    new_available = available - request

    safe, _ = is_safe(processes, new_available)

    # Roll back
    process.allocated = process.allocated - request

    return safe


def explain_safety(
    processes: List[Process],
    available: ResourceVector,
) -> dict:
    """
    Compute Banker's safety with full step-by-step audit for educational display.
    """
    n = len(processes)
    if n == 0:
        return {
            "is_safe": True,
            "safe_sequence": [],
            "safe_sequence_names": [],
            "steps": [],
            "reason": "No active processes in system.",
            "initial_available": available.as_list(),
        }

    work = available.copy()
    finish = [False] * n
    safe_seq: List[int] = []
    safe_names: List[str] = []
    steps = []

    for step_num in range(1, n + 1):
        found = False
        for i, p in enumerate(processes):
            if finish[i]:
                continue
            need = p.need()
            if need.le(work):
                work_before = work.copy()
                work = work + p.allocated
                finish[i] = True
                safe_seq.append(p.pid)
                safe_names.append(p.name)
                found = True
                steps.append({
                    "step": step_num,
                    "pid": p.pid,
                    "name": p.name,
                    "work_before": work_before.as_list(),
                    "need": need.as_list(),
                    "allocated": p.allocated.as_list(),
                    "work_after": work.as_list(),
                })
                break
        if not found:
            unfinished = [p.name for i, p in enumerate(processes) if not finish[i]]
            return {
                "is_safe": False,
                "safe_sequence": [],
                "safe_sequence_names": [],
                "steps": steps,
                "reason": f"Deadlock avoidance: cannot find safe path for {', '.join(unfinished)}. Available resources insufficient.",
                "initial_available": available.as_list(),
            }

    return {
        "is_safe": True,
        "safe_sequence": safe_seq,
        "safe_sequence_names": safe_names,
        "steps": steps,
        "reason": f"Safe sequence found: {' -> '.join(safe_names)}.",
        "initial_available": available.as_list(),
    }


def detect_deadlock(
    processes: List[Process],
    available: ResourceVector,
) -> Tuple[bool, List[int], str]:
    """
    Detect if an actual resource deadlock exists:
    Processes holding resources are waiting for additional resources,
    available resources cannot satisfy ANY waiting process,
    and no process is currently RUNNING or READY to release resources.
    """
    waiting = [p for p in processes if p.state == ProcessState.WAITING and p.need().as_list() != [0, 0, 0, 0]]
    if len(waiting) < 2:
        return False, [], "No deadlock"

    ready_or_running = [p for p in processes if p.state in (ProcessState.RUNNING, ProcessState.READY) and p.remaining_burst > 0]
    if ready_or_running:
        return False, [], "Active processes are making progress"

    # Check if any waiting process can be satisfied with current available
    can_any_run = any(p.need().le(available) for p in waiting)
    if not can_any_run:
        # Verify that waiting processes actually hold some resources
        holding = [p for p in waiting if any(x > 0 for x in p.allocated.as_list())]
        if len(holding) >= 2:
            pids = [p.pid for p in holding]
            names = [p.name for p in holding]
            return True, pids, f"Deadlock: {', '.join(names)} hold resources and wait for each other with 0 available resources."

    return False, [], "No circular deadlock"

