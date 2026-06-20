"""Accelerated 24h chaos soak harness for SimCluster."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from mesh.models.enums import NodeState, TaskState
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.sim.chaos import ChaosController
from mesh.sim.clock import SimClock
from mesh.sim.cluster import SimCluster


@dataclass
class SoakReport:
    """Results from a simulated soak run."""

    sim_duration_seconds: float
    ticks: int
    node_deaths: int
    preemptions: int
    partitions: int
    tasks_submitted: int
    tasks_completed: int
    tasks_failed: int
    uptime_pct: float
    events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sim_duration_seconds": self.sim_duration_seconds,
            "sim_duration_hours": round(self.sim_duration_seconds / 3600, 2),
            "ticks": self.ticks,
            "node_deaths": self.node_deaths,
            "preemptions": self.preemptions,
            "partitions": self.partitions,
            "tasks_submitted": self.tasks_submitted,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "uptime_pct": round(self.uptime_pct, 2),
            "passed": self.uptime_pct >= 90.0 and self.tasks_submitted > 0,
        }


class SoakHarness:
    """
    Run a compressed 24h chaos soak using SimClock.

    Default simulates 86400s (24h) of cluster operation with random failures,
    preemptions, and network partitions — completes in seconds of wall time.
    """

    def __init__(
        self,
        node_count: int = 50,
        sim_duration: float = 86400.0,
        seed: int = 42,
    ) -> None:
        self.node_count = node_count
        self.sim_duration = sim_duration
        self.rng = random.Random(seed)
        self.clock = SimClock()
        self.cluster = SimCluster.create(node_count=node_count, clock=self.clock)
        sites = ["bangalore", "london", "aws-us-east", "local-dev"]
        for i, agent in enumerate(self.cluster.agents):
            agent.location = sites[i % len(sites)]
        self.chaos = ChaosController(self.cluster)

    def run(self) -> SoakReport:
        deaths = 0
        preemptions = 0
        partitions = 0
        submitted = 0
        events: list[str] = []

        # Schedule chaos across simulated 24h
        for hour in range(int(self.sim_duration // 3600)):
            t = hour * 3600 + self.rng.randint(0, 3000)
            node_idx = self.rng.randint(0, self.node_count - 1)
            action = self.rng.choice(["kill", "preempt", "partition"])
            if action == "kill":
                self.chaos.kill_node(f"NODE-{node_idx:03d}", at=t)
                deaths += 1
                events.append(f"t={t:.0f}s kill NODE-{node_idx:03d}")
            elif action == "preempt":
                self.chaos.preempt(f"NODE-{node_idx:03d}", at=t)
                preemptions += 1
            else:
                locs = list({a.location for a in self.cluster.agents})
                if len(locs) >= 2:
                    self.chaos.partition(locs[0], locs[1], at=t, duration=600)
                    partitions += 1

        # Submit periodic batch tasks
        batch_count = max(1, int(self.sim_duration // 7200))
        for batch in range(batch_count):
            at = batch * 7200 + 100

            def submit_task(b=batch):
                spec = TaskSpec(
                    task_id=f"soak-{b}",
                    job_id=f"soak-job-{b}",
                    name="soak-work",
                    requirements=ResourceRequirements(cpu_cores=1, ram_gb=1),
                    total_work=100,
                    checkpoint=True,
                )
                self.cluster.submit(spec)

            self.cluster.schedule_event(at, submit_task, f"submit batch {batch}")
            submitted += 1

        ticks = 0
        healthy_samples = 0
        while self.clock.now() < self.sim_duration:
            self.cluster._tick()
            self.clock.advance(self.cluster.tick_interval)
            ticks += 1
            stats = self.cluster.cluster_stats()
            if stats["healthy_nodes"] >= self.node_count * 0.5:
                healthy_samples += 1

        completed = sum(
            1 for t in self.cluster._tasks.values() if t.state == TaskState.COMPLETED
        )
        failed = sum(
            1 for t in self.cluster._tasks.values() if t.state == TaskState.FAILED
        )
        uptime = (healthy_samples / max(ticks, 1)) * 100

        return SoakReport(
            sim_duration_seconds=self.sim_duration,
            ticks=ticks,
            node_deaths=deaths,
            preemptions=preemptions,
            partitions=partitions,
            tasks_submitted=submitted,
            tasks_completed=completed,
            tasks_failed=failed,
            uptime_pct=uptime,
            events=events[:20],
        )


def main() -> None:
    import argparse
    import json
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="ComputeMesh 24h chaos soak (accelerated)")
    parser.add_argument("--nodes", type=int, default=50)
    parser.add_argument("--hours", type=float, default=24.0, help="Simulated hours")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    harness = SoakHarness(
        node_count=args.nodes,
        sim_duration=args.hours * 3600,
        seed=args.seed,
    )
    report = harness.run()
    print(json.dumps(report.to_dict(), indent=2))
    if not report.to_dict()["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
