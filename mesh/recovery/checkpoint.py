from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mesh.models.task import TaskSpec


@dataclass
class Checkpoint:
    task_id: str
    progress: float
    state_data: dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class CheckpointManager:
    """In-memory checkpoint store (Phase 2 — will move to durable storage)."""

    _checkpoints: dict[str, Checkpoint] = field(default_factory=dict, repr=False)

    def save(self, task: TaskSpec, state_data: Optional[dict] = None, timestamp: float = 0.0) -> Checkpoint:
        cp = Checkpoint(
            task_id=task.task_id,
            progress=task.progress,
            state_data=state_data or {},
            timestamp=timestamp,
        )
        self._checkpoints[task.task_id] = cp
        return cp

    def load(self, task_id: str) -> Optional[Checkpoint]:
        return self._checkpoints.get(task_id)

    def restore_progress(self, task: TaskSpec) -> TaskSpec:
        cp = self.load(task.task_id)
        if cp:
            task.progress = cp.progress
            task.state_data = dict(cp.state_data)
        return task

    def restore(self, task: TaskSpec) -> TaskSpec:
        """Restore progress and user state from last checkpoint."""
        return self.restore_progress(task)
