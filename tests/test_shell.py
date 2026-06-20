"""Tests for remote shell execution."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from mesh.agent.shell import run_shell_command
from mesh.api.app import create_app
from mesh.api.context import AppContext
from mesh.api.events import EventBus
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources
from mesh.proto import mesh_pb2


class TestRunShellCommand:
    def test_echo(self):
        result = run_shell_command("echo hello")
        assert result["ok"] is True
        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0

    def test_empty_command(self):
        result = run_shell_command("   ")
        assert result["ok"] is False

    def test_failing_command(self):
        result = run_shell_command("exit 7")
        assert result["ok"] is False
        assert result["exit_code"] == 7


class TestShellAPI:
    def _client_with_remote(self):
        cluster = DriverCluster()
        manager = JobManager(cluster=cluster)
        bus = EventBus()
        ctx = AppContext(cluster=cluster, job_manager=manager, event_bus=bus)
        node = Node(
            node_id="n1",
            hostname="worker-1",
            resources=NodeResources(cpu_cores_total=8, cpu_cores_free=4, ram_gb_total=16, ram_gb_free=8),
            state=NodeState.HEALTHY,
        )
        remote = MagicMock()
        remote.run_shell.return_value = mesh_pb2.ShellCommandResponse(
            ok=True,
            exit_code=0,
            stdout="pyspark ok\n",
            stderr="",
            message="completed",
            duration_seconds=1.2,
        )
        cluster.register_node(node, remote=remote)
        return TestClient(create_app(ctx)), remote

    def test_shell_on_remote_agent(self):
        client, remote = self._client_with_remote()
        r = client.post(
            "/api/v1/nodes/n1/shell",
            json={"command": "python -c 'print(1)'"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "pyspark ok" in data["stdout"]
        remote.run_shell.assert_called_once()

    def test_shell_requires_command(self):
        cluster = DriverCluster()
        ctx = AppContext(cluster=cluster, job_manager=JobManager(cluster=cluster), event_bus=EventBus())
        client = TestClient(create_app(ctx))
        r = client.post("/api/v1/nodes/n1/shell", json={"command": ""})
        assert r.status_code == 200
        assert r.json()["ok"] is False
