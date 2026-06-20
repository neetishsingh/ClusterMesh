"""Multi-site mesh coordinator — peer registry, routing, health."""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Optional

from mesh.meshvpn.site import MeshConfig, SitePeer

logger = logging.getLogger(__name__)


class MeshCoordinator:
    """Manages cross-site peer connections and route selection."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()
        self._peers: dict[str, SitePeer] = {p.site_id: p for p in self.config.peers}
        self._lock = threading.Lock()
        self._relay = None

    @classmethod
    def from_yaml(cls, path: str) -> MeshCoordinator:
        return cls(MeshConfig.from_yaml(path))

    def start_relay(self, target_grpc: str = "127.0.0.1:50050") -> None:
        from mesh.meshvpn.relay import TcpRelayServer

        self._relay = TcpRelayServer(
            listen_address=self.config.relay_listen,
            target_address=target_grpc,
        )
        self._relay.start()
        logger.info("Mesh relay active for site %s", self.config.site_id)

    def stop_relay(self) -> None:
        if self._relay:
            self._relay.stop()

    def add_peer(self, peer: SitePeer) -> None:
        with self._lock:
            self._peers[peer.site_id] = peer
        logger.info("Registered mesh peer: %s → %s", peer.site_id, peer.grpc_address)

    def remove_peer(self, site_id: str) -> None:
        with self._lock:
            self._peers.pop(site_id, None)

    def peers(self) -> list[SitePeer]:
        with self._lock:
            return list(self._peers.values())

    def probe_peers(self) -> None:
        """Measure TCP latency to peer relay endpoints."""
        with self._lock:
            items = list(self._peers.items())
        for site_id, peer in items:
            host, _, port = peer.relay_address.rpartition(":")
            if not host:
                host, port = peer.relay_address, "6000"
            start = time.monotonic()
            try:
                s = socket.create_connection((host, int(port)), timeout=3)
                s.close()
                peer.latency_ms = (time.monotonic() - start) * 1000
                peer.status = "reachable"
            except OSError:
                peer.latency_ms = -1
                peer.status = "unreachable"

    def best_peer_route(self, target_site: str) -> Optional[str]:
        """Return gRPC address for reaching a remote site (lowest latency)."""
        with self._lock:
            peer = self._peers.get(target_site)
            if peer and peer.status == "reachable":
                return peer.grpc_address
            if peer:
                return peer.grpc_address
        return None

    def resolve_agent_driver(self, agent_site: str, local_grpc: str) -> str:
        """Agents at remote sites connect via peer relay; local agents use direct gRPC."""
        if agent_site == self.config.site_id or agent_site == "default":
            return local_grpc
        route = self.best_peer_route(agent_site)
        return route or local_grpc

    def payload(self) -> dict:
        relay_info = None
        if self._relay:
            relay_info = {
                "listen": self.config.relay_listen,
                "public": self.config.relay_public or self._relay.address,
                "connections": self._relay.connections,
            }
        return {
            "site_id": self.config.site_id,
            "relay": relay_info,
            "peers": [p.to_dict() for p in self.peers()],
        }
