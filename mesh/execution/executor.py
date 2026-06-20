from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import inspect
import threading

from mesh.models.enums import TaskState
from mesh.recovery.checkpoint import CheckpointManager


class TaskInterrupted(Exception):
    """Raised when a task is interrupted for migration or node failure."""


@dataclass
class TaskContext:
    """
    Runtime context passed to @task functions.

    Tracks progress and user state for checkpoint/resume.
    """

    task_spec: TaskSpec
    checkpoint_manager: CheckpointManager
    total_work: float = 1.0
    interrupt: threading.Event = field(default_factory=threading.Event)
    _progress: float = 0.0
    _state: dict[str, Any] = field(default_factory=dict)
    _last_checkpoint_at: float = 0.0

    @property
    def task_id(self) -> str:
        return self.task_spec.task_id

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def restore_from_checkpoint(self) -> bool:
        cp = self.checkpoint_manager.load(self.task_id)
        if cp is None:
            return False
        self._progress = cp.progress
        self._state = dict(cp.state_data)
        self.task_spec.progress = cp.progress
        self.task_spec.state_data = dict(cp.state_data)
        return True

    def set_progress(self, value: float, **state: Any) -> None:
        self._check_interrupt()
        self._progress = min(value, self.total_work)
        self.task_spec.progress = self._progress
        if state:
            self._state.update(state)
            self.task_spec.state_data = dict(self._state)

        if self.task_spec.checkpoint:
            now = self._current_time()
            if now - self._last_checkpoint_at >= self.task_spec.checkpoint_interval:
                self.checkpoint()

    def checkpoint(self, **state: Any) -> None:
        if state:
            self._state.update(state)
            self.task_spec.state_data = dict(self._state)
        self.task_spec.progress = self._progress
        self.checkpoint_manager.save(
            self.task_spec,
            state_data=self._state,
            timestamp=self._current_time(),
        )
        self._last_checkpoint_at = self._current_time()

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def _check_interrupt(self) -> None:
        if self.interrupt.is_set():
            self.checkpoint()
            raise TaskInterrupted(f"Task {self.task_id} interrupted for migration")

    def _current_time(self) -> float:
        import time
        return time.monotonic()


@dataclass
class TaskExecutor:
    """Executes Python callables with checkpoint and interrupt support."""

    checkpoint_manager: CheckpointManager = field(default_factory=CheckpointManager)
    _interrupts: dict[str, threading.Event] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def interrupt(self, task_id: str) -> None:
        with self._lock:
            event = self._interrupts.get(task_id)
            if event:
                event.set()

    def clear_interrupt(self, task_id: str) -> None:
        with self._lock:
            event = self._interrupts.get(task_id)
            if event:
                event.clear()

    def execute(self, fn: Callable, spec: TaskSpec) -> Any:
        ctx = TaskContext(
            task_spec=spec,
            checkpoint_manager=self.checkpoint_manager,
            total_work=spec.total_work,
        )
        ctx.restore_from_checkpoint()

        with self._lock:
            self._interrupts[spec.task_id] = ctx.interrupt

        try:
            if _accepts_context(fn):
                result = fn(ctx)
            else:
                result = fn()
            if spec.progress < spec.total_work:
                spec.progress = spec.total_work
            spec.state = TaskState.COMPLETED
            return result
        except TaskInterrupted:
            return None
        finally:
            with self._lock:
                self._interrupts.pop(spec.task_id, None)


def _accepts_context(fn: Callable) -> bool:
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return False
    params = list(sig.parameters.values())
    if not params:
        return False
    first = params[0]
    return first.name in ("ctx", "context") or (
        first.annotation != inspect.Parameter.empty
        and "TaskContext" in str(first.annotation)
    )
