from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import uuid

from mesh.models.enums import ResourcePool, TaskState


@dataclass
class ResourceRequirements:
    cpu_cores: float = 1.0
    ram_gb: float = 1.0
    gpu_count: int = 0
    vram_gb: float = 0.0
    cuda_version: Optional[str] = None
    network_gbps: float = 0.0
    min_battery_pct: Optional[float] = None


@dataclass
class TaskSpec:
    """Specification for a schedulable task."""

    name: str
    requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    pool: Optional[ResourcePool] = None
    replicas: int = 1
    checkpoint: bool = False
    checkpoint_interval: float = 30.0
    preemption_ok: bool = True
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: Optional[str] = None
    replica_index: int = 0
    state: TaskState = TaskState.PENDING
    assigned_node: Optional[str] = None
    progress: float = 0.0
    total_work: float = 1.0
    state_data: dict[str, Any] = field(default_factory=dict)
    fn: Optional[Callable] = field(default=None, repr=False, compare=False)

    @property
    def cpu_cores(self) -> float:
        return self.requirements.cpu_cores

    @property
    def ram_gb(self) -> float:
        return self.requirements.ram_gb

    @property
    def progress_pct(self) -> float:
        if self.total_work == 0:
            return 100.0
        return min(100.0, (self.progress / self.total_work) * 100.0)
