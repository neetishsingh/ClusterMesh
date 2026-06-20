from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mesh.models.enums import NodeState

if TYPE_CHECKING:
    from mesh.sim.cluster import SimCluster


@dataclass
class ChaosController:
    """Scriptable failure injection for SimCluster tests."""

    cluster: SimCluster
    _scheduled: list[tuple[float, str]] = field(default_factory=list, repr=False)

    def kill_node(self, node_id: str, at: float) -> None:
        def action() -> None:
            for agent in self.cluster.agents:
                if agent.node_id == node_id:
                    agent.kill()
            self.cluster._health_registry.force_state(node_id, NodeState.DEAD)

        self.cluster.schedule_event(at, action, f"kill {node_id}")

    def preempt(self, node_id: str, at: float, cpu_spike: float = 0.95) -> None:
        def action() -> None:
            for agent in self.cluster.agents:
                if agent.node_id == node_id:
                    agent.preempt(cpu_spike)

        self.cluster.schedule_event(at, action, f"preempt {node_id}")

    def battery_drain(self, node_id: str, at: float, to_pct: float) -> None:
        def action() -> None:
            for agent in self.cluster.agents:
                if agent.node_id == node_id:
                    agent.drain_battery(to_pct)

        self.cluster.schedule_event(at, action, f"battery drain {node_id} to {to_pct}%")

    def partition(self, location_a: str, location_b: str, at: float, duration: float) -> None:
        def isolate() -> None:
            for agent in self.cluster.agents:
                if agent.location in (location_a, location_b):
                    agent._partitioned = True  # type: ignore[attr-defined]

        def heal() -> None:
            for agent in self.cluster.agents:
                agent._partitioned = False  # type: ignore[attr-defined]

        self.cluster.schedule_event(at, isolate, f"partition {location_a}/{location_b}")
        self.cluster.schedule_event(at + duration, heal, f"heal partition")
