from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from mesh.health.heartbeat import HeartbeatTracker, NodeHealthRegistry
from mesh.models.enums import NodeState, TaskState
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import CheckpointManager
from mesh.recovery.work_stealing import WorkStealer
from mesh.scheduler.placement import PlacementEngine
from mesh.sim.agent import SimAgent
from mesh.sim.clock import SimClock

if TYPE_CHECKING:
    from mesh.driver.job_manager import JobManager


@dataclass
class SimEvent:
    at: float
    action: Callable[[], None]
    description: str = ""


@dataclass
class SimCluster:
    """
    Orchestrates simulated agents, scheduler, and health tracking.

    Runs deterministically with SimClock for fast CI testing.
    """

    agents: list[SimAgent] = field(default_factory=list)
    clock: SimClock = field(default_factory=SimClock)
    heartbeat_interval: float = 2.0
    tick_interval: float = 1.0

    placement_engine: PlacementEngine = field(default_factory=PlacementEngine)
    checkpoint_manager: CheckpointManager = field(default_factory=CheckpointManager)
    work_stealer: WorkStealer = field(default_factory=WorkStealer)

    _tasks: dict[str, TaskSpec] = field(default_factory=dict, repr=False)
    _events: list[SimEvent] = field(default_factory=list, repr=False)
    _health_registry: NodeHealthRegistry = field(init=False, repr=False)
    _state_changes: list[tuple[float, str, NodeState, NodeState]] = field(
        default_factory=list, repr=False
    )
    _job_manager: Optional[JobManager] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        tracker = HeartbeatTracker(
            interval_seconds=self.heartbeat_interval,
            clock=self.clock.now,
        )
        self._health_registry = NodeHealthRegistry(tracker=tracker)
        self._health_registry.on_state_change(self._on_state_change)

        for agent in self.agents:
            self._health_registry.register(agent.node_id)

    @classmethod
    def create(
        cls,
        node_count: int = 10,
        clock: Optional[SimClock] = None,
        **agent_kwargs,
    ) -> SimCluster:
        clock = clock or SimClock()
        agents = [
            SimAgent(
                node_id=f"NODE-{i:03d}",
                cpu_cores=8 + (i % 4) * 4,
                ram_gb=16 + (i % 3) * 16,
                preemptible=(i % 3 == 0),
                battery_pct=80.0 if i % 3 == 0 else None,
                reliability=0.6 if i % 3 == 0 else 0.9,
            )
            for i in range(node_count)
        ]
        return cls(agents=agents, clock=clock, **agent_kwargs)

    def attach_job_manager(self, job_manager: JobManager) -> None:
        self._job_manager = job_manager

    def is_remote(self, node_id: str) -> bool:
        return False

    def get_remote(self, node_id: str) -> None:
        return None

    def _on_state_change(self, node_id: str, old: NodeState, new: NodeState) -> None:
        self._state_changes.append((self.clock.now(), node_id, old, new))
        if new == NodeState.DEAD:
            self._handle_node_death(node_id)

    def _handle_node_death(self, dead_node_id: str) -> None:
        if self._job_manager is not None:
            self._job_manager.handle_node_death(dead_node_id)
            return

        for agent in self.agents:
            if agent.node_id == dead_node_id:
                agent.kill()

        orphaned = self.work_stealer.find_orphaned_tasks(
            list(self._tasks.values()),
            {dead_node_id},
        )
        if orphaned:
            nodes = self._live_nodes()
            self.work_stealer.steal(orphaned, nodes)

    def _live_nodes(self) -> list:
        return [
            a.to_node(self._health_registry.get_state(a.node_id))
            for a in self.agents
            if a.alive
        ]

    def submit(self, task: TaskSpec) -> Optional[str]:
        self._tasks[task.task_id] = task
        nodes = self._live_nodes()
        placement = self.placement_engine.place(task, nodes)
        if placement:
            task.assigned_node = placement.node_id
            task.state = TaskState.RUNNING
            for agent in self.agents:
                if agent.node_id == placement.node_id:
                    agent._assigned_tasks.append(task.task_id)
            return placement.node_id
        task.state = TaskState.PENDING
        return None

    def schedule_event(self, at: float, action: Callable[[], None], description: str = "") -> None:
        self._events.append(SimEvent(at=at, action=action, description=description))
        self._events.sort(key=lambda e: e.at)

    def run(self, until: float) -> None:
        while self.clock.now() < until:
            self._tick()
            self.clock.advance(self.tick_interval)

    def _tick(self) -> None:
        now = self.clock.now()

        while self._events and self._events[0].at <= now:
            event = self._events.pop(0)
            event.action()

        for agent in self.agents:
            if agent.alive:
                self._health_registry.record_heartbeat(agent.node_id)

        self._health_registry.evaluate_all()

        for task in self._tasks.values():
            if task.state == TaskState.RUNNING:
                task.progress = min(task.total_work, task.progress + self.tick_interval)
                if task.checkpoint:
                    self.checkpoint_manager.save(task, timestamp=now)

        for task in self._tasks.values():
            if task.state == TaskState.RUNNING and task.progress >= task.total_work:
                task.state = TaskState.COMPLETED

    def get_task(self, task_id: str) -> Optional[TaskSpec]:
        return self._tasks.get(task_id)

    def task_completed(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task is not None and task.state == TaskState.COMPLETED

    def cluster_stats(self) -> dict:
        nodes = self._live_nodes()
        return {
            "total_nodes": len(self.agents),
            "alive_nodes": sum(1 for a in self.agents if a.alive),
            "healthy_nodes": sum(1 for n in nodes if n.state == NodeState.HEALTHY),
            "total_cpu_cores": sum(n.resources.cpu_cores_total for n in nodes),
            "free_cpu_cores": sum(n.resources.cpu_cores_free for n in nodes),
            "total_ram_gb": sum(n.resources.ram_gb_total for n in nodes),
            "free_ram_gb": sum(n.resources.ram_gb_free for n in nodes),
            "tasks_running": sum(1 for t in self._tasks.values() if t.state == TaskState.RUNNING),
            "tasks_completed": sum(1 for t in self._tasks.values() if t.state == TaskState.COMPLETED),
        }
