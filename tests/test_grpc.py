"""Integration tests for gRPC driver ↔ agent communication."""

import socket
import threading
import time

import pytest

from mesh.agent.client import DriverClient
from mesh.agent.config import AgentConfig
from mesh.agent.daemon import AgentDaemon
from mesh.agent.executor import AgentTaskRunner
from mesh.agent.monitor import ResourceSnapshot
from mesh.agent.server import AgentServer
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.driver.server import DriverServer
import mesh.tasks.builtins  # noqa: F401


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def grpc_cluster():
    driver_port = _free_port()
    agent_port = _free_port()
    while agent_port == driver_port:
        agent_port = _free_port()

    driver_addr = f"127.0.0.1:{driver_port}"
    agent_addr = f"127.0.0.1:{agent_port}"

    cluster = DriverCluster()
    manager = JobManager(cluster=cluster)
    driver = DriverServer(address=f"127.0.0.1:{driver_port}", cluster=cluster, job_manager=manager)
    driver.start()

    config = AgentConfig(
        node_id="test-agent-1",
        driver_address=driver_addr,
        agent_address=agent_addr,
        preemptible=True,
    )
    daemon = AgentDaemon(config)

    agent_thread = threading.Thread(target=daemon.start, daemon=True)
    agent_thread.start()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if cluster.get_node("test-agent-1"):
            break
        time.sleep(0.05)
    else:
        driver.stop()
        daemon.stop()
        pytest.fail("Agent failed to register")

    yield cluster, manager, daemon, driver

    daemon.stop()
    driver.stop()


class TestGrpcIntegration:
    def test_agent_registers(self, grpc_cluster):
        cluster, _, _, _ = grpc_cluster
        node = cluster.get_node("test-agent-1")
        assert node is not None
        assert node.hostname

    def test_heartbeat(self, grpc_cluster):
        cluster, _, daemon, _ = grpc_cluster
        resp = daemon.driver.heartbeat()
        assert resp.ok

    def test_submit_remote_task(self, grpc_cluster):
        cluster, manager, _, _ = grpc_cluster
        result = manager.submit_remote_by_name(
            "builtin.counter",
            timeout=15,
            total_work=100,
        )
        assert result == {"count": 100}

    def test_resource_report_updates_cluster(self, grpc_cluster):
        cluster, _, daemon, _ = grpc_cluster
        snap = ResourceSnapshot(
            cpu_cores_total=16,
            cpu_cores_free=12,
            ram_gb_total=64,
            ram_gb_free=32,
            cpu_utilization=0.25,
        )
        daemon.driver.report_resources(snap)
        node = cluster.get_node("test-agent-1")
        assert node.resources.cpu_cores_total == 16
        assert node.resources.ram_gb_free == 32

    def test_submit_remote_task(self, grpc_cluster):
        cluster, manager, _, _ = grpc_cluster
        result = manager.submit_remote_by_name(
            "builtin.counter",
            timeout=15,
            total_work=100,
        )
        assert result == {"count": 100}

    def test_preemption_warning_accepted(self, grpc_cluster):
        cluster, manager, daemon, _ = grpc_cluster
        from mesh.models.enums import NodeState

        ack = daemon.driver.preemption_warning(0.95, "test_preemption")
        assert ack.ok
        node = cluster.get_node("test-agent-1")
        assert node.state == NodeState.PREEMPTED
