from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import uvicorn

from mesh.api.app import create_app
from mesh.api.auth import AuthConfig
from mesh.api.context import AppContext
from mesh.api.events import event_bus
from mesh.driver.cluster import DriverCluster
from mesh.driver.ha import HADriverCoordinator, LeaderElection
from mesh.driver.job_manager import JobManager
from mesh.driver.server import DriverServer
from mesh.state import create_state_store
from mesh.meshvpn.coordinator import MeshCoordinator

logger = logging.getLogger(__name__)


def _parse_grpc_port(address: str) -> int:
    return int(address.rsplit(":", 1)[-1])


class MeshPlatform:
    """Unified driver + REST API + dashboard platform."""

    def __init__(
        self,
        grpc_address: str = "0.0.0.0:50050",
        api_port: int = 8080,
        db_path: str = "clustermesh.db",
        store_url: str | None = None,
        mdns: bool = False,
        site: str = "default",
        auth: AuthConfig | None = None,
        mesh_config: str | None = None,
    ) -> None:
        self.grpc_address = grpc_address
        self.api_port = api_port
        self.db_path = db_path
        self.site = site
        self.store = create_state_store(store_url or f"sqlite:///{db_path}")
        self.mesh: MeshCoordinator | None = None
        if mesh_config:
            self.mesh = MeshCoordinator.from_yaml(mesh_config)
            self.mesh.config.site_id = site
        elif site != "default":
            from mesh.meshvpn.site import MeshConfig

            self.mesh = MeshCoordinator(MeshConfig(site_id=site))
        self.cluster = DriverCluster()
        self.manager = JobManager(cluster=self.cluster, state_store=self.store)
        self.coordinator = HADriverCoordinator(self.manager, self.store, LeaderElection(self.store))
        self.grpc_server = DriverServer(
            address=grpc_address,
            cluster=self.cluster,
            job_manager=self.manager,
        )
        self.auth = auth or AuthConfig.from_env()
        self.ctx = AppContext(
            cluster=self.cluster,
            job_manager=self.manager,
            coordinator=self.coordinator,
            state_store=self.store,
            event_bus=event_bus,
            mesh=self.mesh,
        )
        self.app = create_app(self.ctx, auth=self.auth)
        self._uvicorn: Optional[uvicorn.Server] = None
        self._api_thread: Optional[threading.Thread] = None
        self._mdns = None
        if mdns:
            from mesh.discovery.mdns import DriverAdvertiser

            self._mdns = DriverAdvertiser(
                grpc_port=_parse_grpc_port(grpc_address),
                api_port=api_port,
                site=site,
            )

    def start(self) -> None:
        event_bus.info(
            "platform",
            "ComputeMesh platform starting",
            site=self.site,
            store=type(self.store).__name__,
        )
        self.coordinator.start()
        self.grpc_server.start()
        event_bus.info("driver", f"gRPC driver listening on {self.grpc_address}")

        if self._mdns:
            self._mdns.start()
            event_bus.info("discovery", f"mDNS advertising site '{self.site}'")

        if self.mesh:
            grpc_target = f"127.0.0.1:{_parse_grpc_port(self.grpc_address)}"
            self.mesh.start_relay(target_grpc=grpc_target)
            self.mesh.probe_peers()
            event_bus.info(
                "mesh",
                f"Mesh VPN active — site {self.mesh.config.site_id}, {len(self.mesh.peers())} peers",
            )

        if self.api_port <= 0:
            return

        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.api_port,
            log_level="warning",
        )
        self._uvicorn = uvicorn.Server(config)
        self._api_thread = threading.Thread(target=self._uvicorn.run, daemon=True)
        self._api_thread.start()
        event_bus.info("api", f"Dashboard at http://localhost:{self.api_port}")
        logger.info("Platform ready — dashboard: http://localhost:%d", self.api_port)

    def run_forever(self) -> None:
        try:
            while True:
                time.sleep(5)
                if self.coordinator.is_leader:
                    self.manager.run_rebalance()
                    self.manager.check_speculation()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._mdns:
            self._mdns.stop()
        if self.mesh:
            self.mesh.stop_relay()
        self.grpc_server.stop()
        self.coordinator.stop()
        self.store.close()
        event_bus.info("platform", "ComputeMesh platform stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    import argparse

    parser = argparse.ArgumentParser(description="ComputeMesh Platform")
    parser.add_argument("--grpc", default="0.0.0.0:50050", help="gRPC listen address")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MESH_DASHBOARD_PORT", "8080")))
    parser.add_argument("--db", default=os.environ.get("MESH_STATE_DB", "clustermesh.db"))
    parser.add_argument(
        "--store-url",
        default=os.environ.get("MESH_STATE_URL"),
        help="State backend URL (sqlite://, postgres://, redis://)",
    )
    parser.add_argument("--mdns", action="store_true", help="Advertise driver via mDNS")
    parser.add_argument("--site", default=os.environ.get("MESH_SITE", "default"), help="Site/region label")
    parser.add_argument("--mesh-config", default=os.environ.get("MESH_CONFIG"), help="Path to sites.yaml")
    parser.add_argument("--api-key", default=os.environ.get("MESH_API_KEY"), help="Require API key for REST")
    args = parser.parse_args()

    auth = AuthConfig(api_key=args.api_key, enabled=bool(args.api_key))
    platform = MeshPlatform(
        grpc_address=args.grpc,
        api_port=args.port,
        db_path=args.db,
        store_url=args.store_url,
        mdns=args.mdns,
        site=args.site,
        auth=auth,
        mesh_config=args.mesh_config,
    )
    platform.start()
    platform.run_forever()


if __name__ == "__main__":
    main()
