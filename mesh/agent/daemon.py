from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time

from mesh.agent.client import DriverClient
from mesh.agent.config import AgentConfig
from mesh.agent.executor import AgentTaskRunner
from mesh.agent.library import LibraryManager
from mesh.agent.monitor import ResourceMonitor, get_hostname, get_os_name
from mesh.agent.preemption import PreemptionDetector
from mesh.agent.server import AgentServer
import mesh.tasks.builtins  # noqa: F401 — register built-in tasks

if False:  # TYPE_CHECKING
    from mesh.worker.state import WorkerState

logger = logging.getLogger(__name__)


class AgentDaemon:
    """ClusterMesh agent — joins a cluster and executes assigned tasks."""

    def __init__(self, config: AgentConfig, worker_state: "WorkerState | None" = None) -> None:
        self.config = config
        self.worker_state = worker_state
        self.monitor = ResourceMonitor()
        self.preemption = PreemptionDetector(cpu_threshold=config.cpu_preemption_threshold)
        self.libraries = LibraryManager()
        self.runner = AgentTaskRunner()
        self.driver = DriverClient(config.driver_address, config.node_id)
        self.agent_server = AgentServer(config.agent_address, self.runner, self.libraries)
        self._running = False

        self.runner.on_progress = self._on_progress
        self.runner.on_complete = self._on_complete

    def start(self) -> None:
        self.agent_server.start()
        self.driver.connect()

        snapshot = self.monitor.snapshot(force=True)
        libs = self.libraries.list_names()
        resp = self.driver.register(
            hostname=get_hostname(),
            agent_address=self.config.agent_address,
            os_name=get_os_name(),
            location=self.config.location,
            preemptible=self.config.preemptible,
            snapshot=snapshot,
            libraries=libs,
        )
        if not resp.accepted:
            if self.worker_state:
                self.worker_state.mark_failed(resp.message or "registration rejected")
            raise RuntimeError(f"Registration rejected: {resp.message}")

        if self.worker_state:
            self.worker_state.mark_registered(self.config.node_id)
            self.worker_state.update_snapshot(snapshot, libraries_count=len(libs))

        logger.info("Registered with driver as %s", self.config.node_id)
        self._running = True
        self._loop()

    def stop(self) -> None:
        self._running = False
        self.agent_server.stop()
        self.driver.close()

    def _loop(self) -> None:
        last_heartbeat = 0.0
        last_resource = 0.0

        while self._running:
            now = time.monotonic()
            try:
                snapshot = self.monitor.snapshot()

                if now - last_resource >= self.config.resource_interval:
                    self.driver.report_resources(snapshot)
                    last_resource = now

                if now - last_heartbeat >= self.config.heartbeat_interval:
                    resp = self.driver.heartbeat()
                    if self.worker_state:
                        self.worker_state.update_heartbeat(resp.node_state or None)
                    last_heartbeat = now

                if self.worker_state:
                    self.worker_state.update_snapshot(
                        snapshot,
                        libraries_count=len(self.libraries.list_names()),
                        active_tasks=self.runner.running_count(),
                    )

                triggered, reason = self.preemption.check(snapshot)
                if triggered and self.config.preemptible:
                    logger.warning("Preemption warning: %s", reason)
                    self.driver.preemption_warning(snapshot.cpu_utilization, reason)
                    self.preemption.reset()
            except Exception as exc:
                if not self._running:
                    break
                logger.debug("Agent loop error: %s", exc)
                break

            time.sleep(0.25)

    def _on_progress(self, spec) -> None:
        try:
            self.driver.task_progress(
                spec.task_id, spec.progress, spec.total_work, spec.state_data
            )
        except Exception as exc:
            logger.debug("Progress report failed: %s", exc)

    def _on_complete(self, spec, result, error) -> None:
        try:
            if error and error != "interrupted":
                self.driver.task_complete(spec.task_id, False, error=error)
            elif error == "interrupted":
                pass
            else:
                self.driver.task_complete(spec.task_id, True, result=result)
        except Exception as exc:
            logger.debug("Complete report failed: %s", exc)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="ClusterMesh Agent Daemon")
    parser.add_argument("--driver", default=None, help="Driver address host:port")
    parser.add_argument("--agent-addr", default=None, help="Agent gRPC listen address")
    parser.add_argument("--node-id", default=None, help="Node identifier")
    parser.add_argument("--location", default=None, help="Site/location label")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Auto-discover driver via mDNS on local network",
    )
    args = parser.parse_args()

    config = AgentConfig.from_env()
    if args.discover or (not args.driver and not config.driver_address):
        from mesh.discovery.mdns import discover_driver

        record = discover_driver(timeout=8.0)
        if record:
            config.driver_address = record.grpc_address
            if not args.location:
                config.location = record.site
            logger.info("Discovered driver at %s (site=%s)", record.grpc_address, record.site)
        elif not config.driver_address:
            parser.error("No driver found — use --driver host:port or start driver with --mdns")
    if args.driver:
        config.driver_address = args.driver
    if args.agent_addr:
        config.agent_address = args.agent_addr
    if args.node_id:
        config.node_id = args.node_id
    if args.location:
        config.location = args.location

    daemon = AgentDaemon(config)

    def shutdown(signum, frame):
        logger.info("Shutting down agent...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(
        "Starting ClusterMesh agent %s → driver %s",
        config.node_id,
        config.driver_address,
    )
    daemon.start()


if __name__ == "__main__":
    main()
