"""Tests for SimCluster, work stealing, and checkpoint recovery."""

from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.models.enums import TaskState
from mesh.recovery.checkpoint import CheckpointManager
from mesh.recovery.work_stealing import WorkStealer
from mesh.sim.agent import SimAgent
from mesh.sim.chaos import ChaosController
from mesh.sim.clock import SimClock
from mesh.sim.cluster import SimCluster


class TestSimCluster:
    def test_create_cluster(self):
        cluster = SimCluster.create(node_count=10)
        stats = cluster.cluster_stats()
        assert stats["total_nodes"] == 10
        assert stats["alive_nodes"] == 10

    def test_submit_and_run_task(self):
        clock = SimClock()
        cluster = SimCluster.create(node_count=5, clock=clock)
        task = TaskSpec(
            name="quick-job",
            requirements=ResourceRequirements(cpu_cores=2, ram_gb=4),
            total_work=5.0,
        )
        node = cluster.submit(task)
        assert node is not None
        cluster.run(until=10.0)
        assert cluster.task_completed(task.task_id)

    def test_kill_node_triggers_work_stealing(self):
        clock = SimClock()
        cluster = SimCluster.create(node_count=10, clock=clock)
        task = TaskSpec(
            name="resilient-job",
            requirements=ResourceRequirements(cpu_cores=2, ram_gb=4),
            checkpoint=True,
            total_work=100.0,
        )
        original_node = cluster.submit(task)
        assert original_node is not None

        chaos = ChaosController(cluster)
        chaos.kill_node(original_node, at=5.0)
        cluster.run(until=20.0)

        assert task.state in (TaskState.RUNNING, TaskState.COMPLETED)
        if task.state == TaskState.RUNNING:
            assert task.assigned_node != original_node

    def test_checkpoint_preserves_progress(self):
        clock = SimClock()
        cluster = SimCluster.create(node_count=5, clock=clock)
        task = TaskSpec(
            name="checkpoint-job",
            requirements=ResourceRequirements(cpu_cores=2, ram_gb=4),
            checkpoint=True,
            total_work=100.0,
        )
        cluster.submit(task)
        cluster.run(until=15.0)
        progress_before = task.progress

        cp = cluster.checkpoint_manager.load(task.task_id)
        assert cp is not None
        assert cp.progress == progress_before
        assert progress_before > 0

    def test_cluster_stats_after_chaos(self):
        clock = SimClock()
        cluster = SimCluster.create(node_count=20, clock=clock)
        chaos = ChaosController(cluster)
        chaos.kill_node("NODE-000", at=5.0)
        chaos.kill_node("NODE-001", at=10.0)
        cluster.run(until=30.0)

        stats = cluster.cluster_stats()
        assert stats["alive_nodes"] == 18


class TestCheckpointManager:
    def test_save_and_restore(self):
        mgr = CheckpointManager()
        task = TaskSpec(name="t", total_work=1000)
        task.progress = 650
        mgr.save(task, state_data={"offset": 650})

        cp = mgr.load(task.task_id)
        assert cp.progress == 650
        assert cp.state_data["offset"] == 650

    def test_restore_progress_on_new_task(self):
        mgr = CheckpointManager()
        task = TaskSpec(name="t", total_work=1000)
        task.progress = 650
        mgr.save(task)

        new_task = TaskSpec(name="t-restart", task_id=task.task_id, total_work=1000)
        restored = mgr.restore_progress(new_task)
        assert restored.progress == 650


class TestWorkStealer:
    def test_finds_orphaned_tasks(self):
        stealer = WorkStealer()
        tasks = [
            TaskSpec(name="t1", assigned_node="DEAD-1", state=TaskState.RUNNING),
            TaskSpec(name="t2", assigned_node="ALIVE-1", state=TaskState.RUNNING),
            TaskSpec(name="t3", assigned_node="DEAD-1", state=TaskState.COMPLETED),
        ]
        orphaned = stealer.find_orphaned_tasks(tasks, {"DEAD-1"})
        assert len(orphaned) == 1
        assert orphaned[0].name == "t1"

    def test_steals_to_healthy_node(self):
        stealer = WorkStealer()
        task = TaskSpec(
            name="orphan",
            requirements=ResourceRequirements(cpu_cores=2, ram_gb=4),
            assigned_node="DEAD-1",
            state=TaskState.RUNNING,
        )
        agents = [
            SimAgent(node_id="ALIVE-1", cpu_cores=16, ram_gb=32),
            SimAgent(node_id="DEAD-1", cpu_cores=8, ram_gb=16),
        ]
        agents[1].kill()
        nodes = [a.to_node() for a in agents if a.alive]

        results = stealer.steal([task], nodes)
        assert len(results) == 1
        assert results[0][1] == "ALIVE-1"
        assert task.state == TaskState.RUNNING
