"""Tests for agent resource monitor."""

from unittest.mock import MagicMock, patch

from mesh.agent.monitor import ResourceMonitor, ResourceSnapshot, get_hostname


class TestResourceMonitor:
    def test_snapshot_without_psutil(self):
        with patch("mesh.agent.monitor.psutil", None):
            monitor = ResourceMonitor()
            snap = monitor.snapshot()
            assert snap.cpu_cores_total == 4
            assert snap.ram_gb_total == 16.0

    def test_snapshot_with_psutil(self):
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.side_effect = lambda logical=True: 8 if logical else 4
        mock_psutil.cpu_percent.side_effect = [0.0, 40.0, 40.0]
        mock_mem = MagicMock()
        mock_mem.total = 32 * 1024**3
        mock_mem.available = 16 * 1024**3
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.sensors_battery.return_value = None
        mock_psutil.cpu_times_percent.return_value = MagicMock(user=10.0, system=5.0, idle=85.0)

        with patch("mesh.agent.monitor.psutil", mock_psutil), patch(
            "mesh.agent.monitor.collect_host_metrics",
            return_value={"cpu": {}, "memory": {}, "processes": {"top": []}, "gpu": {"count": 0}},
        ):
            monitor = ResourceMonitor(min_sample_interval=0.0)
            snap = monitor.snapshot(force=True)
            assert snap.cpu_cores_total == 8
            assert snap.ram_gb_total == 32.0
            assert snap.ram_gb_free == 16.0
            assert snap.cpu_utilization == 0.4
            assert snap.host_metrics_json

    def test_snapshot_reuses_cached_reading(self):
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.cpu_percent.side_effect = [0.0, 50.0, 90.0]
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 8 * 1024**3
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_psutil.sensors_battery.return_value = None
        mock_psutil.cpu_times_percent.return_value = MagicMock(idle=80.0)

        with patch("mesh.agent.monitor.psutil", mock_psutil), patch(
            "mesh.agent.monitor.collect_host_metrics",
            return_value={"cpu": {}, "memory": {}, "processes": {"top": []}, "gpu": {"count": 0}},
        ):
            monitor = ResourceMonitor(min_sample_interval=60.0)
            first = monitor.snapshot(force=True)
            second = monitor.snapshot()
            assert first.cpu_utilization == 0.5
            assert second.cpu_utilization == 0.5
            assert mock_psutil.cpu_percent.call_count == 2

    def test_get_hostname(self):
        assert isinstance(get_hostname(), str)
