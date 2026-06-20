"""Tests for preemption detection."""

from mesh.agent.monitor import ResourceSnapshot
from mesh.agent.preemption import PreemptionDetector


class TestPreemptionDetector:
    def test_no_trigger_on_idle(self):
        det = PreemptionDetector(cpu_threshold=0.85, consecutive_triggers=2)
        snap = ResourceSnapshot(
            cpu_cores_total=8,
            cpu_cores_free=6,
            ram_gb_total=16,
            ram_gb_free=8,
            cpu_utilization=0.2,
            user_active=False,
        )
        triggered, reason = det.check(snap)
        assert not triggered

    def test_trigger_on_cpu_spike(self):
        det = PreemptionDetector(cpu_threshold=0.85, consecutive_triggers=2)
        snap = ResourceSnapshot(
            cpu_cores_total=8,
            cpu_cores_free=1,
            ram_gb_total=16,
            ram_gb_free=8,
            cpu_utilization=0.95,
        )
        det.check(snap)
        triggered, reason = det.check(snap)
        assert triggered
        assert "cpu_spike" in reason

    def test_trigger_on_user_active(self):
        det = PreemptionDetector()
        snap = ResourceSnapshot(
            cpu_cores_total=8,
            cpu_cores_free=2,
            ram_gb_total=16,
            ram_gb_free=8,
            cpu_utilization=0.6,
            user_active=True,
        )
        triggered, _ = det.check(snap)
        assert triggered
