from __future__ import annotations

from dataclasses import dataclass, field
import statistics
import time

from mesh.models.enums import TaskState
from mesh.models.task import TaskSpec


@dataclass
class SpeculativeExecutor:
    """
    Straggler mitigation — duplicate slow tasks on another node.

    Trigger: runtime > median × multiplier (default 1.5×).
    """

    multiplier: float = 1.5
    min_runtime_seconds: float = 2.0
    _start_times: dict[str, float] = field(default_factory=dict, repr=False)
    _speculative: dict[str, str] = field(default_factory=dict, repr=False)  # original -> duplicate id

    def record_start(self, task_id: str) -> None:
        self._start_times[task_id] = time.monotonic()

    def clear(self, task_id: str) -> None:
        self._start_times.pop(task_id, None)
        self._speculative.pop(task_id, None)

    def find_stragglers(self, tasks: list[TaskSpec]) -> list[TaskSpec]:
        running = [t for t in tasks if t.state == TaskState.RUNNING]
        if len(running) < 2:
            return []

        runtimes = []
        now = time.monotonic()
        for t in running:
            start = self._start_times.get(t.task_id)
            if start:
                runtimes.append(now - start)

        if not runtimes:
            return []

        median = statistics.median(runtimes)
        threshold = max(self.min_runtime_seconds, median * self.multiplier)
        stragglers = []
        for t in running:
            start = self._start_times.get(t.task_id)
            if start and (now - start) > threshold and t.task_id not in self._speculative:
                stragglers.append(t)
        return stragglers

    def mark_speculative(self, original_id: str, duplicate_id: str) -> None:
        self._speculative[original_id] = duplicate_id

    def duplicate_id(self, original_id: str) -> str | None:
        return self._speculative.get(original_id)
