"""Tests for node scoring and placement."""

import pytest
from datetime import datetime

from mesh.models.enums import NodeState, ResourcePool
from mesh.models.node import Node, NodeResources
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.scheduler.placement import PlacementEngine
from mesh.scheduler.pools import PoolRouter
from mesh.scheduler.scoring import NodeScorer, ScoringWeights


def make_node(
    node_id: str,
    cpu_total: int = 32,
    cpu_free: float = 28,
    ram_total: float = 64,
    ram_free: float = 48,
    gpu: int = 0,
    vram: float = 0,
    cuda: str | None = None,
    battery: float | None = None,
    preemptible: bool = False,
    reliability: float = 0.9,
) -> Node:
    return Node(
        node_id=node_id,
        hostname=node_id,
        resources=NodeResources(
            cpu_cores_total=cpu_total,
            cpu_cores_free=cpu_free,
            ram_gb_total=ram_total,
            ram_gb_free=ram_free,
            gpu_count=gpu,
            vram_gb_free=vram,
            cuda_version=cuda,
            battery_pct=battery,
        ),
        reliability_score=reliability,
        preemptible=preemptible,
    )


class TestNodeScorer:
    def test_high_free_resources_scores_higher(self):
        scorer = NodeScorer()
        req = ResourceRequirements(cpu_cores=4, ram_gb=8)
        good = make_node("GOOD", cpu_free=30, ram_free=50)
        bad = make_node("BAD", cpu_free=5, ram_free=5)
        assert scorer.score(good, req) > scorer.score(bad, req)

    def test_insufficient_cpu_scores_lower_than_sufficient(self):
        scorer = NodeScorer()
        req = ResourceRequirements(cpu_cores=16, ram_gb=8)
        insufficient = make_node("N", cpu_total=32, cpu_free=2)
        sufficient = make_node("OK", cpu_total=64, cpu_free=60)
        assert scorer.score(insufficient, req) < scorer.score(sufficient, req)

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError):
            ScoringWeights(cpu=0.5, memory=0.5, gpu=0.5)

    def test_deterministic_tiebreak(self):
        scorer = NodeScorer()
        req = ResourceRequirements(cpu_cores=4, ram_gb=8)
        n1 = make_node("A", cpu_free=20, ram_free=40)
        n2 = make_node("B", cpu_free=20, ram_free=40)
        assert scorer.score(n1, req) == scorer.score(n2, req)


class TestPoolRouter:
    def test_battery_gate_excludes_low_battery(self):
        router = PoolRouter(battery_min_pct=60)
        low = make_node("LOW", battery=40, preemptible=True)
        assert router._passes_battery_gate(low) is False

    def test_battery_gate_allows_no_battery(self):
        router = PoolRouter()
        desktop = make_node("DESK", battery=None)
        assert router._passes_battery_gate(desktop) is True

    def test_night_pool_only_preemptible(self):
        router = PoolRouter()
        night_time = datetime(2026, 6, 20, 22, 0)
        laptop = make_node("LAP", preemptible=True, battery=80)
        desktop = make_node("DESK", preemptible=False)
        eligible = router.eligible_nodes([laptop, desktop], ResourcePool.NIGHT, night_time)
        assert len(eligible) == 1
        assert eligible[0].node_id == "LAP"

    def test_night_pool_empty_during_day(self):
        router = PoolRouter()
        day_time = datetime(2026, 6, 20, 14, 0)
        laptop = make_node("LAP", preemptible=True, battery=80)
        eligible = router.eligible_nodes([laptop], ResourcePool.NIGHT, day_time)
        assert eligible == []

    def test_gpu_pool_requires_cuda(self):
        router = PoolRouter()
        gpu_node = make_node("GPU", gpu=2, vram=24, cuda="12")
        no_cuda = make_node("NOGPU", gpu=1, vram=8, cuda=None)
        eligible = router.eligible_nodes([gpu_node, no_cuda], ResourcePool.GPU)
        assert len(eligible) == 1
        assert eligible[0].node_id == "GPU"


class TestPlacementEngine:
    def test_places_on_best_node(self):
        engine = PlacementEngine()
        task = TaskSpec(name="etl", requirements=ResourceRequirements(cpu_cores=4, ram_gb=8))
        nodes = [
            make_node("SMALL", cpu_free=5, ram_free=10, reliability=0.5),
            make_node("BIG", cpu_free=30, ram_free=50, reliability=0.95),
        ]
        placement = engine.place(task, nodes)
        assert placement is not None
        assert placement.node_id == "BIG"

    def test_rejects_insufficient_resources(self):
        engine = PlacementEngine()
        task = TaskSpec(
            name="big",
            requirements=ResourceRequirements(cpu_cores=128, ram_gb=256),
        )
        nodes = [make_node("SMALL", cpu_total=32, cpu_free=32, ram_total=64, ram_free=64)]
        assert engine.place(task, nodes) is None

    def test_rejects_dead_nodes(self):
        engine = PlacementEngine()
        task = TaskSpec(name="etl", requirements=ResourceRequirements(cpu_cores=2, ram_gb=4))
        node = make_node("DEAD")
        node.state = NodeState.DEAD
        assert engine.place(task, [node]) is None

    def test_respects_pool_routing(self):
        engine = PlacementEngine()
        task = TaskSpec(
            name="gpu-train",
            requirements=ResourceRequirements(cpu_cores=8, ram_gb=32, gpu_count=1),
            pool=ResourcePool.GPU,
        )
        nodes = [
            make_node("CPU-ONLY", gpu=0),
            make_node("GPU-BOX", gpu=2, vram=24, cuda="12"),
        ]
        placement = engine.place(task, nodes)
        assert placement is not None
        assert placement.node_id == "GPU-BOX"

    def test_place_all_with_resource_tracking(self):
        engine = PlacementEngine()
        tasks = [
            TaskSpec(name=f"t{i}", requirements=ResourceRequirements(cpu_cores=4, ram_gb=8))
            for i in range(3)
        ]
        nodes = [make_node("BIG", cpu_total=64, cpu_free=60, ram_total=128, ram_free=120)]
        placements = engine.place_all(tasks, nodes)
        assert len(placements) == 3
