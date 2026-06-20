from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from mesh.health.heartbeat import HeartbeatTracker, NodeHealthRegistry
from mesh.models.enums import NodeState, TaskState
from mesh.models.node import Node, NodeResources
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import CheckpointManager
from mesh.scheduler.placement import PlacementEngine


@dataclass
class RemoteAgent:
    """Handle to a real agent connected via gRPC."""

    node_id: str
    agent_address: str
    assign_task: Callable  # (TaskAssignment proto) -> Ack
    cancel_task: Callable
    pause_task: Callable
    install_library: Callable
    run_shell: Callable


@dataclass
class DriverCluster:
    """
    Production cluster state backing the driver.

    Holds registered real agents plus optional simulated nodes for testing.
    """

    heartbeat_interval: float = 2.0
    placement_engine: PlacementEngine = field(default_factory=PlacementEngine)
    checkpoint_manager: CheckpointManager = field(default_factory=CheckpointManager)

    _nodes: dict[str, Node] = field(default_factory=dict, repr=False)
    _remote_agents: dict[str, RemoteAgent] = field(default_factory=dict, repr=False)
    _tasks: dict[str, TaskSpec] = field(default_factory=dict, repr=False)
    _health_registry: NodeHealthRegistry = field(init=False, repr=False)
    _job_manager: object = field(default=None, repr=False)
    _state_changes: list[tuple[float, str, NodeState, NodeState]] = field(
        default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        tracker = HeartbeatTracker(interval_seconds=self.heartbeat_interval)
        self._health_registry = NodeHealthRegistry(tracker=tracker)
        self._health_registry.on_state_change(self._on_state_change)

    def attach_job_manager(self, job_manager: object) -> None:
        self._job_manager = job_manager

    def _on_state_change(self, node_id: str, old: NodeState, new: NodeState) -> None:
        import time
        self._state_changes.append((time.time(), node_id, old, new))
        if new == NodeState.DEAD and self._job_manager is not None:
            self._job_manager.handle_node_death(node_id)

    def register_node(self, node: Node, remote: Optional[RemoteAgent] = None) -> None:
        self._nodes[node.node_id] = node
        self._health_registry.register(node.node_id)
        if remote:
            self._remote_agents[node.node_id] = remote

    def update_node_resources(self, node_id: str, resources: NodeResources, *, host_metrics_json: str = "") -> None:
        if node_id in self._nodes:
            from dataclasses import replace
            node = self._nodes[node_id]
            tags = dict(node.tags)
            if host_metrics_json:
                tags["host_metrics"] = host_metrics_json
            self._nodes[node_id] = replace(node, resources=resources, tags=tags)

    def update_node_state(self, node_id: str, state: NodeState) -> None:
        if node_id in self._nodes:
            from dataclasses import replace
            self._nodes[node_id] = replace(self._nodes[node_id], state=state)

    def record_heartbeat(self, node_id: str) -> NodeState:
        return self._health_registry.record_heartbeat(node_id)

    def evaluate_health(self) -> dict[str, NodeState]:
        return self._health_registry.evaluate_all()

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def is_remote(self, node_id: str) -> bool:
        return node_id in self._remote_agents

    def get_remote(self, node_id: str) -> Optional[RemoteAgent]:
        return self._remote_agents.get(node_id)

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._remote_agents.pop(node_id, None)
        self._health_registry.tracker.mark_dead(node_id)

    def live_nodes(self) -> list[Node]:
        nodes = []
        for node_id, node in self._nodes.items():
            state = self._health_registry.get_state(node_id)
            from dataclasses import replace
            nodes.append(replace(node, state=state))
        return [n for n in nodes if n.state != NodeState.DEAD]

    @staticmethod
    def aggregate_cpu_utilization_pct(
        nodes: list[Node],
        *,
        extra_util: float = 0.0,
        extra_cores: int = 0,
    ) -> float:
        """Core-weighted average CPU % across nodes (0–100)."""
        weighted = 0.0
        total_cores = 0
        for node in nodes:
            cores = node.resources.cpu_cores_total
            total_cores += cores
            weighted += node.resources.cpu_utilization * cores
        if extra_cores > 0:
            total_cores += extra_cores
            weighted += extra_util * extra_cores
        if total_cores == 0:
            return 0.0
        return round(weighted / total_cores * 100, 1)

    def submit(self, task: TaskSpec) -> Optional[str]:
        self._tasks[task.task_id] = task
        placement = self.placement_engine.place(task, self.live_nodes())
        if placement:
            task.assigned_node = placement.node_id
            task.state = TaskState.RUNNING
            return placement.node_id
        task.state = TaskState.PENDING
        return None

    def cluster_stats(self) -> dict:
        nodes = list(self._nodes.values())
        live = self.live_nodes()
        running = sum(1 for t in self._tasks.values() if t.state == TaskState.RUNNING)
        pending = sum(1 for t in self._tasks.values() if t.state == TaskState.PENDING)
        return {
            "total_nodes": len(self._nodes),
            "healthy_nodes": sum(1 for n in nodes if n.state == NodeState.HEALTHY),
            "suspected_nodes": sum(1 for n in nodes if n.state == NodeState.SUSPECTED),
            "dead_nodes": sum(1 for n in nodes if n.state == NodeState.DEAD),
            "total_cpu_cores": sum(n.resources.cpu_cores_total for n in live),
            "free_cpu_cores": sum(n.resources.cpu_cores_free for n in live),
            "total_ram_gb": sum(n.resources.ram_gb_total for n in live),
            "free_ram_gb": sum(n.resources.ram_gb_free for n in live),
            "total_gpus": sum(n.resources.gpu_count for n in live),
            "tasks_running": running,
            "tasks_completed": sum(
                1 for t in self._tasks.values() if t.state == TaskState.COMPLETED
            ),
            "active_tasks": running + pending,
            "active_jobs": 0,
        }

    @property
    def tasks(self) -> dict[str, TaskSpec]:
        return self._tasks

    @property
    def health_registry(self) -> NodeHealthRegistry:
        return self._health_registry
