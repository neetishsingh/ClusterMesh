from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.node import Node
from mesh.models.task import TaskSpec
from mesh.scheduler.pools import PoolRouter
from mesh.scheduler.scoring import NodeScorer


@dataclass(frozen=True)
class Placement:
    task_id: str
    node_id: str
    score: float


@dataclass
class PlacementEngine:
    """Constraint-aware task placement with node scoring."""

    scorer: NodeScorer = field(default_factory=NodeScorer)
    pool_router: PoolRouter = field(default_factory=PoolRouter)

    def place(
        self,
        task: TaskSpec,
        nodes: list[Node],
    ) -> Optional[Placement]:
        eligible = self.pool_router.eligible_nodes(nodes, pool=task.pool)
        candidates = [n for n in eligible if n.meets_requirements(task.requirements)]

        if not candidates:
            return None

        scored = [
            (n, self.scorer.score(n, task.requirements))
            for n in candidates
        ]
        scored.sort(key=lambda x: (-x[1], x[0].node_id))

        best_node, best_score = scored[0]
        if best_score <= 0:
            return None

        return Placement(
            task_id=task.task_id,
            node_id=best_node.node_id,
            score=best_score,
        )

    def place_all(
        self,
        tasks: list[TaskSpec],
        nodes: list[Node],
    ) -> list[Placement]:
        placements = []
        used_resources: dict[str, tuple[float, float]] = {}

        for task in tasks:
            available = self._apply_usage(nodes, used_resources)
            placement = self.place(task, available)
            if placement:
                placements.append(placement)
                node = next(n for n in nodes if n.node_id == placement.node_id)
                cpu_used, ram_used = used_resources.get(placement.node_id, (0.0, 0.0))
                used_resources[placement.node_id] = (
                    cpu_used + task.requirements.cpu_cores,
                    ram_used + task.requirements.ram_gb,
                )
        return placements

    def _apply_usage(
        self,
        nodes: list[Node],
        usage: dict[str, tuple[float, float]],
    ) -> list[Node]:
        adjusted = []
        for node in nodes:
            cpu_used, ram_used = usage.get(node.node_id, (0.0, 0.0))
            from dataclasses import replace
            from mesh.models.node import NodeResources

            new_resources = NodeResources(
                cpu_cores_total=node.resources.cpu_cores_total,
                cpu_cores_free=max(0, node.resources.cpu_cores_free - cpu_used),
                ram_gb_total=node.resources.ram_gb_total,
                ram_gb_free=max(0, node.resources.ram_gb_free - ram_used),
                gpu_count=node.resources.gpu_count,
                vram_gb_free=node.resources.vram_gb_free,
                cuda_version=node.resources.cuda_version,
                network_gbps=node.resources.network_gbps,
                battery_pct=node.resources.battery_pct,
                cpu_utilization=node.resources.cpu_utilization,
                user_active=node.resources.user_active,
            )
            adjusted.append(replace(node, resources=new_resources))
        return adjusted
