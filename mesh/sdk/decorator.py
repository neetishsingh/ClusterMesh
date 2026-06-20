from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from mesh.models.enums import ResourcePool
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.sdk.units import parse_bandwidth, parse_bytes, parse_pool


@dataclass
class MeshTask:
    """A Python callable annotated with resource requirements."""

    fn: Callable
    name: str
    requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    pool: Optional[ResourcePool] = None
    replicas: int = 1
    checkpoint: bool = False
    checkpoint_interval: float = 30.0
    preemption_ok: bool = True
    total_work: float = 1.0

    def to_spec(self, job_id: Optional[str] = None, replica_index: int = 0) -> TaskSpec:
        return TaskSpec(
            name=self.name,
            requirements=self.requirements,
            pool=self.pool,
            replicas=self.replicas,
            checkpoint=self.checkpoint,
            checkpoint_interval=self.checkpoint_interval,
            preemption_ok=self.preemption_ok,
            total_work=self.total_work,
            job_id=job_id,
            replica_index=replica_index,
            fn=self.fn,
        )


def task(
    fn: Callable | None = None,
    *,
    cpu: float = 1,
    ram: str | float = 1,
    gpu: int = 0,
    vram: str | float = 0,
    cuda: str | None = None,
    network: str | float = 0,
    pool: str | ResourcePool | None = None,
    replicas: int = 1,
    checkpoint: bool = False,
    checkpoint_interval: float = 30.0,
    preemption_ok: bool = True,
    total_work: float = 1.0,
    name: str | None = None,
) -> Callable:
    """
    Decorator to register a function as a ClusterMesh task.

    Example::

        @task(cpu=4, checkpoint=True, total_work=1_000_000)
        def process(ctx: TaskContext):
            for i in range(int(ctx.progress), 1_000_000):
                ctx.set_progress(i)
    """

    def decorator(f: Callable) -> MeshTask:
        requirements = ResourceRequirements(
            cpu_cores=cpu,
            ram_gb=parse_bytes(ram) if isinstance(ram, str) else float(ram),
            gpu_count=gpu,
            vram_gb=parse_bytes(vram) if isinstance(vram, str) else float(vram),
            cuda_version=cuda,
            network_gbps=parse_bandwidth(network) if isinstance(network, str) else float(network),
        )
        mesh_task = MeshTask(
            fn=f,
            name=name or f.__name__,
            requirements=requirements,
            pool=parse_pool(pool),
            replicas=replicas,
            checkpoint=checkpoint,
            checkpoint_interval=checkpoint_interval,
            preemption_ok=preemption_ok,
            total_work=total_work,
        )
        f._mesh_task = mesh_task  # type: ignore[attr-defined]
        return mesh_task

    if fn is not None:
        return decorator(fn)
    return decorator
