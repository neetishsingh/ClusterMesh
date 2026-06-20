"""Tests for rebalancing and speculation."""

import time

from mesh.models.enums import TaskState
from mesh.models.node import Node, NodeResources
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.recovery.speculation import SpeculativeExecutor
from mesh.scheduler.rebalancing import Rebalancer


def _node(node_id: str, cpu_total: int, cpu_free: float) -> Node:
    return Node(
        node_id=node_id,
        hostname=node_id,
        resources=NodeResources(
            cpu_cores_total=cpu_total,
            cpu_cores_free=cpu_free,
            ram_gb_total=64,
            ram_gb_free=32,
        ),
    )


class TestRebalancer:
    def test_finds_rebalance_actions(self):
        rebalancer = Rebalancer(variance_threshold=0.2)
        nodes = [
            _node("hot", 64, 2),
            _node("cold", 64, 58),
        ]
        tasks = [
            TaskSpec(
                name="t1",
                task_id="t1",
                assigned_node="hot",
                state=TaskState.RUNNING,
                requirements=ResourceRequirements(cpu_cores=1, ram_gb=1),
            )
        ]
        actions = rebalancer.analyze(nodes, tasks)
        assert len(actions) == 1
        assert actions[0].from_node == "hot"
        assert actions[0].to_node == "cold"


class TestSpeculativeExecutor:
    def test_detects_straggler(self):
        spec = SpeculativeExecutor(multiplier=1.5, min_runtime_seconds=0.01)
        tasks = [
            TaskSpec(name="fast", task_id="fast", state=TaskState.RUNNING),
            TaskSpec(name="slow", task_id="slow", state=TaskState.RUNNING),
        ]
        spec.record_start("slow")
        time.sleep(0.05)
        spec.record_start("fast")
        stragglers = spec.find_stragglers(tasks)
        assert any(s.task_id == "slow" for s in stragglers)
