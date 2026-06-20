from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Union
import json
import threading
import time

from mesh.execution.executor import TaskExecutor, TaskInterrupted
from mesh.models.enums import NodeState, TaskState
from mesh.models.job import Job, JobState
from mesh.models.task import TaskSpec
from mesh.proto import mesh_pb2
from mesh.recovery.replication import ReplicationManager
from mesh.recovery.speculation import SpeculativeExecutor
from mesh.recovery.work_stealing import WorkStealer
from mesh.sdk.decorator import MeshTask
from mesh.scheduler.rebalancing import Rebalancer
from mesh.sim.cluster import SimCluster
from mesh.driver.cluster import DriverCluster
from mesh.state.store import StateStore
from mesh.tasks.registry import get, register_mesh_task


class ClusterBackend(Protocol):
    checkpoint_manager: Any
    placement_engine: Any
    tasks: dict[str, TaskSpec]

    def submit(self, task: TaskSpec) -> Optional[str]: ...
    def live_nodes(self) -> list: ...
    def is_remote(self, node_id: str) -> bool: ...
    def get_remote(self, node_id: str) -> Any: ...
    def attach_job_manager(self, manager: object) -> None: ...


@dataclass
class JobHandle:
    job: Job
    manager: "JobManager"

    def wait(self, timeout: Optional[float] = None) -> Any:
        return self.manager.wait_for_job(self.job.job_id, timeout=timeout)

    def cancel(self) -> None:
        self.manager.cancel_job(self.job.job_id)

    @property
    def state(self) -> JobState:
        return self.job.state


@dataclass
class _RunningTask:
    spec: TaskSpec
    job: Job
    thread: Optional[threading.Thread] = None
    remote: bool = False


@dataclass
class JobManager:
    cluster: Union[SimCluster, DriverCluster]
    state_store: Optional[StateStore] = None
    speculation: SpeculativeExecutor = field(default_factory=SpeculativeExecutor)
    rebalancer: Rebalancer = field(default_factory=Rebalancer)
    leadership_check: Optional[Callable[[], bool]] = None
    executor: TaskExecutor = field(init=False)
    replication: ReplicationManager = field(default_factory=ReplicationManager)
    work_stealer: WorkStealer = field(init=False)
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _job_tasks: dict[str, list[TaskSpec]] = field(default_factory=dict, repr=False)
    _idempotency: dict[str, str] = field(default_factory=dict, repr=False)
    _running: dict[str, _RunningTask] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.executor = TaskExecutor(checkpoint_manager=self.cluster.checkpoint_manager)
        self.work_stealer = WorkStealer(
            placement_engine=self.cluster.placement_engine,
            checkpoint_manager=self.cluster.checkpoint_manager,
        )
        self.replication.placement_engine = self.cluster.placement_engine
        self.cluster.attach_job_manager(self)

    def _can_write(self) -> bool:
        if self.leadership_check is None:
            return True
        return self.leadership_check()

    def _persist_job(self, job: Job) -> None:
        if self.state_store and self._can_write():
            self.state_store.save_job(job)

    def _persist_task(self, task: TaskSpec) -> None:
        if self.state_store and self._can_write():
            self.state_store.save_task(task)
            cp = self.cluster.checkpoint_manager.load(task.task_id)
            if cp:
                self.state_store.save_checkpoint(cp)

    def resume_from_store(self, store: StateStore) -> None:
        for job in store.list_jobs():
            self._jobs[job.job_id] = job
            if job.idempotency_key:
                self._idempotency[job.idempotency_key] = job.job_id

        job_tasks: dict[str, list[TaskSpec]] = {}
        for task in store.list_tasks():
            try:
                task.fn = get(task.name)
            except KeyError:
                task.fn = None
            self._tasks()[task.task_id] = task
            if task.job_id:
                job_tasks.setdefault(task.job_id, []).append(task)

        for job_id, specs in job_tasks.items():
            self._job_tasks[job_id] = specs

        for task in store.list_tasks():
            if task.state != TaskState.RUNNING:
                continue
            cp = store.load_checkpoint(task.task_id)
            if cp:
                task.progress = cp.progress
                task.state_data = dict(cp.state_data)
            job = self._find_job_for_task(task)
            if job and not job.is_terminal():
                self._dispatch(task, job)

    def run_rebalance(self) -> int:
        actions = self.rebalancer.analyze(self._live_nodes(), list(self._tasks().values()))
        for action in actions:
            task = self._tasks().get(action.task_id)
            if not task:
                continue
            self._pause_task(task)
            task.assigned_node = action.to_node
            task.state = TaskState.MIGRATING
            job = self._find_job_for_task(task)
            if job:
                self._dispatch(task, job)
                self._persist_task(task)
        return len(actions)

    def check_speculation(self) -> int:
        stragglers = self.speculation.find_stragglers(list(self._tasks().values()))
        launched = 0
        for spec in stragglers:
            job = self._find_job_for_task(spec)
            if not job or job.is_terminal():
                continue
            from dataclasses import replace
            import uuid
            dup = replace(spec, task_id=str(uuid.uuid4()), replica_index=spec.replica_index + 100)
            dup.state = TaskState.PENDING
            dup.assigned_node = None
            self._tasks()[dup.task_id] = dup
            node_id = self.cluster.submit(dup)
            if node_id:
                self.speculation.mark_speculative(spec.task_id, dup.task_id)
                self._dispatch(dup, job)
                self._persist_task(dup)
                launched += 1
        return launched

    def _tasks(self) -> dict[str, TaskSpec]:
        if isinstance(self.cluster, SimCluster):
            return self.cluster._tasks
        return self.cluster.tasks

    def _live_nodes(self) -> list:
        if isinstance(self.cluster, SimCluster):
            return self.cluster._live_nodes()
        return self.cluster.live_nodes()

    def submit(
        self,
        mesh_task: MeshTask | Callable,
        *,
        async_: bool = False,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Any | JobHandle:
        if not isinstance(mesh_task, MeshTask):
            mesh_task = getattr(mesh_task, "_mesh_task", None)
            if mesh_task is None:
                raise TypeError("Expected @task-decorated function or MeshTask")

        register_mesh_task(mesh_task)

        if idempotency_key and idempotency_key in self._idempotency:
            existing_id = self._idempotency[idempotency_key]
            job = self._jobs[existing_id]
            if async_:
                return JobHandle(job=job, manager=self)
            return self.wait_for_job(existing_id, timeout=timeout)

        job = Job(name=mesh_task.name, idempotency_key=idempotency_key)
        self._jobs[job.job_id] = job
        if idempotency_key:
            self._idempotency[idempotency_key] = job.job_id

        base_spec = mesh_task.to_spec(job_id=job.job_id)
        if mesh_task.replicas > 1:
            specs = self.replication.create_replica_specs(
                base_spec, job.job_id, mesh_task.replicas
            )
        else:
            specs = [base_spec]

        job.task_ids = [s.task_id for s in specs]
        self._job_tasks[job.job_id] = specs
        tasks = self._tasks()
        for spec in specs:
            tasks[spec.task_id] = spec

        nodes = self._live_nodes()
        if mesh_task.replicas > 1:
            placements = self.replication.assign_to_different_nodes(specs, nodes)
        else:
            placements = []
            for spec in specs:
                node_id = self.cluster.submit(spec)
                placements.append((spec, node_id))

        job.state = JobState.RUNNING
        self._persist_job(job)
        for spec, node_id in placements:
            self._persist_task(spec)
            if node_id:
                self._dispatch(spec, job)

        if async_:
            return JobHandle(job=job, manager=self)
        return self.wait_for_job(job.job_id, timeout=timeout)

    def wait_for_job(self, job_id: str, timeout: Optional[float] = None) -> Any:
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Unknown job: {job_id}")
            if job.is_terminal():
                break
            if deadline and time.monotonic() > deadline:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
            time.sleep(0.005)

        if job.state == JobState.FAILED:
            raise RuntimeError(job.error or "Job failed")
        if job.state == JobState.CANCELLED:
            raise RuntimeError("Job was cancelled")
        return job.result

    def cancel_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for spec in self._job_tasks.get(job_id, []):
            self._cancel_task(spec)
            spec.state = TaskState.FAILED
        job.state = JobState.CANCELLED

    def handle_preemption(self, node_id: str) -> None:
        interrupted_ids: list[str] = []
        with self._lock:
            for running in self._running.values():
                if running.spec.assigned_node == node_id:
                    self._pause_task(running.spec)
                    interrupted_ids.append(running.spec.task_id)

        deadline = time.monotonic() + 2.0
        while interrupted_ids and time.monotonic() < deadline:
            with self._lock:
                if not any(tid in self._running for tid in interrupted_ids):
                    break
            time.sleep(0.005)

        all_tasks = list(self._tasks().values())
        orphaned = self.work_stealer.find_orphaned_tasks(all_tasks, {node_id})
        if not orphaned:
            return

        nodes = [n for n in self._live_nodes() if n.node_id != node_id]
        stolen = self.work_stealer.steal(orphaned, nodes)
        for spec, new_node in stolen:
            if new_node is None:
                continue
            job = self._find_job_for_task(spec)
            if job and not job.is_terminal():
                self._dispatch(spec, job)

    def handle_node_death(self, dead_node_id: str) -> None:
        if isinstance(self.cluster, SimCluster):
            for agent in self.cluster.agents:
                if agent.node_id == dead_node_id:
                    agent.kill()
        else:
            self.cluster.update_node_state(dead_node_id, NodeState.DEAD)
            self.cluster._remote_agents.pop(dead_node_id, None)
            self.cluster.health_registry.force_state(dead_node_id, NodeState.DEAD)

        interrupted_ids: list[str] = []
        with self._lock:
            for running in self._running.values():
                if running.spec.assigned_node == dead_node_id:
                    self._pause_task(running.spec)
                    interrupted_ids.append(running.spec.task_id)

        deadline = time.monotonic() + 2.0
        while interrupted_ids and time.monotonic() < deadline:
            with self._lock:
                if not any(tid in self._running for tid in interrupted_ids):
                    break
            time.sleep(0.005)

        all_tasks = list(self._tasks().values())
        orphaned = self.work_stealer.find_orphaned_tasks(all_tasks, {dead_node_id})
        if not orphaned:
            return

        nodes = self._live_nodes()
        stolen = self.work_stealer.steal(orphaned, nodes)
        for spec, new_node in stolen:
            if new_node is None:
                continue
            job = self._find_job_for_task(spec)
            if job and not job.is_terminal():
                self._dispatch(spec, job)

    def _dispatch(self, spec: TaskSpec, job: Job) -> None:
        self.speculation.record_start(spec.task_id)
        if spec.assigned_node and self.cluster.is_remote(spec.assigned_node):
            self._dispatch_remote(spec, job)
        elif spec.fn:
            self._start_local_execution(spec, job)

    def _dispatch_remote(self, spec: TaskSpec, job: Job) -> None:
        remote = self.cluster.get_remote(spec.assigned_node)
        if not remote:
            return

        with self._lock:
            if spec.task_id in self._running:
                return
            self._running[spec.task_id] = _RunningTask(spec=spec, job=job, remote=True)

        cp = self.cluster.checkpoint_manager.load(spec.task_id)
        resume_progress = cp.progress if cp else spec.progress
        resume_state = json.dumps(cp.state_data if cp else spec.state_data)

        req = mesh_pb2.TaskAssignment(
            task_id=spec.task_id,
            job_id=spec.job_id or "",
            task_name=spec.name,
            cpu_cores=spec.requirements.cpu_cores,
            ram_gb=spec.requirements.ram_gb,
            gpu_count=spec.requirements.gpu_count,
            checkpoint=spec.checkpoint,
            checkpoint_interval=spec.checkpoint_interval,
            total_work=spec.total_work,
            resume_progress=resume_progress,
            resume_state_json=resume_state,
        )
        try:
            ack = remote.assign_task(req)
            if not ack.ok:
                spec.state = TaskState.FAILED
                self._on_task_failed(spec, job, ack.message)
                with self._lock:
                    self._running.pop(spec.task_id, None)
        except Exception as exc:
            spec.state = TaskState.FAILED
            self._on_task_failed(spec, job, str(exc))
            with self._lock:
                self._running.pop(spec.task_id, None)

    def _start_local_execution(self, spec: TaskSpec, job: Job) -> None:
        if spec.fn is None:
            return

        with self._lock:
            if spec.task_id in self._running:
                return
            running = _RunningTask(spec=spec, job=job)
            self._running[spec.task_id] = running

        def run() -> None:
            try:
                self.executor.clear_interrupt(spec.task_id)
                result = self.executor.execute(spec.fn, spec)
                if spec.state == TaskState.COMPLETED:
                    self._on_task_complete(spec, job, result)
            except TaskInterrupted:
                pass
            except Exception as exc:
                spec.state = TaskState.FAILED
                self._on_task_failed(spec, job, str(exc))
            finally:
                with self._lock:
                    self._running.pop(spec.task_id, None)

        thread = threading.Thread(target=run, daemon=True, name=f"mesh-{spec.name}")
        running.thread = thread
        thread.start()

    def _pause_task(self, spec: TaskSpec) -> None:
        if spec.assigned_node and self.cluster.is_remote(spec.assigned_node):
            remote = self.cluster.get_remote(spec.assigned_node)
            if remote:
                remote.pause_task(mesh_pb2.TaskPauseRequest(task_id=spec.task_id, reason="preemption"))
        else:
            self.executor.interrupt(spec.task_id)

    def _cancel_task(self, spec: TaskSpec) -> None:
        if spec.assigned_node and self.cluster.is_remote(spec.assigned_node):
            remote = self.cluster.get_remote(spec.assigned_node)
            if remote:
                remote.cancel_task(mesh_pb2.TaskCancelRequest(task_id=spec.task_id))
        else:
            self.executor.interrupt(spec.task_id)

    def _on_task_complete(self, spec: TaskSpec, job: Job, result: Any) -> None:
        with self._lock:
            self._running.pop(spec.task_id, None)
        self.speculation.clear(spec.task_id)
        dup_id = self.speculation.duplicate_id(spec.task_id)
        if dup_id:
            self._cancel_task(self._tasks()[dup_id])

        all_specs = self._job_tasks.get(job.job_id, [])
        if len(all_specs) > 1:
            to_cancel = self.replication.on_replica_complete(job, spec, all_specs)
            for other in to_cancel:
                self._cancel_task(other)
                other.state = TaskState.FAILED
        else:
            job.state = JobState.COMPLETED
        job.result = result
        self._persist_task(spec)
        self._persist_job(job)

    def _on_task_failed(self, spec: TaskSpec, job: Job, error: str) -> None:
        with self._lock:
            self._running.pop(spec.task_id, None)
        self.speculation.clear(spec.task_id)

        all_specs = self._job_tasks.get(job.job_id, [])
        if len(all_specs) > 1:
            if not self.replication.on_replica_failure(job, spec, all_specs):
                return
        else:
            job.state = JobState.FAILED
            job.error = error
        self._persist_task(spec)
        self._persist_job(job)

    def _find_job_for_task(self, spec: TaskSpec) -> Optional[Job]:
        if spec.job_id:
            return self._jobs.get(spec.job_id)
        for job_id, specs in self._job_tasks.items():
            if spec.task_id in {s.task_id for s in specs}:
                return self._jobs.get(job_id)
        return None

    def submit_remote_by_name(
        self,
        task_name: str,
        *,
        async_: bool = False,
        timeout: Optional[float] = None,
        total_work: float = 1000,
        checkpoint: bool = True,
    ) -> Any | JobHandle:
        """Submit a registry task to remote agents (no local fn required)."""
        from mesh.models.task import ResourceRequirements

        spec = TaskSpec(
            name=task_name,
            requirements=ResourceRequirements(cpu_cores=1, ram_gb=1),
            checkpoint=checkpoint,
            total_work=total_work,
        )
        mesh_task = MeshTask(
            fn=lambda: None,
            name=task_name,
            checkpoint=checkpoint,
            total_work=total_work,
        )
        job = Job(name=task_name)
        self._jobs[job.job_id] = job
        spec.job_id = job.job_id
        spec.fn = None
        self._job_tasks[job.job_id] = [spec]
        self._tasks()[spec.task_id] = spec

        node_id = self.cluster.submit(spec)
        job.state = JobState.RUNNING
        job.task_ids = [spec.task_id]
        if node_id:
            self._dispatch_remote(spec, job)

        if async_:
            return JobHandle(job=job, manager=self)
        return self.wait_for_job(job.job_id, timeout=timeout)

    def submit_notebook_cell(
        self,
        code: str,
        *,
        language: str = "python",
        timeout: Optional[float] = 120,
    ) -> dict[str, Any]:
        """Execute a notebook cell on a remote agent."""
        from mesh.models.task import ResourceRequirements

        spec = TaskSpec(
            name="notebook.exec",
            requirements=ResourceRequirements(cpu_cores=1, ram_gb=0.5),
            checkpoint=False,
            total_work=1,
            state_data={"code": code, "language": language},
        )
        job = Job(name=f"notebook-{language}")
        self._jobs[job.job_id] = job
        spec.job_id = job.job_id
        self._job_tasks[job.job_id] = [spec]
        self._tasks()[spec.task_id] = spec
        self._persist_job(job)
        self._persist_task(spec)

        node_id = self.cluster.submit(spec)
        if not node_id:
            raise RuntimeError("No healthy workers available — start mesh-agent on a machine")
        job.state = JobState.RUNNING
        job.task_ids = [spec.task_id]
        self._dispatch_remote(spec, job)
        result = self.wait_for_job(job.job_id, timeout=timeout)
        if isinstance(result, dict):
            return result
        return {"stdout": str(result), "stderr": "", "error": None, "result": result}
