"""Shared runtime state for the local worker UI."""

from __future__ import annotations

from dataclasses import dataclass, field
import socket
import time
from typing import Any


@dataclass
class WorkerState:
    node_id: str = ""
    hostname: str = field(default_factory=socket.gethostname)
    driver_address: str = ""
    agent_address: str = ""
    location: str = "default"
    ui_port: int = 50052
    registered: bool = False
    node_state: str = "STARTING"
    preemptible: bool = True
    started_at: float = field(default_factory=time.time)
    last_heartbeat_at: float | None = None
    cpu_utilization_pct: float = 0.0
    cpu_cores: int = 0
    cpu_physical: int = 0
    ram_gb_total: float = 0.0
    ram_gb_free: float = 0.0
    process_count: int = 0
    thread_count: int = 0
    libraries_count: int = 0
    active_tasks: int = 0
    last_error: str | None = None
    host_metrics: dict[str, Any] = field(default_factory=dict)

    def mark_registered(self, node_id: str) -> None:
        self.node_id = node_id
        self.registered = True
        self.node_state = "HEALTHY"
        self.last_error = None

    def mark_failed(self, error: str) -> None:
        self.registered = False
        self.node_state = "ERROR"
        self.last_error = error

    def update_heartbeat(self, node_state: str | None = None) -> None:
        self.last_heartbeat_at = time.time()
        if node_state:
            self.node_state = node_state

    def update_snapshot(
        self,
        snapshot,
        *,
        libraries_count: int = 0,
        active_tasks: int = 0,
    ) -> None:
        import json

        self.cpu_utilization_pct = round(snapshot.cpu_utilization * 100, 1)
        self.cpu_cores = snapshot.cpu_cores_total
        self.cpu_physical = getattr(snapshot, "cpu_cores_physical", 0) or snapshot.cpu_cores_total
        self.ram_gb_total = round(snapshot.ram_gb_total, 1)
        self.ram_gb_free = round(snapshot.ram_gb_free, 1)
        if snapshot.host_metrics_json:
            try:
                hm = json.loads(snapshot.host_metrics_json)
                procs = hm.get("processes", {})
                self.process_count = procs.get("total", 0)
                self.thread_count = procs.get("threads_total", 0)
                self.host_metrics = hm
            except json.JSONDecodeError:
                pass
        self.libraries_count = libraries_count
        self.active_tasks = active_tasks

    @property
    def dashboard_url(self) -> str | None:
        if not self.driver_address:
            return None
        host = self.driver_address.rsplit(":", 1)[0]
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return "http://localhost:8080"
        return f"http://{host}:8080"

    def to_dict(self) -> dict[str, Any]:
        uptime = int(time.time() - self.started_at)
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "driver_address": self.driver_address,
            "agent_address": self.agent_address,
            "location": self.location,
            "ui_port": self.ui_port,
            "registered": self.registered,
            "node_state": self.node_state,
            "preemptible": self.preemptible,
            "uptime_seconds": uptime,
            "last_heartbeat_at": self.last_heartbeat_at,
            "cpu_utilization_pct": self.cpu_utilization_pct,
            "cpu_cores": self.cpu_cores,
            "cpu_physical": self.cpu_physical,
            "ram_gb_total": self.ram_gb_total,
            "ram_gb_free": self.ram_gb_free,
            "process_count": self.process_count,
            "thread_count": self.thread_count,
            "libraries_count": self.libraries_count,
            "active_tasks": self.active_tasks,
            "last_error": self.last_error,
            "dashboard_url": self.dashboard_url,
            "local_ui_url": f"http://127.0.0.1:{self.ui_port}",
            "host_metrics": self.host_metrics,
        }
