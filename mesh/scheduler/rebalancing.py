from __future__ import annotations

from dataclasses import dataclass

from mesh.models.node import Node
from mesh.models.task import TaskSpec


@dataclass
class RebalanceAction:
    task_id: str
    from_node: str
    to_node: str
    reason: str


@dataclass
class Rebalancer:
    """
    Migrates tasks from overloaded nodes to underutilized ones.

    Triggered when CPU utilization variance exceeds threshold (default 30%).
    """

    variance_threshold: float = 0.30

    def analyze(
        self,
        nodes: list[Node],
        tasks: list[TaskSpec],
    ) -> list[RebalanceAction]:
        if len(nodes) < 2:
            return []

        utilizations = []
        for n in nodes:
            total = n.resources.cpu_cores_total
            if total == 0:
                continue
            used = total - n.resources.cpu_cores_free
            utilizations.append((n, used / total))

        if not utilizations:
            return []

        avg = sum(u for _, u in utilizations) / len(utilizations)
        overloaded = [(n, u) for n, u in utilizations if u - avg > self.variance_threshold]
        underloaded = [(n, u) for n, u in utilizations if avg - u > self.variance_threshold]

        if not overloaded or not underloaded:
            return []

        actions = []
        under_idx = 0
        for node, util in overloaded:
            node_tasks = [t for t in tasks if t.assigned_node == node.node_id]
            for task in node_tasks[:1]:
                if under_idx >= len(underloaded):
                    break
                target, _ = underloaded[under_idx]
                actions.append(RebalanceAction(
                    task_id=task.task_id,
                    from_node=node.node_id,
                    to_node=target.node_id,
                    reason=f"cpu_util={util:.0%} → target free={target.resources.cpu_cores_free:.1f}",
                ))
                under_idx += 1
        return actions
