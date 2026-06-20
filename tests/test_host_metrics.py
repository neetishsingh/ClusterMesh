"""Tests for macOS-style host metrics collection."""

from unittest.mock import MagicMock, patch

from mesh.agent.host_metrics import collect_host_metrics


class TestHostMetrics:
    def test_minimal_without_psutil(self):
        with patch("mesh.agent.host_metrics.psutil", None):
            data = collect_host_metrics(cpu_utilization=0.42)
            assert data["cpu"]["utilization_pct"] == 42.0

    def test_cpu_breakdown_from_times(self):
        times = MagicMock(user=12.5, system=6.0, idle=81.5)
        with patch("mesh.agent.host_metrics.psutil", MagicMock()):
            data = collect_host_metrics(cpu_utilization=0.18, cpu_times=times)
            assert data["cpu"]["user_pct"] == 12.5
            assert data["cpu"]["system_pct"] == 6.0
            assert data["cpu"]["idle_pct"] == 81.5
