from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional
import uuid


class JobState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class Job:
    """A submitted unit of work, possibly replicated across nodes."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    state: JobState = JobState.PENDING
    task_ids: list[str] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
    completed_task_id: Optional[str] = None

    def is_terminal(self) -> bool:
        return self.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)
