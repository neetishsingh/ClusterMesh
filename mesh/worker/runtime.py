"""Worker runtime — agent + local dashboard."""

from __future__ import annotations

import logging
import signal
import sys
import threading

from mesh.agent.config import AgentConfig
from mesh.agent.daemon import AgentDaemon
from mesh.worker.server import run_worker_ui
from mesh.worker.state import WorkerState

logger = logging.getLogger(__name__)


class WorkerRuntime:
    """Runs mesh-agent and the local worker UI in one process."""

    def __init__(self, config: AgentConfig, *, ui_port: int = 50052, ui_host: str = "127.0.0.1") -> None:
        self.config = config
        self.ui_port = ui_port
        self.ui_host = ui_host
        self.state = WorkerState(
            node_id=config.node_id,
            driver_address=config.driver_address,
            agent_address=config.agent_address,
            location=config.location,
            ui_port=ui_port,
            preemptible=config.preemptible,
        )
        self.daemon = AgentDaemon(config, worker_state=self.state)
        self._ui_thread: threading.Thread | None = None

    def start(self, *, blocking: bool = True) -> None:
        self._ui_thread = threading.Thread(
            target=run_worker_ui,
            args=(self.state, self.ui_host, self.ui_port),
            daemon=True,
            name="worker-ui",
        )
        self._ui_thread.start()
        logger.info("Worker UI: http://%s:%s", self.ui_host, self.ui_port)

        def shutdown(signum, frame):
            logger.info("Shutting down worker...")
            self.daemon.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        if blocking:
            self.daemon.start()
        else:
            thread = threading.Thread(target=self.daemon.start, daemon=True, name="mesh-agent")
            thread.start()

    @property
    def local_ui_url(self) -> str:
        host = "localhost" if self.ui_host in ("0.0.0.0", "::") else self.ui_host
        return f"http://{host}:{self.ui_port}"
