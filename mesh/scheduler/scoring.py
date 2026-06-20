from __future__ import annotations

from dataclasses import dataclass

from mesh.models.node import Node
from mesh.models.task import ResourceRequirements


@dataclass(frozen=True)
class ScoringWeights:
    cpu: float = 0.35
    memory: float = 0.25
    gpu: float = 0.15
    reliability: float = 0.15
    network: float = 0.10

    def __post_init__(self) -> None:
        total = self.cpu + self.memory + self.gpu + self.reliability + self.network
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


@dataclass
class NodeScorer:
    """
    Multi-dimensional node scoring engine.

    NodeScore = 0.35×CPU + 0.25×Memory + 0.15×GPU + 0.15×Reliability + 0.10×Network
    """

    weights: ScoringWeights = ScoringWeights()

    def score(self, node: Node, requirements: ResourceRequirements) -> float:
        r = node.resources

        cpu_score = r.cpu_score_component if r.cpu_cores_free >= requirements.cpu_cores else 0.0
        mem_score = r.memory_score_component if r.ram_gb_free >= requirements.ram_gb else 0.0

        if requirements.gpu_count > 0:
            gpu_score = r.gpu_score_component if r.gpu_count >= requirements.gpu_count else 0.0
        else:
            gpu_score = 1.0

        network_score = min(1.0, r.network_gbps / max(requirements.network_gbps, 1.0))

        total = (
            self.weights.cpu * cpu_score
            + self.weights.memory * mem_score
            + self.weights.gpu * gpu_score
            + self.weights.reliability * node.reliability_score
            + self.weights.network * network_score
        )
        return round(total, 6)
