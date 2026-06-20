from __future__ import annotations

import socket
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

from mesh.libraries.manager import LibraryManager
from mesh.api.events import EventBus
from mesh.driver.cluster import DriverCluster
from mesh.models.enums import NodeState, ResourcePool
from mesh.proto import mesh_pb2
from mesh.scheduler.pools import PoolRouter


@dataclass
class TargetResult:
    target: str
    hostname: str
    ok: bool
    message: str
    log: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "hostname": self.hostname,
            "ok": self.ok,
            "message": self.message,
            "log": self.log,
        }


@dataclass
class LibraryInstaller:
    cluster: DriverCluster
    event_bus: EventBus
    driver_libraries: LibraryManager = field(default_factory=LibraryManager)
    pool_router: PoolRouter = field(default_factory=PoolRouter)

    def install(
        self,
        package_name: str,
        version: str = "",
        *,
        pool: str = "all",
        include_driver: bool = True,
        node_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        install_id = str(uuid.uuid4())[:8]
        pkg = package_name.strip()
        ver = version.strip()
        if ver.lower() in ("latest", "*"):
            ver = ""

        targets = self._resolve_targets(pool, node_ids, include_driver)
        total = len(targets)
        results: list[TargetResult] = []

        self.event_bus.info(
            "libraries",
            f"Installing {pkg}{('==' + ver) if ver else ''} on {total} target(s)",
            install_id=install_id,
            package=pkg,
            version=ver or "latest",
            total=total,
        )

        if total == 0:
            self.event_bus.warn("libraries", "No install targets available", install_id=install_id)
            return {
                "ok": False,
                "install_id": install_id,
                "package": pkg,
                "version": ver or "latest",
                "results": [],
                "message": "No targets available — start mesh-agent or enable driver install",
            }

        completed = 0

        def run_one(item: tuple[str, str, Optional[object]]) -> TargetResult:
            kind, hostname, handle = item
            label = f"{hostname} ({kind})"
            self.event_bus.info(
                "libraries",
                f"Starting pip install on {label}",
                install_id=install_id,
                target=kind,
                hostname=hostname,
            )
            try:
                if kind == "driver":
                    lib, log = self.driver_libraries.install(pkg, ver)
                    msg = f"Installed {lib.name} {lib.version}"
                    self.event_bus.info(
                        "libraries",
                        f"Success on driver: {msg}",
                        install_id=install_id,
                        target="driver",
                    )
                    return TargetResult("driver", hostname, True, msg, log)
                remote = handle
                assert remote is not None
                ack = remote.install_library(
                    mesh_pb2.LibraryInstallRequest(package_name=pkg, version=ver)
                )
                log = ack.message or ""
                if ack.ok:
                    self._merge_library_tag(remote.node_id, pkg)
                    self.event_bus.info(
                        "libraries",
                        f"Success on {hostname}: {log[:200]}",
                        install_id=install_id,
                        target=remote.node_id,
                        node_id=remote.node_id,
                    )
                    return TargetResult(remote.node_id, hostname, True, log or "installed", log)
                self.event_bus.error(
                    "libraries",
                    f"Failed on {hostname}: {log[:300]}",
                    install_id=install_id,
                    target=remote.node_id,
                )
                return TargetResult(remote.node_id, hostname, False, log or "install failed", log)
            except Exception as exc:
                err = str(exc)
                self.event_bus.error(
                    "libraries",
                    f"Failed on {label}: {err}",
                    install_id=install_id,
                    target=kind,
                )
                return TargetResult(kind if kind == "driver" else str(handle), hostname, False, err, err)

        with ThreadPoolExecutor(max_workers=min(8, total)) as pool_exec:
            futures = {pool_exec.submit(run_one, t): t for t in targets}
            for fut in as_completed(futures):
                result = fut.result()
                results.append(result)
                completed += 1
                self.event_bus.info(
                    "libraries",
                    f"Progress {completed}/{total} — {'ok' if result.ok else 'failed'} on {result.hostname}",
                    install_id=install_id,
                    step=completed,
                    total=total,
                )

        ok_count = sum(1 for r in results if r.ok)
        all_ok = ok_count == total
        summary = f"Installed on {ok_count}/{total} targets"
        if all_ok:
            self.event_bus.info("libraries", summary, install_id=install_id, package=pkg)
        else:
            self.event_bus.warn("libraries", summary, install_id=install_id, package=pkg)

        return {
            "ok": all_ok,
            "install_id": install_id,
            "package": pkg,
            "version": ver or "latest",
            "total_targets": total,
            "results": [r.to_dict() for r in results],
            "message": summary,
        }

    def _resolve_targets(
        self,
        pool: str,
        node_ids: Optional[list[str]],
        include_driver: bool,
    ) -> list[tuple[str, str, Optional[object]]]:
        targets: list[tuple[str, str, Optional[object]]] = []
        driver_host = socket.gethostname()

        nodes = self.cluster.live_nodes()
        if node_ids:
            nodes = [n for n in nodes if n.node_id in node_ids]

        pool_enum: Optional[ResourcePool] = None
        if pool and pool.lower() not in ("all", ""):
            try:
                pool_enum = ResourcePool[pool.upper()]
            except KeyError:
                pool_enum = None

        if pool_enum is not None:
            nodes = self.pool_router.eligible_nodes(nodes, pool=pool_enum)

        agent_hosts = {n.hostname for n in nodes}
        for node in nodes:
            if node.state == NodeState.DEAD:
                continue
            remote = self.cluster.get_remote(node.node_id)
            if remote:
                targets.append(("agent", node.hostname, remote))

        if include_driver and driver_host not in agent_hosts:
            targets.insert(0, ("driver", driver_host, None))

        return targets

    def _merge_library_tag(self, node_id: str, package_name: str) -> None:
        node = self.cluster.get_node(node_id)
        if not node:
            return
        from dataclasses import replace

        libs = {p.strip().lower() for p in node.tags.get("libraries", "").split(",") if p.strip()}
        libs.add(package_name.lower())
        self.cluster._nodes[node_id] = replace(
            node, tags={**node.tags, "libraries": ",".join(sorted(libs))}
        )

    def driver_library_names(self) -> set[str]:
        return {n.lower() for n in self.driver_libraries.list_names()}
