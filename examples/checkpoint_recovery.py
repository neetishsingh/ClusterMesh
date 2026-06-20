"""
Phase 2 example: submit a checkpointed task and survive node failure.

Run: python examples/checkpoint_recovery.py
"""

import threading
import time

from mesh import task, submit, TaskContext
from mesh.driver.job_manager import JobManager
from mesh.sim.cluster import SimCluster


def main() -> None:
    cluster = SimCluster.create(node_count=10)
    manager = JobManager(cluster=cluster)
    reached = threading.Event()

    @task(cpu=2, ram="4GB", checkpoint=True, checkpoint_interval=0, total_work=1000)
    def process_billion(ctx: TaskContext):
        start = int(ctx.progress)
        for i in range(start, 1000):
            ctx.set_progress(i + 1, records_processed=i + 1)
            if i + 1 == 650:
                reached.set()
                time.sleep(0.2)
        return "done"

    print("Submitting checkpointed task (simulating 1B records)...")
    handle = manager.submit(process_billion, async_=True)

    reached.wait(timeout=5)
    spec = next(iter(cluster._tasks.values()))
    dead_node = spec.assigned_node
    print(f"  Progress: {spec.progress:.0f}/1000 on {dead_node}")

    print(f"  Killing node {dead_node}...")
    manager.handle_node_death(dead_node)

    result = handle.wait(timeout=10)
    final = next(iter(cluster._tasks.values()))
    cp = cluster.checkpoint_manager.load(final.task_id)

    print(f"  Result: {result}")
    print(f"  Resumed on: {final.assigned_node}")
    print(f"  Final progress: {final.progress:.0f}")
    print(f"  Checkpoint records: {cp.state_data.get('records_processed', 0)}")
    print("  ✓ Survived node death without restarting from 0")


if __name__ == "__main__":
    main()
