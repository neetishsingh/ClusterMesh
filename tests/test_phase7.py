"""Phase 7 — mesh VPN, relay, 24h soak."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from mesh.api.app import create_app
from mesh.api.context import AppContext
from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.meshvpn.coordinator import MeshCoordinator
from mesh.meshvpn.relay import TcpRelayServer
from mesh.meshvpn.site import MeshConfig, SitePeer
from mesh.sim.soak import SoakHarness


class TestMeshConfig:
    def test_from_yaml(self, tmp_path):
        cfg_file = tmp_path / "sites.yaml"
        cfg_file.write_text(yaml.dump({
            "site": "bangalore",
            "relay": {"listen": "0.0.0.0:6000", "public": "bangalore:6000"},
            "peers": [{"site": "london", "relay": "london:6000", "grpc": "london:50050"}],
        }))
        cfg = MeshConfig.from_yaml(cfg_file)
        assert cfg.site_id == "bangalore"
        assert len(cfg.peers) == 1
        assert cfg.peers[0].site_id == "london"


class TestMeshCoordinator:
    def test_add_peer_and_payload(self):
        mesh = MeshCoordinator(MeshConfig(site_id="local"))
        mesh.add_peer(SitePeer("remote", "remote:6000", "remote:50050", region="eu"))
        payload = mesh.payload()
        assert payload["site_id"] == "local"
        assert len(payload["peers"]) == 1

    def test_resolve_local_vs_remote(self):
        mesh = MeshCoordinator(MeshConfig(site_id="bangalore"))
        mesh.add_peer(SitePeer("london", "london:6000", "london:50050"))
        assert mesh.resolve_agent_driver("bangalore", "local:50050") == "local:50050"
        assert mesh.resolve_agent_driver("london", "local:50050") == "london:50050"


class TestTcpRelay:
    def test_relay_forwards(self):
        # Echo server as fake gRPC target
        echo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        echo.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        echo.bind(("127.0.0.1", 0))
        echo.listen(1)
        port = echo.getsockname()[1]

        def accept_echo():
            conn, _ = echo.accept()
            data = conn.recv(1024)
            conn.sendall(data)
            conn.close()

        threading.Thread(target=accept_echo, daemon=True).start()

        relay = TcpRelayServer(f"127.0.0.1:0", f"127.0.0.1:{port}")
        relay.start()
        time.sleep(0.1)
        rport = relay._server.getsockname()[1]

        client = socket.create_connection(("127.0.0.1", rport), timeout=5)
        client.sendall(b"ping")
        assert client.recv(4) == b"ping"
        client.close()
        relay.stop()
        echo.close()


class TestMeshAPI:
    def test_mesh_endpoints(self):
        mesh = MeshCoordinator(MeshConfig(site_id="test-site"))
        ctx = AppContext(
            cluster=DriverCluster(),
            job_manager=JobManager(cluster=DriverCluster()),
            mesh=mesh,
        )
        client = TestClient(create_app(ctx))
        r = client.get("/api/v1/mesh")
        assert r.status_code == 200
        assert r.json()["site_id"] == "test-site"

        client.post("/api/v1/mesh/peers", json={
            "site_id": "peer1",
            "relay_address": "p:6000",
            "grpc_address": "p:50050",
        })
        peers = client.get("/api/v1/mesh/peers").json()["peers"]
        assert len(peers) == 1


class TestSoak24h:
    def test_accelerated_24h_soak(self):
        harness = SoakHarness(node_count=30, sim_duration=86400, seed=1)
        report = harness.run()
        data = report.to_dict()
        assert data["sim_duration_hours"] == 24.0
        assert data["node_deaths"] > 0
        assert data["uptime_pct"] >= 50.0

    def test_short_soak_for_ci(self):
        harness = SoakHarness(node_count=10, sim_duration=3600, seed=99)
        report = harness.run()
        assert report.ticks > 0
