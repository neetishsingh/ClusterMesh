from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import TaskState
from mesh.models.job import Job, JobState
from mesh.models.task import TaskSpec
from mesh.scheduler.placement import PlacementEngine


@dataclass
class ReplicationManager:
    """
    Manages task replicas for fault-tolerant execution.

    When replicas=N, the same job runs on N different nodes.
    First replica to complete wins; others are cancelled.
    """

    placement_engine: PlacementEngine = field(default_factory=PlacementEngine)

    def create_replica_specs(
        self,
        base_spec: TaskSpec,
        job_id: str,
        count: int,
    ) -> list[TaskSpec]:
        from dataclasses import replace
        import uuid

        return [
            replace(
                base_spec,
                task_id=str(uuid.uuid4()),
                job_id=job_id,
                replica_index=i,
                replicas=1,
            )
            for i in range(count)
        ]

    def on_replica_complete(
        self,
        job: Job,
        completed_spec: TaskSpec,
        all_specs: list[TaskSpec],
    ) -> list[TaskSpec]:
        """Mark job complete and return replica specs that should be cancelled."""
        job.state = JobState.COMPLETED
        job.completed_task_id = completed_spec.task_id
        return [
            s for s in all_specs
            if s.task_id != completed_spec.task_id
            and s.state in (TaskState.RUNNING, TaskState.PENDING, TaskState.MIGRATING)
        ]

    def on_replica_failure(
        self,
        job: Job,
        failed_spec: TaskSpec,
        all_specs: list[TaskSpec],
    ) -> bool:
        """
        Returns True if job can continue (another replica still running).
        Returns False if all replicas have failed.
        """
        active = [
            s for s in all_specs
            if s.task_id != failed_spec.task_id
            and s.state in (TaskState.RUNNING, TaskState.PENDING, TaskState.MIGRATING)
        ]
        if active:
            return True
        job.state = JobState.FAILED
        job.error = f"All replicas failed (last: {failed_spec.task_id})"
        return False

    def assign_to_different_nodes(
        self,
        specs: list[TaskSpec],
        nodes: list,
    ) -> list[tuple[TaskSpec, Optional[str]]]:
        """Place each replica on a distinct node when possible."""
        results = []
        used: set[str] = set()

        for spec in specs:
            available = [n for n in nodes if n.node_id not in used]
            if not available:
                available = nodes
            placement = self.placement_engine.place(spec, available)
            if placement:
                spec.assigned_node = placement.node_id
                spec.state = TaskState.RUNNING
                used.add(placement.node_id)
                results.append((spec, placement.node_id))
            else:
                spec.state = TaskState.PENDING
                results.append((spec, None))

        return results
