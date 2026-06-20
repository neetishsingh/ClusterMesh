"""Tests for FastAPI dashboard and REST API."""

from fastapi.testclient import TestClient

from mesh.api.app import create_app
from mesh.api.context import AppContext
from mesh.api.events import EventBus
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources


def _client() -> TestClient:
    cluster = DriverCluster()
    manager = JobManager(cluster=cluster)
    bus = EventBus()
    ctx = AppContext(cluster=cluster, job_manager=manager, event_bus=bus)
    cluster.register_node(
        Node(
            node_id="n1",
            hostname="worker-1",
            resources=NodeResources(cpu_cores_total=8, cpu_cores_free=4, ram_gb_total=16, ram_gb_free=8),
            state=NodeState.HEALTHY,
        )
    )
    return TestClient(create_app(ctx))


class TestFastAPI:
    def test_cluster_status(self):
        client = _client()
        r = client.get("/api/v1/cluster/status")
        assert r.status_code == 200
        data = r.json()
        assert data["healthy_nodes"] == 1
        assert "cpu_utilization_pct" in data
        assert isinstance(data["cpu_utilization_pct"], (int, float))
        assert "site_id" not in data or data.get("total_nodes") == 1

    def test_nodes_list(self):
        client = _client()
        r = client.get("/api/v1/nodes")
        assert r.status_code == 200
        nodes = r.json()["nodes"]
        assert len(nodes) == 1
        assert nodes[0]["hostname"] == "worker-1"

    def test_jobs_and_logs(self):
        client = _client()
        assert client.get("/api/v1/jobs").status_code == 200
        logs = client.get("/api/v1/logs").json()["logs"]
        assert isinstance(logs, list)

    def test_rebalance(self):
        client = _client()
        r = client.post("/api/v1/cluster/rebalance")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_libraries(self):
        client = _client()
        r = client.get("/api/v1/libraries")
        assert r.status_code == 200
        assert isinstance(r.json()["libraries"], list)

    def test_install_library(self):
        client = _client()
        r = client.post("/api/v1/libraries/install", json={"package_name": "numpy", "version": "2.0"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "install_id" in data

    def test_node_actions(self):
        client = _client()
        assert client.post("/api/v1/nodes/n1/pause").status_code == 200
        assert client.post("/api/v1/nodes/n1/drain").status_code == 200

    def test_savings_metrics(self):
        client = _client()
        r = client.get("/api/v1/metrics/savings")
        assert r.status_code == 200
        assert "estimated_monthly_savings_usd" in r.json()

    def test_notebook_execute_local_fallback(self):
        """Notebook runs on driver when mesh workers cannot accept the task."""
        cluster = DriverCluster()
        manager = JobManager(cluster=cluster)
        ctx = AppContext(cluster=cluster, job_manager=manager, event_bus=EventBus())
        cluster.register_node(
            Node(
                node_id="n1",
                hostname="worker-1",
                resources=NodeResources(
                    cpu_cores_total=8,
                    cpu_cores_free=4,
                    ram_gb_total=8,
                    ram_gb_free=0.3,
                ),
                state=NodeState.HEALTHY,
            )
        )
        client = TestClient(create_app(ctx))
        r = client.post(
            "/api/v1/notebook/execute",
            json={"code": 'print("ok")', "language": "python", "mode": "mesh"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "local"
        assert data["node"] == "driver"
        assert "ok" in data["stdout"]
        assert data["error"] is None

    def test_notebook_status_counts_runnable_workers(self):
        cluster = DriverCluster()
        manager = JobManager(cluster=cluster)
        ctx = AppContext(cluster=cluster, job_manager=manager, event_bus=EventBus())
        cluster.register_node(
            Node(
                node_id="n1",
                hostname="worker-1",
                resources=NodeResources(
                    cpu_cores_total=8,
                    cpu_cores_free=4,
                    ram_gb_total=16,
                    ram_gb_free=8,
                ),
                state=NodeState.HEALTHY,
            )
        )
        client = TestClient(create_app(ctx))
        status = client.get("/api/v1/notebook/status").json()
        assert status["workers_available"] == 1
        assert status["local_available"] is True
