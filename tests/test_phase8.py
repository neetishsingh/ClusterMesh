"""Phase 8 — memory fabric, 1000-node SLA, dogfood."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mesh.api.app import create_app
from mesh.api.context import AppContext
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.memory.fabric import MemoryFabric
from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources
from mesh.scheduler.benchmark import benchmark_placement


def _nodes(count: int = 3) -> list[Node]:
    return [
        Node(
            node_id=f"n{i}",
            hostname=f"host-{i}",
            resources=NodeResources(
                cpu_cores_total=8,
                cpu_cores_free=4,
                ram_gb_total=32,
                ram_gb_free=float(20 + i * 10),
            ),
            state=NodeState.HEALTHY,
            location="local",
        )
        for i in range(count)
    ]


class TestMemoryFabric:
    def test_pool_aggregation(self):
        fabric = MemoryFabric()
        stats = fabric.pool_stats(_nodes(3))
        assert stats.total_gb == 96.0
        assert stats.free_gb == 20 + 30 + 40

    def test_allocate_across_nodes(self):
        fabric = MemoryFabric()
        alloc = fabric.allocate(50.0, _nodes(3), owner="job-1")
        assert alloc is not None
        assert alloc.total_gb == 50.0
        assert len(alloc.segments) >= 1
        assert sum(s.size_gb for s in alloc.segments) == pytest.approx(50.0)

    def test_release_frees_pool(self):
        fabric = MemoryFabric()
        nodes = _nodes(3)
        alloc = fabric.allocate(30.0, nodes)
        assert alloc is not None
        free_after = fabric.pool_stats(nodes).free_gb
        fabric.release(alloc.allocation_id)
        free_restored = fabric.pool_stats(nodes).free_gb
        assert free_restored > free_after

    def test_insufficient_memory(self):
        fabric = MemoryFabric()
        assert fabric.allocate(500.0, _nodes(2)) is None


class TestPlacementSLA:
    def test_1000_node_p99_under_100ms(self):
        result = benchmark_placement(node_count=1000, iterations=100, sla_ms=100.0)
        assert result.passed, f"p99={result.p99_ms}ms exceeds 100ms SLA"
        assert result.node_count == 1000

    def test_100_node_fast(self):
        result = benchmark_placement(node_count=100, iterations=50, sla_ms=100.0)
        assert result.passed


class TestMemoryAPI:
    def test_memory_endpoints(self):
        cluster = DriverCluster()
        for n in _nodes(2):
            cluster.register_node(n)
        ctx = AppContext(
            cluster=cluster,
            job_manager=JobManager(cluster=cluster),
            memory=MemoryFabric(),
        )
        client = TestClient(create_app(ctx))

        pool = client.get("/api/v1/memory/pool").json()
        assert pool["total_gb"] > 0

        r = client.post("/api/v1/memory/allocate", json={"size_gb": 10, "owner": "test"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        allocs = client.get("/api/v1/memory/allocations").json()["allocations"]
        assert len(allocs) == 1

        bench = client.get("/api/v1/scheduler/benchmark?nodes=500&iterations=20").json()
        assert "p99_ms" in bench
