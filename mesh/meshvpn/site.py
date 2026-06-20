"""Site definitions for multi-region mesh clusters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class SitePeer:
    site_id: str
    relay_address: str
    grpc_address: str
    region: str = ""
    latency_ms: float = 0.0
    status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "relay_address": self.relay_address,
            "grpc_address": self.grpc_address,
            "region": self.region or self.site_id,
            "latency_ms": round(self.latency_ms, 1),
            "status": self.status,
        }


@dataclass
class MeshConfig:
    """Local site + remote peer configuration."""

    site_id: str = "default"
    relay_listen: str = "0.0.0.0:6000"
    relay_public: str = ""
    peers: list[SitePeer] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> MeshConfig:
        data = yaml.safe_load(Path(path).read_text()) or {}
        peers = [
            SitePeer(
                site_id=p["site"],
                relay_address=p.get("relay", ""),
                grpc_address=p.get("grpc", ""),
                region=p.get("region", p["site"]),
                latency_ms=float(p.get("latency_ms", 0)),
            )
            for p in data.get("peers", [])
        ]
        relay = data.get("relay", {})
        return cls(
            site_id=data.get("site", "default"),
            relay_listen=relay.get("listen", "0.0.0.0:6000"),
            relay_public=relay.get("public", ""),
            peers=peers,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "relay_listen": self.relay_listen,
            "relay_public": self.relay_public,
            "peers": [p.to_dict() for p in self.peers],
        }
