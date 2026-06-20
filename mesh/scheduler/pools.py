from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from mesh.models.enums import ResourcePool
from mesh.models.node import Node


@dataclass
class PoolRouter:
    """
    Routes tasks to eligible resource pools.

    Night pool: laptops after office hours (default 6PM–8AM).
    GPU pool: requires CUDA-capable nodes.
    """

    night_start_hour: int = 18
    night_end_hour: int = 8
    battery_min_pct: float = 60.0

    def is_night_window(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        hour = now.hour
        if self.night_start_hour > self.night_end_hour:
            return hour >= self.night_start_hour or hour < self.night_end_hour
        return self.night_start_hour <= hour < self.night_end_hour

    def eligible_nodes(
        self,
        nodes: list[Node],
        pool: Optional[ResourcePool] = None,
        now: Optional[datetime] = None,
    ) -> list[Node]:
        if pool is None:
            return list(nodes)

        if pool == ResourcePool.NIGHT:
            if not self.is_night_window(now):
                return []
            return [
                n
                for n in nodes
                if n.preemptible and self._passes_battery_gate(n)
            ]

        if pool == ResourcePool.GPU:
            return [
                n
                for n in nodes
                if n.resources.gpu_count > 0
                and n.resources.cuda_version is not None
                and self._passes_battery_gate(n)
            ]

        if pool == ResourcePool.MEMORY:
            return sorted(
                [n for n in nodes if self._passes_battery_gate(n)],
                key=lambda n: n.resources.ram_gb_free,
                reverse=True,
            )

        # CPU pool — office desktops, non-preemptible preferred
        return [
            n
            for n in nodes
            if not n.preemptible and self._passes_battery_gate(n)
        ]

    def _passes_battery_gate(self, node: Node) -> bool:
        battery = node.resources.battery_pct
        if battery is None:
            return True
        return battery >= self.battery_min_pct
