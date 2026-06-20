from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import NodeState, ResourcePool


@dataclass
class NodeResources:
    """Live resource snapshot reported by an agent."""

    cpu_cores_total: int
    cpu_cores_free: float
    ram_gb_total: float
    ram_gb_free: float
    gpu_count: int = 0
    vram_gb_free: float = 0.0
    cuda_version: Optional[str] = None
    network_gbps: float = 1.0
    battery_pct: Optional[float] = None
    cpu_utilization: float = 0.0
    user_active: bool = False

    @property
    def cpu_score_component(self) -> float:
        if self.cpu_cores_total == 0:
            return 0.0
        return min(1.0, self.cpu_cores_free / self.cpu_cores_total)

    @property
    def memory_score_component(self) -> float:
        if self.ram_gb_total == 0:
            return 0.0
        return min(1.0, self.ram_gb_free / self.ram_gb_total)

    @property
    def gpu_score_component(self) -> float:
        if self.gpu_count == 0:
            return 0.0
        return 1.0 if self.vram_gb_free > 0 else 0.0


@dataclass
class Node:
    """A compute node in the cluster."""

    node_id: str
    hostname: str
    resources: NodeResources
    state: NodeState = NodeState.HEALTHY
    reliability_score: float = 0.8
    latency_score: float = 0.9
    pool: ResourcePool = ResourcePool.CPU
    preemptible: bool = False
    location: str = "default"
    tags: dict[str, str] = field(default_factory=dict)

    def meets_requirements(self, req: "ResourceRequirements") -> bool:
        from mesh.models.task import ResourceRequirements

        if not isinstance(req, ResourceRequirements):
            return False

        r = self.resources
        if r.cpu_cores_free < req.cpu_cores:
            return False
        if r.ram_gb_free < req.ram_gb:
            return False
        if req.gpu_count > 0:
            if r.gpu_count < req.gpu_count:
                return False
            if req.vram_gb > 0 and r.vram_gb_free < req.vram_gb:
                return False
            if req.cuda_version and r.cuda_version:
                if float(r.cuda_version.split(".")[0]) < float(req.cuda_version.split(".")[0]):
                    return False
        if req.network_gbps > 0 and r.network_gbps < req.network_gbps:
            return False
        if req.min_battery_pct is not None and r.battery_pct is not None:
            if r.battery_pct < req.min_battery_pct:
                return False
        if self.state not in (NodeState.HEALTHY,):
            return False
        return True
