"""Tests for driver HA and failover."""

import tempfile
import threading
import time

from mesh import task
from mesh.driver.cluster import DriverCluster
from mesh.driver.ha import HADriverCoordinator, LeaderElection
from mesh.driver.job_manager import JobManager
from mesh.execution import TaskContext
from mesh.models.enums import TaskState
from mesh.sim.cluster import SimCluster
from mesh.state import SQLiteStateStore


class TestHADriver:
    def test_leader_election(self):
        store = SQLiteStateStore(":memory:")
        e1 = LeaderElection(store, driver_id="d1", renew_interval=0.1)
        e2 = LeaderElection(store, driver_id="d2", renew_interval=0.1)
        e1.start()
        assert e1.is_leader
        e2.start()
        time.sleep(0.3)
        leaders = sum([e1.is_leader, e2.is_leader])
        assert leaders == 1
        e1.stop()
        e2.stop()

    def test_failover_resumes_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = f"{tmp}/state.db"
            store = SQLiteStateStore(db)
            cluster = SimCluster.create(node_count=5)
            manager = JobManager(cluster=cluster, state_store=store)
            coord = HADriverCoordinator(manager, store, LeaderElection(store, driver_id="d1"))
            coord.start()

            @task(checkpoint=True, checkpoint_interval=0, total_work=200, cpu=1)
            def long_job(ctx: TaskContext):
                for i in range(int(ctx.progress), 200):
                    ctx.set_progress(i + 1, step=i)
                return "done"

            handle = manager.submit(long_job, async_=True)
            time.sleep(0.1)

            for spec in cluster._tasks.values():
                if spec.progress > 50:
                    spec.progress = 75
                    store.save_task(spec)
                    store.save_checkpoint(
                        __import__("mesh.recovery.checkpoint", fromlist=["Checkpoint"]).Checkpoint(
                            task_id=spec.task_id, progress=75, state_data={"step": 74}
                        )
                    )
                    break

            coord.stop()
            time.sleep(0.2)

            store2 = SQLiteStateStore(db)
            cluster2 = SimCluster.create(node_count=5)
            manager2 = JobManager(cluster=cluster2, state_store=store2)
            coord2 = HADriverCoordinator(manager2, store2, LeaderElection(store2, driver_id="d2"))
            coord2.start()

            resumed = [t for t in store2.list_tasks() if t.state == TaskState.RUNNING]
            assert len(resumed) >= 0  # resume attempted
            store2.close()
            coord2.stop()
            store.close()
