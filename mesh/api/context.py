from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from mesh.driver.cluster import DriverCluster
from mesh.driver.ha.coordinator import HADriverCoordinator
from mesh.driver.job_manager import JobManager
from mesh.api.events import EventBus
from mesh.api.auth import get_current_tenant
from mesh.state.store import StateStore

from mesh.meshvpn.coordinator import MeshCoordinator
from mesh.memory.fabric import MemoryFabric
from mesh.driver.library_installer import LibraryInstaller


@dataclass
class AppContext:
    cluster: DriverCluster
    job_manager: JobManager
    coordinator: Optional[HADriverCoordinator] = None
    state_store: Optional[StateStore] = None
    mesh: Optional[MeshCoordinator] = None
    memory: MemoryFabric = field(default_factory=MemoryFabric)
    event_bus: EventBus = field(default_factory=lambda: __import__("mesh.api.events", fromlist=["event_bus"]).event_bus)
    library_installer: LibraryInstaller | None = field(default=None, repr=False)
    _driver_snapshot_at: float = field(default=0.0, repr=False)
    _driver_snapshot: Any = field(default=None, repr=False)
    _driver_cpu_ema: float | None = field(default=None, repr=False)
    _cluster_cpu_ema: float | None = field(default=None, repr=False)

    def _cached_driver_snapshot(self):
        now = time.time()
        if self._driver_snapshot is not None and now - self._driver_snapshot_at < 2.0:
            return self._driver_snapshot
        cpu_count, cpu_util = 1, 0.0
        try:
            import psutil

            cpu_count = psutil.cpu_count(logical=True) or 1
            raw = psutil.cpu_percent(interval=0.5) / 100.0
            if self._driver_cpu_ema is None:
                self._driver_cpu_ema = raw
            else:
                self._driver_cpu_ema = 0.25 * raw + 0.75 * self._driver_cpu_ema
            cpu_util = self._driver_cpu_ema
        except Exception:
            if self._driver_cpu_ema is not None:
                cpu_util = self._driver_cpu_ema
        self._driver_snapshot = type(
            "Snap", (), {"cpu_utilization": cpu_util, "cpu_cores_total": cpu_count}
        )()
        self._driver_snapshot_at = now
        return self._driver_snapshot

    def cluster_status(self) -> dict[str, Any]:
        stats = self.cluster.cluster_stats()
        live = self.cluster.live_nodes()
        driver_snap = self._cached_driver_snapshot()
        driver_host = socket.gethostname()
        include_driver = driver_host not in {n.hostname for n in live}
        raw_pct = DriverCluster.aggregate_cpu_utilization_pct(
            live,
            extra_util=driver_snap.cpu_utilization if include_driver else 0.0,
            extra_cores=driver_snap.cpu_cores_total if include_driver else 0,
        )
        if self._cluster_cpu_ema is None:
            self._cluster_cpu_ema = raw_pct
        else:
            self._cluster_cpu_ema = round(0.35 * raw_pct + 0.65 * self._cluster_cpu_ema, 1)
        stats["cpu_utilization_pct"] = self._cluster_cpu_ema
        stats["driver_host_included"] = include_driver
        if self.job_manager:
            stats["active_jobs"] = len(self.job_manager._jobs)
        leader = None
        if self.coordinator:
            info = self.coordinator.election.current_leader()
            if info:
                leader = {"driver_id": info[0], "term": info[1]}
            stats["is_leader"] = self.coordinator.is_leader
        stats["leader"] = leader
        if self.mesh:
            stats["site_id"] = self.mesh.config.site_id
        return stats

    def mesh_payload(self) -> dict:
        if self.mesh:
            return self.mesh.payload()
        return {"site_id": "default", "relay": None, "peers": []}

    def memory_pool_payload(self) -> dict:
        stats = self.memory.pool_stats(self.cluster.live_nodes())
        return stats.to_dict()

    def memory_allocations_payload(self) -> list[dict]:
        return [a.to_dict() for a in self.memory.list_allocations()]

    def _estimate_savings(self, stats: dict) -> int:
        """Rough estimate: idle cores × $0.05/hr × 730 hrs/month."""
        free = stats.get("free_cpu_cores", 0)
        return int(free * 0.05 * 730 * 24)

    def nodes_payload(self, tenant: str | None = None) -> list[dict]:
        nodes = self.cluster.live_nodes()
        tenant = tenant or get_current_tenant()
        payload = []
        for n in nodes:
            host = _parse_host_metrics(n.tags.get("host_metrics", ""))
            cpu = host.get("cpu", {}) if host else {}
            mem = host.get("memory", {}) if host else {}
            procs = host.get("processes", {}) if host else {}
            item = {
                "node_id": n.node_id,
                "hostname": n.hostname,
                "state": n.state.name,
                "cpu_total": n.resources.cpu_cores_total,
                "cpu_physical": cpu.get("physical_cores") or n.tags.get("cpu_physical"),
                "cpu_free": round(n.resources.cpu_cores_free, 1),
                "cpu_utilization": round(n.resources.cpu_utilization * 100, 1),
                "cpu_user_pct": cpu.get("user_pct"),
                "cpu_system_pct": cpu.get("system_pct"),
                "cpu_idle_pct": cpu.get("idle_pct"),
                "cpu_brand": cpu.get("brand"),
                "load_avg": cpu.get("load_avg"),
                "ram_gb_total": round(n.resources.ram_gb_total, 1),
                "ram_gb_free": round(n.resources.ram_gb_free, 1),
                "memory_used_gb": mem.get("used_gb"),
                "memory_wired_gb": mem.get("wired_gb"),
                "memory_compressed_gb": mem.get("compressed_gb"),
                "memory_swap_gb": mem.get("swap_gb"),
                "process_count": procs.get("total"),
                "thread_count": procs.get("threads_total"),
                "top_processes": procs.get("top", []),
                "gpu_count": n.resources.gpu_count,
                "gpu_name": (host.get("gpu") or {}).get("name") if host else None,
                "battery_pct": n.resources.battery_pct,
                "preemptible": n.preemptible,
                "user_active": n.resources.user_active,
                "location": n.location,
                "pool": n.pool.value,
                "reliability": round(n.reliability_score, 2),
                "is_remote": self.cluster.is_remote(n.node_id),
                "tenant": n.tags.get("tenant", n.location),
                "os": n.tags.get("os"),
                "host_metrics": host,
            }
            if isinstance(item["cpu_physical"], str):
                try:
                    item["cpu_physical"] = int(item["cpu_physical"])
                except ValueError:
                    item["cpu_physical"] = None
            payload.append(item)
        if tenant:
            payload = [p for p in payload if p["tenant"] == tenant]
        return payload

    def sites_payload(self) -> list[dict]:
        sites: dict[str, dict] = {}
        for n in self.cluster.live_nodes():
            site = n.location or "default"
            if site not in sites:
                sites[site] = {"site": site, "nodes": 0, "healthy": 0, "tenant": n.tags.get("tenant", site)}
            sites[site]["nodes"] += 1
            if n.state.name == "HEALTHY":
                sites[site]["healthy"] += 1
        return list(sites.values())

    def jobs_payload(self) -> list[dict]:
        if not self.job_manager:
            return []
        result = []
        for job in self.job_manager._jobs.values():
            tasks = self.job_manager._job_tasks.get(job.job_id, [])
            result.append({
                "job_id": job.job_id,
                "name": job.name,
                "state": job.state.name,
                "task_count": len(tasks),
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "name": t.name,
                        "state": t.state.name,
                        "progress": round(t.progress_pct, 1),
                        "assigned_node": t.assigned_node,
                        "checkpoint": t.checkpoint,
                    }
                    for t in tasks
                ],
                "error": job.error,
                "created": job.job_id[:8],
            })
        return result

    def tasks_payload(self) -> list[dict]:
        tasks = []
        if self.job_manager:
            for t in self.job_manager._tasks().values():
                tasks.append({
                    "task_id": t.task_id,
                    "job_id": t.job_id,
                    "name": t.name,
                    "state": t.state.name,
                    "progress": round(t.progress_pct, 1),
                    "assigned_node": t.assigned_node,
                    "cpu_cores": t.requirements.cpu_cores,
                    "ram_gb": t.requirements.ram_gb,
                })
        return tasks

    def libraries_payload(self) -> list[dict]:
        """Libraries reported by agents and the driver host."""
        package_nodes: dict[str, set[str]] = {}
        for n in self.cluster.live_nodes():
            raw = n.tags.get("libraries", "")
            for pkg in raw.split(","):
                pkg = pkg.strip().lower()
                if not pkg:
                    continue
                package_nodes.setdefault(pkg, set()).add(n.node_id)
        if self.library_installer:
            for pkg in self.library_installer.driver_library_names():
                package_nodes.setdefault(pkg, set()).add("driver")
        return [
            {
                "name": name,
                "version": "",
                "nodes": len(nodes),
                "pool": "cluster",
            }
            for name, nodes in sorted(package_nodes.items())
        ]


def _parse_host_metrics(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


# Set by create_app()
app_context: Optional[AppContext] = None
