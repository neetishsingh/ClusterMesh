from __future__ import annotations

from dataclasses import dataclass, field

from mesh.agent.monitor import ResourceSnapshot


@dataclass
class PreemptionDetector:
    """
    Detects when the host user needs resources back.

    Triggers when CPU utilization exceeds threshold or user is actively working.
    """

    cpu_threshold: float = 0.85
    consecutive_triggers: int = 2
    _high_cpu_streak: int = field(default=0, repr=False)
    _last_triggered: bool = field(default=False, repr=False)

    def check(self, snapshot: ResourceSnapshot) -> tuple[bool, str]:
        reasons = []
        if snapshot.user_active and snapshot.cpu_utilization > 0.5:
            reasons.append("user_active")
        if snapshot.cpu_utilization >= self.cpu_threshold:
            self._high_cpu_streak += 1
        else:
            self._high_cpu_streak = 0

        if self._high_cpu_streak >= self.consecutive_triggers:
            reasons.append(f"cpu_spike:{snapshot.cpu_utilization:.0%}")

        triggered = len(reasons) > 0
        self._last_triggered = triggered
        return triggered, ",".join(reasons) if reasons else ""

    def reset(self) -> None:
        self._high_cpu_streak = 0
        self._last_triggered = False
