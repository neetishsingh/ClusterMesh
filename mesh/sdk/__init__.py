from __future__ import annotations

from typing import Any, Callable, Optional

from mesh.driver.job_manager import JobHandle, JobManager
from mesh.sdk.decorator import MeshTask, task
from mesh.sim.cluster import SimCluster

_default_cluster: SimCluster | None = None
_default_manager: JobManager | None = None


def get_cluster(node_count: int = 10) -> SimCluster:
    global _default_cluster, _default_manager
    if _default_cluster is None:
        _default_cluster = SimCluster.create(node_count=node_count)
        _default_manager = JobManager(cluster=_default_cluster)
    return _default_cluster


def get_manager() -> JobManager:
    get_cluster()
    assert _default_manager is not None
    return _default_manager


def submit(
    mesh_task: MeshTask | Callable,
    *,
    async_: bool = False,
    idempotency_key: Optional[str] = None,
    timeout: Optional[float] = None,
    cluster: Optional[SimCluster] = None,
) -> Any | JobHandle:
    """
    Submit a @task-decorated function for distributed execution.

    Returns the result directly, or a JobHandle if async_=True.
    """
    if cluster is not None:
        manager = JobManager(cluster=cluster)
    else:
        manager = get_manager()
    return manager.submit(
        mesh_task,
        async_=async_,
        idempotency_key=idempotency_key,
        timeout=timeout,
    )


def reset_defaults() -> None:
    """Reset the default cluster and manager (for testing)."""
    global _default_cluster, _default_manager
    _default_cluster = None
    _default_manager = None


__all__ = ["MeshTask", "get_cluster", "get_manager", "reset_defaults", "submit", "task"]
