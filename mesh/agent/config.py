from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class AgentConfig:
    node_id: str = ""
    driver_address: str = "localhost:50050"
    agent_address: str = "localhost:50051"
    location: str = "default"
    preemptible: bool = True
    heartbeat_interval: float = 2.0
    resource_interval: float = 1.0
    cpu_preemption_threshold: float = 0.85

    @classmethod
    def from_env(cls) -> AgentConfig:
        import socket
        hostname = socket.gethostname()
        return cls(
            node_id=os.environ.get("MESH_NODE_ID", hostname),
            driver_address=os.environ.get("MESH_DRIVER_ADDRESS", "localhost:50050"),
            agent_address=os.environ.get("MESH_AGENT_ADDRESS", "localhost:50051"),
            location=os.environ.get("MESH_LOCATION", "default"),
            preemptible=os.environ.get("MESH_PREEMPTIBLE", "true").lower() == "true",
        )
