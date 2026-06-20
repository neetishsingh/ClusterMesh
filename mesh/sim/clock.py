from __future__ import annotations


class SimClock:
    """Deterministic injectable clock for simulation and testing."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def now(self) -> float:
        return self._time

    def advance(self, seconds: float) -> float:
        self._time += seconds
        return self._time

    def set(self, timestamp: float) -> None:
        self._time = timestamp

    @property
    def time(self) -> float:
        return self._time
