"""Memory Management: Paging simulation with FIFO and LRU page replacement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PageFrame:
    frame_id: int
    pid: Optional[int] = None
    process_name: str = "Free"
    page_num: Optional[int] = None
    loaded_tick: int = 0
    last_accessed_tick: int = 0


class PagingMemoryManager:
    def __init__(self, num_frames: int = 8, policy: str = "LRU"):
        self.num_frames = num_frames
        self.policy = policy if policy in ("FIFO", "LRU") else "LRU"
        self.frames: List[PageFrame] = [PageFrame(frame_id=i) for i in range(num_frames)]
        self.total_references: int = 0
        self.page_hits: int = 0
        self.page_faults: int = 0
        self.last_eviction: Optional[str] = None

    def set_policy(self, policy: str) -> None:
        if policy in ("FIFO", "LRU"):
            self.policy = policy

    def reset(self) -> None:
        self.frames = [PageFrame(frame_id=i) for i in range(self.num_frames)]
        self.total_references = 0
        self.page_hits = 0
        self.page_faults = 0
        self.last_eviction = None

    def access_page(self, pid: int, process_name: str, page_num: int, tick: int) -> Dict[str, Any]:
        """Simulate a memory access to a page of a process."""
        self.total_references += 1

        # Check for page hit
        for f in self.frames:
            if f.pid == pid and f.page_num == page_num:
                self.page_hits += 1
                f.last_accessed_tick = tick
                return {
                    "hit": True,
                    "frame_id": f.frame_id,
                    "evicted": None,
                    "msg": f"Hit: Page {page_num} of {process_name} found in Frame {f.frame_id}",
                }

        # Page fault occurs
        self.page_faults += 1

        # 1. Look for free frame
        for f in self.frames:
            if f.pid is None:
                f.pid = pid
                f.process_name = process_name
                f.page_num = page_num
                f.loaded_tick = tick
                f.last_accessed_tick = tick
                return {
                    "hit": False,
                    "frame_id": f.frame_id,
                    "evicted": None,
                    "msg": f"Fault: Loaded Page {page_num} of {process_name} into free Frame {f.frame_id}",
                }

        # 2. Page replacement needed
        if self.policy == "FIFO":
            victim = min(self.frames, key=lambda f: f.loaded_tick)
        else:  # LRU
            victim = min(self.frames, key=lambda f: f.last_accessed_tick)

        old_desc = f"{victim.process_name} P{victim.page_num}"
        victim.pid = pid
        victim.process_name = process_name
        victim.page_num = page_num
        victim.loaded_tick = tick
        victim.last_accessed_tick = tick

        self.last_eviction = f"Evicted {old_desc} from Frame {victim.frame_id} ({self.policy})"
        return {
            "hit": False,
            "frame_id": victim.frame_id,
            "evicted": old_desc,
            "msg": f"Fault: {self.policy} evicted {old_desc} for Page {page_num} of {process_name} in Frame {victim.frame_id}",
        }

    def release_process_pages(self, pid: int) -> None:
        """Free all frames allocated to a process."""
        for f in self.frames:
            if f.pid == pid:
                f.pid = None
                f.process_name = "Free"
                f.page_num = None
                f.loaded_tick = 0
                f.last_accessed_tick = 0

    def snapshot(self) -> Dict[str, Any]:
        hit_ratio = round((self.page_hits / self.total_references) * 100, 1) if self.total_references > 0 else 0.0
        fault_ratio = round((self.page_faults / self.total_references) * 100, 1) if self.total_references > 0 else 0.0

        return {
            "policy": self.policy,
            "total_references": self.total_references,
            "page_hits": self.page_hits,
            "page_faults": self.page_faults,
            "hit_ratio": hit_ratio,
            "fault_ratio": fault_ratio,
            "last_eviction": self.last_eviction,
            "frames": [
                {
                    "frame_id": f.frame_id,
                    "pid": f.pid,
                    "process_name": f.process_name,
                    "page_num": f.page_num,
                    "loaded_tick": f.loaded_tick,
                    "last_accessed_tick": f.last_accessed_tick,
                    "is_free": f.pid is None,
                }
                for f in self.frames
            ],
        }
