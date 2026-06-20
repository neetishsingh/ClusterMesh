"""Tests for SDK decorator and submit API."""

import time

import pytest

from mesh import submit, task
from mesh.execution import TaskContext
from mesh.models.enums import TaskState
from mesh.driver.job_manager import JobManager
from mesh.sdk import reset_defaults
from mesh.sdk.units import parse_bandwidth, parse_bytes
from mesh.sim.cluster import SimCluster


@pytest.fixture(autouse=True)
def clean_defaults():
    reset_defaults()
    yield
    reset_defaults()


class TestUnits:
    def test_parse_gb(self):
        assert parse_bytes("64GB") == 64.0

    def test_parse_numeric(self):
        assert parse_bytes(32) == 32.0

    def test_parse_bandwidth(self):
        assert parse_bandwidth("10Gbps") == 10.0


class TestTaskDecorator:
    def test_decorator_creates_mesh_task(self):
        @task(cpu=4, ram="8GB", checkpoint=True)
        def my_job(ctx: TaskContext):
            return 42

        assert my_job.name == "my_job"
        assert my_job.requirements.cpu_cores == 4
        assert my_job.requirements.ram_gb == 8.0
        assert my_job.checkpoint is True

    def test_to_spec(self):
        @task(cpu=2, gpu=1, vram="24GB", pool="gpu")
        def gpu_job(ctx: TaskContext):
            pass

        spec = gpu_job.to_spec()
        assert spec.requirements.gpu_count == 1
        assert spec.requirements.vram_gb == 24.0
        assert spec.pool.value == "gpu"


class TestSubmit:
    def test_submit_simple_function(self):
        @task()
        def add_one():
            return 1

        cluster = SimCluster.create(node_count=5)
        result = submit(add_one, cluster=cluster)
        assert result == 1

    def test_submit_with_context(self):
        @task(checkpoint=True, checkpoint_interval=0, total_work=100)
        def counter(ctx: TaskContext):
            for i in range(int(ctx.progress), 100):
                ctx.set_progress(i + 1)
            return "done"

        cluster = SimCluster.create(node_count=5)
        result = submit(counter, cluster=cluster)
        assert result == "done"

    def test_submit_async(self):
        @task()
        def slow():
            time.sleep(0.05)
            return "ok"

        cluster = SimCluster.create(node_count=5)
        handle = submit(slow, async_=True, cluster=cluster)
        assert handle.wait(timeout=5) == "ok"

    def test_idempotency_key(self):
        @task()
        def once():
            return "first"

        cluster = SimCluster.create(node_count=5)
        manager = JobManager(cluster=cluster)
        r1 = manager.submit(once, idempotency_key="key-1")
        r2 = manager.submit(once, idempotency_key="key-1")
        assert r1 == r2
