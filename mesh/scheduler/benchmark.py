"""Scheduler scale benchmarks — 1000-node placement SLA."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from mesh.models.enums import NodeState
from mesh.models.node import Node, NodeResources
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.scheduler.placement import PlacementEngine


@dataclass
class PlacementBenchmarkResult:
    node_count: int
    iterations: int
    mean_ms: float
    p50_ms: float
    p99_ms: float
    max_ms: float
    sla_ms: float
    passed: bool

    def to_dict(self) -> dict:
        return {
            "node_count": self.node_count,
            "iterations": self.iterations,
            "mean_ms": round(self.mean_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "sla_ms": self.sla_ms,
            "passed": self.passed,
        }


def _make_nodes(count: int) -> list[Node]:
    return [
        Node(
            node_id=f"NODE-{i:04d}",
            hostname=f"worker-{i:04d}",
            resources=NodeResources(
                cpu_cores_total=8 + (i % 4) * 4,
                cpu_cores_free=float(4 + (i % 4) * 2),
                ram_gb_total=float(16 + (i % 5) * 8),
                ram_gb_free=float(8 + (i % 5) * 4),
                gpu_count=1 if i % 10 == 0 else 0,
                vram_gb_free=8.0 if i % 10 == 0 else 0,
            ),
            state=NodeState.HEALTHY,
            reliability_score=0.7 + (i % 3) * 0.1,
            location=["bangalore", "london", "aws"][i % 3],
        )
        for i in range(count)
    ]


def benchmark_placement(
    node_count: int = 1000,
    iterations: int = 200,
    sla_ms: float = 100.0,
) -> PlacementBenchmarkResult:
    """Measure single-task placement latency at scale."""
    nodes = _make_nodes(node_count)
    engine = PlacementEngine()
    task = TaskSpec(
        name="bench",
        requirements=ResourceRequirements(cpu_cores=2, ram_gb=4),
    )

    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        engine.place(task, nodes)
        times.append((time.perf_counter() - t0) * 1000)

    times.sort()
    p99_idx = min(len(times) - 1, int(len(times) * 0.99))
    p50_idx = len(times) // 2

    return PlacementBenchmarkResult(
        node_count=node_count,
        iterations=iterations,
        mean_ms=statistics.mean(times),
        p50_ms=times[p50_idx],
        p99_ms=times[p99_idx],
        max_ms=max(times),
        sla_ms=sla_ms,
        passed=times[p99_idx] < sla_ms,
    )


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Placement scale benchmark")
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--sla-ms", type=float, default=100.0)
    args = parser.parse_args()

    result = benchmark_placement(args.nodes, args.iterations, args.sla_ms)
    print(json.dumps(result.to_dict(), indent=2))
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
