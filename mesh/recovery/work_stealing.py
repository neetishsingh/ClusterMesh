from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import NodeState, TaskState
from mesh.models.node import Node
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import CheckpointManager
from mesh.scheduler.placement import PlacementEngine


@dataclass
class WorkStealer:
    """
    Reassigns orphaned tasks when a node dies or is preempted.

    Restores checkpoint progress before resuming on a new node.
    SLA target: reassignment within 5 seconds of DEAD state.
    """

    placement_engine: PlacementEngine = field(default_factory=PlacementEngine)
    checkpoint_manager: CheckpointManager = field(default_factory=CheckpointManager)
    reassignment_deadline_seconds: float = 5.0

    def find_orphaned_tasks(
        self,
        tasks: list[TaskSpec],
        dead_node_ids: set[str],
    ) -> list[TaskSpec]:
        return [
            t
            for t in tasks
            if t.assigned_node in dead_node_ids
            and t.state in (TaskState.RUNNING, TaskState.PAUSED, TaskState.CHECKPOINTING)
        ]

    def steal(
        self,
        orphaned_tasks: list[TaskSpec],
        available_nodes: list[Node],
    ) -> list[tuple[TaskSpec, Optional[str]]]:
        results = []
        healthy_nodes = [n for n in available_nodes if n.state == NodeState.HEALTHY]
        used_nodes: set[str] = set()

        for task in orphaned_tasks:
            self.checkpoint_manager.restore(task)
            task.state = TaskState.MIGRATING

            candidates = [
                n for n in healthy_nodes
                if n.node_id not in used_nodes or len(healthy_nodes) == 1
            ]
            placement = self.placement_engine.place(task, candidates)
            if placement:
                task.assigned_node = placement.node_id
                task.state = TaskState.RUNNING
                used_nodes.add(placement.node_id)
                results.append((task, placement.node_id))
            else:
                task.state = TaskState.PENDING
                task.assigned_node = None
                results.append((task, None))

        return results
