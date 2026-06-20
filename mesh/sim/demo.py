"""Demo: run a simulated 50-node cluster with chaos injection."""

from mesh.models.enums import ResourcePool
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.sim.chaos import ChaosController
from mesh.sim.clock import SimClock
from mesh.sim.cluster import SimCluster


def main() -> None:
    clock = SimClock()
    cluster = SimCluster.create(node_count=50, clock=clock)

    tasks = [
        TaskSpec(
            name=f"etl-job-{i}",
            requirements=ResourceRequirements(cpu_cores=4, ram_gb=8),
            pool=ResourcePool.CPU,
            checkpoint=True,
            total_work=30.0,
        )
        for i in range(5)
    ]

    print("=" * 60)
    print("  ClusterMesh SimCluster Demo")
    print("=" * 60)

    stats = cluster.cluster_stats()
    print(f"\nCluster: {stats['total_nodes']} nodes, "
          f"{stats['total_cpu_cores']} cores, "
          f"{stats['total_ram_gb']:.0f} GB RAM")

    placed = 0
    for task in tasks:
        node = cluster.submit(task)
        if node:
            placed += 1
            print(f"  ✓ {task.name} → {node}")

    print(f"\nPlaced {placed}/{len(tasks)} tasks")

    chaos = ChaosController(cluster)
    chaos.kill_node("NODE-005", at=10.0)
    chaos.kill_node("NODE-012", at=15.0)
    chaos.preempt("NODE-003", at=20.0)

    print("\nRunning simulation (60s simulated time)...")
    print("  t=10s: kill NODE-005")
    print("  t=15s: kill NODE-012")
    print("  t=20s: preempt NODE-003")

    cluster.run(until=60.0)

    stats = cluster.cluster_stats()
    print(f"\nResults after 60s:")
    print(f"  Alive nodes:    {stats['alive_nodes']}/{stats['total_nodes']}")
    print(f"  Tasks running:  {stats['tasks_running']}")
    print(f"  Tasks completed: {stats['tasks_completed']}")

    if cluster._state_changes:
        print(f"\nState changes ({len(cluster._state_changes)}):")
        for t, node_id, old, new in cluster._state_changes[:10]:
            print(f"  t={t:.0f}s  {node_id}: {old.name} → {new.name}")

    for task in tasks:
        status = task.state.name
        progress = f"{task.progress_pct:.0f}%"
        node = task.assigned_node or "unassigned"
        print(f"  {task.name}: {status} ({progress}) on {node}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
