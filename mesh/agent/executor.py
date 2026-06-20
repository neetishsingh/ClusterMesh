from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import json
import threading

from mesh.execution.executor import TaskContext, TaskExecutor, TaskInterrupted
from mesh.models.enums import TaskState
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.recovery.checkpoint import CheckpointManager
from mesh.tasks.registry import get


@dataclass
class AgentTaskRunner:
    """Runs assigned tasks locally on the agent."""

    checkpoint_manager: CheckpointManager = field(default_factory=CheckpointManager)
    executor: TaskExecutor = field(init=False)
    on_progress: Optional[Callable[[TaskSpec], None]] = None
    on_complete: Optional[Callable[[TaskSpec, Any, Optional[str]], None]] = None

    _running: dict[str, threading.Thread] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.executor = TaskExecutor(checkpoint_manager=self.checkpoint_manager)

    def assign(self, assignment: dict) -> bool:
        task_id = assignment["task_id"]
        with self._lock:
            if task_id in self._running:
                return False

        spec = TaskSpec(
            name=assignment["task_name"],
            task_id=task_id,
            job_id=assignment.get("job_id"),
            requirements=ResourceRequirements(
                cpu_cores=assignment.get("cpu_cores", 1),
                ram_gb=assignment.get("ram_gb", 1),
                gpu_count=assignment.get("gpu_count", 0),
            ),
            checkpoint=assignment.get("checkpoint", False),
            checkpoint_interval=assignment.get("checkpoint_interval", 30),
            total_work=assignment.get("total_work", 1),
            progress=assignment.get("resume_progress", 0),
            state_data=json.loads(assignment.get("resume_state_json") or "{}"),
        )

        if assignment.get("resume_progress"):
            self.checkpoint_manager.save(spec, state_data=spec.state_data)

        fn = get(assignment["task_name"])

        def progress_hook(progress: float, state: dict) -> None:
            spec.progress = progress
            spec.state_data = state
            if self.on_progress:
                self.on_progress(spec)

        def run() -> None:
            try:
                ctx = TaskContext(
                    task_spec=spec,
                    checkpoint_manager=self.checkpoint_manager,
                    total_work=spec.total_work,
                )
                ctx.restore_from_checkpoint()

                original_set = ctx.set_progress

                def tracked_set(value: float, **state: Any) -> None:
                    original_set(value, **state)
                    if self.on_progress:
                        self.on_progress(spec)

                ctx.set_progress = tracked_set  # type: ignore[method-assign]

                from mesh.execution.executor import _accepts_context
                if _accepts_context(fn):
                    result = fn(ctx)
                else:
                    result = fn()

                if spec.progress < spec.total_work:
                    spec.progress = spec.total_work
                spec.state = TaskState.COMPLETED
                if self.on_complete:
                    self.on_complete(spec, result, None)
            except TaskInterrupted:
                if self.on_complete:
                    self.on_complete(spec, None, "interrupted")
            except Exception as exc:
                spec.state = TaskState.FAILED
                if self.on_complete:
                    self.on_complete(spec, None, str(exc))
            finally:
                with self._lock:
                    self._running.pop(task_id, None)

        thread = threading.Thread(target=run, daemon=True, name=f"agent-{task_id[:8]}")
        with self._lock:
            self._running[task_id] = thread
        thread.start()
        return True

    def pause(self, task_id: str) -> None:
        self.executor.interrupt(task_id)

    def cancel(self, task_id: str) -> None:
        self.executor.interrupt(task_id)
        with self._lock:
            self._running.pop(task_id, None)

    def running_count(self) -> int:
        with self._lock:
            return len(self._running)
