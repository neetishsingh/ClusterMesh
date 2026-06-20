from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import NodeState, ResourcePool
from mesh.models.node import Node, NodeResources


@dataclass
class SimAgent:
    """In-process simulated compute agent."""

    node_id: str
    cpu_cores: int = 8
    ram_gb: float = 16.0
    gpu_count: int = 0
    vram_gb: float = 0.0
    cuda_version: Optional[str] = None
    network_gbps: float = 1.0
    battery_pct: Optional[float] = None
    preemptible: bool = False
    reliability: float = 0.8
    latency_score: float = 0.9
    pool: ResourcePool = ResourcePool.CPU
    location: str = "default"
    hostname: str = ""
    alive: bool = True
    user_active: bool = False
    cpu_utilization: float = 0.0
    _assigned_tasks: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.hostname:
            self.hostname = self.node_id

    def to_node(self, state: NodeState = NodeState.HEALTHY) -> Node:
        free_cpu = max(0, self.cpu_cores * (1.0 - self.cpu_utilization))
        return Node(
            node_id=self.node_id,
            hostname=self.hostname,
            resources=NodeResources(
                cpu_cores_total=self.cpu_cores,
                cpu_cores_free=free_cpu if self.alive else 0,
                ram_gb_total=self.ram_gb,
                ram_gb_free=self.ram_gb * 0.7 if self.alive else 0,
                gpu_count=self.gpu_count,
                vram_gb_free=self.vram_gb if self.alive else 0,
                cuda_version=self.cuda_version,
                network_gbps=self.network_gbps,
                battery_pct=self.battery_pct,
                cpu_utilization=self.cpu_utilization,
                user_active=self.user_active,
            ),
            state=state if self.alive else NodeState.DEAD,
            reliability_score=self.reliability,
            latency_score=self.latency_score,
            pool=self.pool,
            preemptible=self.preemptible,
            location=self.location,
        )

    def kill(self) -> None:
        self.alive = False

    def preempt(self, cpu_spike: float = 0.95) -> None:
        self.user_active = True
        self.cpu_utilization = cpu_spike

    def drain_battery(self, to_pct: float) -> None:
        if self.battery_pct is not None:
            self.battery_pct = to_pct
