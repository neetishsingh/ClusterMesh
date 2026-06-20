"""Phase 6 — production backends, auth, discovery, chaos soak."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from mesh import task
from mesh.api.app import create_app
from mesh.api.auth import AuthConfig
from mesh.api.context import AppContext
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.execution import TaskContext
from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources
from mesh.state.factory import create_state_store
from mesh.state.redis_store import RedisStateStore
from mesh.sim.cluster import SimCluster


class TestStateFactory:
    def test_sqlite_factory(self, tmp_path):
        store = create_state_store(f"sqlite:///{tmp_path / 't.db'}")
        assert type(store).__name__ == "SQLiteStateStore"
        store.close()

    def test_sqlite_relative_path(self, tmp_path):
        store = create_state_store(f"sqlite:///{tmp_path / 'rel.db'}")
        assert type(store).__name__ == "SQLiteStateStore"
        store.close()

    def test_sqlite_three_slash_not_absolute_root(self, tmp_path):
        import os
        os.chdir(tmp_path)
        store = create_state_store("sqlite:///clustermesh.db")
        store.close()
        assert (tmp_path / "clustermesh.db").exists()

    def test_unsupported_url(self):
        with pytest.raises(ValueError):
            create_state_store("mysql://localhost/db")


class TestRedisStore:
    def test_redis_roundtrip(self):
        redis = pytest.importorskip("redis")
        try:
            client = redis.from_url("redis://localhost:6379/15", decode_responses=True)
            client.ping()
        except Exception:
            pytest.skip("Redis not available")

        store = RedisStateStore("redis://localhost:6379/15")
        from mesh.models.job import Job, JobState

        job = Job(job_id="j1", name="test", state=JobState.RUNNING)
        store.save_job(job)
        loaded = store.load_job("j1")
        assert loaded is not None
        assert loaded.name == "test"
        store.close()


class TestAuth:
    def test_validate_key(self):
        cfg = AuthConfig(api_key="secret-key", enabled=True)
        assert cfg.validate_key("secret-key")
        assert not cfg.validate_key("wrong")

    def test_auth_middleware_blocks(self):
        cluster = DriverCluster()
        ctx = AppContext(cluster=cluster, job_manager=JobManager(cluster=cluster))
        auth = AuthConfig(api_key="test-key", enabled=True)
        client = TestClient(create_app(ctx, auth=auth))
        assert client.get("/api/v1/cluster/status").status_code == 401
        r = client.get(
            "/api/v1/cluster/status",
            headers={"Authorization": "Bearer test-key"},
        )
        assert r.status_code == 200

    def test_tenant_header(self):
        cluster = DriverCluster()
        cluster.register_node(
            Node(
                node_id="n1",
                hostname="a",
                resources=NodeResources(4, 2, 8, 4),
                location="bangalore",
                tags={"tenant": "acme"},
            )
        )
        cluster.register_node(
            Node(
                node_id="n2",
                hostname="b",
                resources=NodeResources(4, 2, 8, 4),
                location="london",
                tags={"tenant": "other"},
            )
        )
        ctx = AppContext(cluster=cluster, job_manager=JobManager(cluster=cluster))
        client = TestClient(create_app(ctx))
        all_nodes = client.get("/api/v1/nodes").json()["nodes"]
        assert len(all_nodes) == 2
        filtered = client.get("/api/v1/nodes", headers={"X-Tenant-Id": "acme"}).json()["nodes"]
        assert len(filtered) == 1
        assert filtered[0]["hostname"] == "a"

    def test_sites_endpoint(self):
        cluster = DriverCluster()
        cluster.register_node(
            Node(
                node_id="n1",
                hostname="a",
                resources=NodeResources(4, 2, 8, 4),
                location="bangalore",
            )
        )
        ctx = AppContext(cluster=cluster, job_manager=JobManager(cluster=cluster))
        client = TestClient(create_app(ctx))
        sites = client.get("/api/v1/discovery/sites").json()["sites"]
        assert len(sites) == 1
        assert sites[0]["site"] == "bangalore"


class TestChaosSoak:
    """Short chaos soak — CI-friendly subset of 24h soak."""

    def test_cluster_survives_rapid_node_failures(self):
        cluster = SimCluster.create(node_count=12)
        manager = JobManager(cluster=cluster)

        @task(checkpoint=True, total_work=100, cpu=1, ram="1GB")
        def work(ctx: TaskContext):
            for i in range(int(ctx.progress), 100):
                ctx.set_progress(i + 1)
                time.sleep(0.002)

        handle = manager.submit(work, async_=True)
        time.sleep(0.3)

        for nid in ["NODE-001", "NODE-003", "NODE-005", "NODE-007"]:
            cluster._health_registry.force_state(nid, NodeState.DEAD)
            manager.handle_node_death(nid)

        stats = cluster.cluster_stats()
        assert stats["healthy_nodes"] >= 1
        assert len(cluster.agents) == 12
