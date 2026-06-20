"""Phase 2 integration tests — recovery and replication exit criteria."""

import threading
import time

import pytest

from mesh import task
from mesh.driver.job_manager import JobManager
from mesh.execution import TaskContext
from mesh.models.enums import TaskState
from mesh.models.task import TaskSpec
from mesh.sim.cluster import SimCluster


def _wait_for_progress(cluster: SimCluster, min_progress: float, timeout: float = 5.0) -> TaskSpec:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for spec in cluster._tasks.values():
            if spec.progress >= min_progress:
                return spec
        time.sleep(0.005)
    raise TimeoutError(f"No task reached progress {min_progress}")


class TestCheckpointRecovery:
    def test_650m_of_1b_survives_node_death(self):
        """
        Exit criteria: task at 650M/1B records survives node death;
        resumes from checkpoint, not from 0.
        """
        cluster = SimCluster.create(node_count=10)
        manager = JobManager(cluster=cluster)
        at_650 = threading.Event()

        @task(checkpoint=True, checkpoint_interval=0, total_work=1000, cpu=1, ram="1GB")
        def process_billion(ctx: TaskContext):
            start = int(ctx.progress)
            for i in range(start, 1000):
                ctx.set_progress(i + 1, records_processed=i + 1)
                if i + 1 == 650:
                    at_650.set()
                    time.sleep(0.5)
            return "done"

        handle = manager.submit(process_billion, async_=True)
        assert at_650.wait(timeout=5.0), "Task never reached 650"

        running = _wait_for_progress(cluster, min_progress=650)
        node_to_kill = running.assigned_node
        assert running.progress >= 650

        manager.handle_node_death(node_to_kill)

        result = handle.wait(timeout=5.0)
        assert result == "done"

        final_spec = next(iter(cluster._tasks.values()))
        assert final_spec.progress == 1000
        cp = cluster.checkpoint_manager.load(final_spec.task_id)
        assert cp.state_data.get("records_processed", 0) >= 650
        assert final_spec.assigned_node != node_to_kill

    def test_recovery_within_sla(self):
        """Reassignment and completion within 10 seconds."""
        cluster = SimCluster.create(node_count=10)
        manager = JobManager(cluster=cluster)
        at_200 = threading.Event()

        @task(checkpoint=True, checkpoint_interval=0, total_work=500, cpu=1)
        def workload(ctx: TaskContext):
            for i in range(int(ctx.progress), 500):
                ctx.set_progress(i + 1)
                if i + 1 == 200:
                    at_200.set()
                    time.sleep(0.3)
            return "ok"

        handle = manager.submit(workload, async_=True)
        assert at_200.wait(timeout=5.0)

        running = _wait_for_progress(cluster, min_progress=200)
        dead_node = running.assigned_node

        start = time.monotonic()
        manager.handle_node_death(dead_node)
        result = handle.wait(timeout=10.0)
        elapsed = time.monotonic() - start

        assert result == "ok"
        assert elapsed <= 10.0


class TestReplication:
    def test_replica_survives_primary_death(self):
        cluster = SimCluster.create(node_count=10)
        manager = JobManager(cluster=cluster)

        @task(replicas=2, checkpoint=True, checkpoint_interval=0, total_work=200, cpu=1)
        def critical_job(ctx: TaskContext):
            for i in range(int(ctx.progress), 200):
                time.sleep(0.001)
                ctx.set_progress(i + 1)
            return "success"

        handle = manager.submit(critical_job, async_=True)
        time.sleep(0.1)

        specs = list(cluster._tasks.values())
        assert len(specs) == 2
        nodes = {s.assigned_node for s in specs if s.assigned_node}
        assert len(nodes) == 2

        primary = specs[0]
        manager.handle_node_death(primary.assigned_node)

        result = handle.wait(timeout=10.0)
        assert result == "success"
        assert handle.job.state.value == 3  # COMPLETED

    def test_first_replica_wins(self):
        cluster = SimCluster.create(node_count=10)
        manager = JobManager(cluster=cluster)

        @task(replicas=2, total_work=1, cpu=1)
        def fast_job(ctx: TaskContext):
            ctx.set_progress(1)
            return "winner"

        result = manager.submit(fast_job)
        assert result == "winner"
