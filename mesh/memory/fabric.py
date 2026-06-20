"""Distributed memory fabric — aggregate RAM across the cluster."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import NodeState
from mesh.models.node import Node


@dataclass
class MemorySegment:
    node_id: str
    hostname: str
    size_gb: float
    location: str = "default"


@dataclass
class MemoryAllocation:
    allocation_id: str
    total_gb: float
    segments: list[MemorySegment] = field(default_factory=list)
    owner: str = ""
    pinned: bool = False

    def to_dict(self) -> dict:
        return {
            "allocation_id": self.allocation_id,
            "total_gb": round(self.total_gb, 2),
            "owner": self.owner,
            "pinned": self.pinned,
            "segments": [
                {
                    "node_id": s.node_id,
                    "hostname": s.hostname,
                    "size_gb": round(s.size_gb, 2),
                    "location": s.location,
                }
                for s in self.segments
            ],
        }


@dataclass
class MemoryPoolStats:
    total_gb: float
    free_gb: float
    allocated_gb: float
    node_count: int
    segment_count: int

    def to_dict(self) -> dict:
        return {
            "total_gb": round(self.total_gb, 2),
            "free_gb": round(self.free_gb, 2),
            "allocated_gb": round(self.allocated_gb, 2),
            "utilization_pct": round(
                (self.allocated_gb / self.total_gb * 100) if self.total_gb else 0, 1
            ),
            "node_count": self.node_count,
            "segment_count": self.segment_count,
        }


class MemoryFabric:
    """
    Expose cluster RAM as a unified logical pool.

    Example: Node1 32GB + Node2 64GB + Node3 16GB → 112GB logical pool.
    Allocations are striped across nodes using best-fit decreasing bin packing.
    """

    def __init__(self) -> None:
        self._allocations: dict[str, MemoryAllocation] = {}
        self._reserved: dict[str, float] = {}  # node_id → reserved gb

    def _eligible_nodes(self, nodes: list[Node]) -> list[Node]:
        return [n for n in nodes if n.state == NodeState.HEALTHY]

    def _free_on_node(self, node: Node) -> float:
        reserved = self._reserved.get(node.node_id, 0.0)
        return max(0.0, node.resources.ram_gb_free - reserved)

    def pool_stats(self, nodes: list[Node]) -> MemoryPoolStats:
        eligible = self._eligible_nodes(nodes)
        total = sum(n.resources.ram_gb_total for n in eligible)
        free = sum(self._free_on_node(n) for n in eligible)
        allocated = sum(a.total_gb for a in self._allocations.values())
        segments = sum(len(a.segments) for a in self._allocations.values())
        return MemoryPoolStats(
            total_gb=total,
            free_gb=free,
            allocated_gb=allocated,
            node_count=len(eligible),
            segment_count=segments,
        )

    def allocate(
        self,
        size_gb: float,
        nodes: list[Node],
        owner: str = "",
        min_segment_gb: float = 1.0,
    ) -> Optional[MemoryAllocation]:
        if size_gb <= 0:
            return None

        eligible = self._eligible_nodes(nodes)
        # Best-fit decreasing: prefer nodes with least waste after allocation
        available = sorted(
            [(n, self._free_on_node(n)) for n in eligible if self._free_on_node(n) >= min_segment_gb],
            key=lambda x: x[1],
        )
        total_free = sum(f for _, f in available)
        if total_free < size_gb:
            return None

        remaining = size_gb
        segments: list[MemorySegment] = []
        # Greedy: take from largest free blocks first for fewer segments
        by_free = sorted(available, key=lambda x: -x[1])

        for node, free in by_free:
            if remaining <= 0:
                break
            take = min(free, remaining)
            if take < min_segment_gb and remaining > min_segment_gb:
                continue
            segments.append(
                MemorySegment(
                    node_id=node.node_id,
                    hostname=node.hostname,
                    size_gb=take,
                    location=node.location,
                )
            )
            self._reserved[node.node_id] = self._reserved.get(node.node_id, 0.0) + take
            remaining -= take

        if remaining > 0.01:
            # rollback
            for seg in segments:
                self._reserved[seg.node_id] = max(
                    0, self._reserved.get(seg.node_id, 0) - seg.size_gb
                )
            return None

        alloc = MemoryAllocation(
            allocation_id=str(uuid.uuid4()),
            total_gb=size_gb,
            segments=segments,
            owner=owner,
        )
        self._allocations[alloc.allocation_id] = alloc
        return alloc

    def release(self, allocation_id: str) -> bool:
        alloc = self._allocations.pop(allocation_id, None)
        if not alloc:
            return False
        for seg in alloc.segments:
            self._reserved[seg.node_id] = max(
                0, self._reserved.get(seg.node_id, 0) - seg.size_gb
            )
        return True

    def list_allocations(self) -> list[MemoryAllocation]:
        return list(self._allocations.values())

    def get_allocation(self, allocation_id: str) -> Optional[MemoryAllocation]:
        return self._allocations.get(allocation_id)
