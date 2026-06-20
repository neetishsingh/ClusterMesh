"""Tests for cluster-wide library installation."""

from unittest.mock import MagicMock

from mesh.api.events import EventBus
from mesh.driver.cluster import DriverCluster
from mesh.driver.library_installer import LibraryInstaller
from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources
from mesh.proto import mesh_pb2


class TestLibraryInstaller:
    def _cluster_with_agent(self) -> DriverCluster:
        cluster = DriverCluster()
        node = Node(
            node_id="n1",
            hostname="worker-1",
            resources=NodeResources(
                cpu_cores_total=4,
                cpu_cores_free=2,
                ram_gb_total=8,
                ram_gb_free=4,
            ),
            state=NodeState.HEALTHY,
        )
        remote = MagicMock()
        remote.node_id = "n1"
        remote.install_library.return_value = mesh_pb2.Ack(ok=True, message="Installed numpy 2.0")
        cluster.register_node(node, remote=remote)
        return cluster

    def test_install_on_agent(self):
        bus = EventBus()
        cluster = self._cluster_with_agent()
        installer = LibraryInstaller(cluster=cluster, event_bus=bus)
        result = installer.install("numpy", "2.0", pool="all", include_driver=False)
        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["ok"] is True
        assert "numpy" in cluster.get_node("n1").tags.get("libraries", "")

    def test_install_driver_only(self, monkeypatch):
        monkeypatch.setattr(
            "mesh.driver.library_installer.socket.gethostname",
            lambda: "driver-only-host",
        )
        bus = EventBus()
        cluster = DriverCluster()
        installer = LibraryInstaller(cluster=cluster, event_bus=bus)
        installer.driver_libraries.install = MagicMock(
            return_value=(MagicMock(name="requests", version="2.32"), "Successfully installed")
        )
        result = installer.install("requests", pool="all", include_driver=True)
        assert result["ok"] is True
        assert result["results"][0]["target"] == "driver"
