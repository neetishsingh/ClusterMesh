from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mesh.api.context import AppContext, app_context
from mesh.api.events import EventBus, event_bus
from mesh.api.auth import AuthConfig, AuthMiddleware, get_current_tenant
from mesh.driver.library_installer import LibraryInstaller
from mesh.models.enums import NodeState
from mesh.models.task import ResourceRequirements, TaskSpec


def _notebook_task_spec() -> TaskSpec:
    return TaskSpec(
        name="notebook.exec",
        requirements=ResourceRequirements(cpu_cores=1, ram_gb=0.5),
    )


def _notebook_runnable_nodes(cluster) -> list:
    """Nodes that can actually accept a notebook cell (healthy + resources)."""
    spec = _notebook_task_spec()
    runnable = []
    for node in cluster.live_nodes():
        if node.state != NodeState.HEALTHY:
            continue
        if cluster.placement_engine.place(spec, [node]):
            runnable.append(node)
    return runnable


def create_app(ctx: Optional[AppContext] = None, auth: Optional[AuthConfig] = None) -> FastAPI:
    global app_context
    if ctx:
        app_context = ctx
        ctx.event_bus = event_bus
        if ctx.library_installer is None:
            ctx.library_installer = LibraryInstaller(cluster=ctx.cluster, event_bus=event_bus)

    app = FastAPI(
        title="ComputeMesh API",
        description="Cluster management API for ComputeMesh",
        version="0.9.0",
    )
    auth_config = auth or AuthConfig.from_env()
    if auth_config.enabled:
        app.add_middleware(AuthMiddleware, config=auth_config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/cluster/status")
    def cluster_status():
        return app_context.cluster_status()

    @app.get("/api/v1/nodes")
    def list_nodes(request: Request):
        tenant = request.headers.get("X-Tenant-Id")
        return {"nodes": app_context.nodes_payload(tenant=tenant)}

    @app.get("/api/v1/nodes/{node_id}")
    def get_node(node_id: str):
        for n in app_context.nodes_payload():
            if n["node_id"] == node_id:
                return n
        return {"error": "not found"}

    @app.post("/api/v1/nodes/{node_id}/pause")
    def pause_node(node_id: str):
        event_bus.warn("cluster", f"Pause requested for node {node_id}", node_id=node_id)
        return {"ok": True, "action": "pause", "node_id": node_id}

    @app.post("/api/v1/nodes/{node_id}/drain")
    def drain_node(node_id: str):
        event_bus.info("cluster", f"Drain started for node {node_id}", node_id=node_id)
        return {"ok": True, "action": "drain", "node_id": node_id}

    @app.post("/api/v1/nodes/{node_id}/shell")
    def run_node_shell(node_id: str, body: dict):
        import socket

        from mesh.agent.shell import run_shell_command
        from mesh.proto import mesh_pb2

        command = str(body.get("command", "")).strip()
        if not command:
            return {"ok": False, "error": "command required"}
        cwd = str(body.get("cwd", "") or "")
        timeout = int(body.get("timeout", 60) or 60)

        node = app_context.cluster.get_node(node_id)
        if not node:
            return {"ok": False, "error": "node not found"}

        remote = app_context.cluster.get_remote(node_id)
        if remote:
            try:
                resp = remote.run_shell(
                    mesh_pb2.ShellCommandRequest(
                        command=command,
                        working_dir=cwd,
                        timeout_seconds=timeout,
                    )
                )
                event_bus.info(
                    "shell",
                    f"Ran on {node.hostname}: {command[:120]}",
                    node_id=node_id,
                    exit_code=resp.exit_code,
                )
                return {
                    "ok": resp.ok,
                    "exit_code": resp.exit_code,
                    "stdout": resp.stdout,
                    "stderr": resp.stderr,
                    "message": resp.message,
                    "duration_seconds": resp.duration_seconds,
                    "hostname": node.hostname,
                    "node_id": node_id,
                }
            except Exception as exc:
                event_bus.error("shell", f"Failed on {node.hostname}: {exc}", node_id=node_id)
                return {"ok": False, "error": str(exc), "node_id": node_id}

        if node.hostname == socket.gethostname():
            result = run_shell_command(command, cwd, timeout)
            event_bus.info(
                "shell",
                f"Ran locally on {node.hostname}: {command[:120]}",
                node_id=node_id,
                exit_code=result["exit_code"],
            )
            return {**result, "hostname": node.hostname, "node_id": node_id}

        return {"ok": False, "error": "node has no remote agent connection", "node_id": node_id}

    @app.get("/api/v1/jobs")
    def list_jobs():
        return {"jobs": app_context.jobs_payload()}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        for j in app_context.jobs_payload():
            if j["job_id"] == job_id:
                return j
        return {"error": "not found"}

    @app.delete("/api/v1/jobs/{job_id}")
    def cancel_job(job_id: str):
        if app_context.job_manager:
            app_context.job_manager.cancel_job(job_id)
            event_bus.info("jobs", f"Job cancelled: {job_id}", job_id=job_id)
        return {"ok": True}

    @app.get("/api/v1/tasks")
    def list_tasks():
        return {"tasks": app_context.tasks_payload()}

    @app.get("/api/v1/logs")
    def get_logs(limit: int = 200, level: str | None = None, source: str | None = None, q: str | None = None):
        return {"logs": event_bus.get_logs(limit=limit, level=level, source=source, search=q)}

    @app.get("/api/v1/libraries")
    def list_libraries():
        return {"libraries": app_context.libraries_payload()}

    @app.post("/api/v1/libraries/install")
    def install_library(body: dict):
        installer = app_context.library_installer
        if installer is None:
            installer = LibraryInstaller(cluster=app_context.cluster, event_bus=event_bus)
            app_context.library_installer = installer
        return installer.install(
            body.get("package_name", ""),
            body.get("version", ""),
            pool=body.get("pool", "all"),
            include_driver=body.get("include_driver", True),
            node_ids=body.get("node_ids"),
        )

    @app.post("/api/v1/cluster/rebalance")
    def trigger_rebalance():
        count = app_context.job_manager.run_rebalance() if app_context.job_manager else 0
        event_bus.info("scheduler", f"Rebalance triggered — {count} tasks migrated")
        return {"ok": True, "migrations": count}

    @app.get("/api/v1/metrics/savings")
    def savings_metrics():
        stats = app_context.cluster_status()
        free = stats.get("free_cpu_cores", 0)
        return {
            "estimated_monthly_savings_usd": int(free * 0.05 * 730 * 24) if free > 0 else 0,
            "utilized_cores": stats.get("total_cpu_cores", 0) - free,
            "idle_cores": free,
            "total_cores": stats.get("total_cpu_cores", 0),
            "has_data": stats.get("total_nodes", 0) > 0,
        }

    @app.post("/api/v1/notebook/execute")
    def notebook_execute(body: dict):
        from mesh.notebook.runner import execute_code

        code = body.get("code", "")
        language = body.get("language", "python")
        mode = body.get("mode", "mesh")
        runnable = _notebook_runnable_nodes(app_context.cluster)

        if mode != "local" and runnable:
            try:
                output = app_context.job_manager.submit_notebook_cell(
                    code, language=language, timeout=body.get("timeout", 120)
                )
                output["mode"] = "mesh"
                output["node"] = runnable[0].hostname
                event_bus.info("notebook", f"Cell executed on {output['node']} ({language})")
                return output
            except Exception as exc:
                event_bus.warn(
                    "notebook",
                    f"Mesh execution failed ({exc}) — running locally on driver",
                )

        if mode == "mesh" and not runnable:
            event_bus.info("notebook", "No mesh workers ready — running cell locally on driver")
        output = execute_code(code, language=language)
        output["mode"] = "local"
        output["node"] = "driver"
        return output

    @app.get("/api/v1/notebook/status")
    def notebook_status():
        runnable = _notebook_runnable_nodes(app_context.cluster)
        live = app_context.cluster.live_nodes()
        pyspark = any("pyspark" in n.tags.get("libraries", "").lower() for n in live)
        return {
            "workers_available": len(runnable),
            "workers": [{"hostname": n.hostname, "location": n.location} for n in runnable],
            "local_available": True,
            "pyspark_ready": pyspark,
        }

    @app.get("/api/v1/cluster/join-info")
    def join_info():
        import socket
        host = socket.gethostname()
        return {
            "driver_grpc": "50050",
            "agent_grpc": "50051",
            "dashboard_port": 8080,
            "relay_port": 6000,
            "install": "pip install -e . && mesh-agent --driver DRIVER_HOST:50050 --location SITE",
            "requirements": ["Python 3.11+", "pip", "network access to driver port 50050"],
            "docs": "/docs/join-mesh.md",
        }

    @app.get("/api/v1/discovery/sites")
    def list_sites():
        return {"sites": app_context.sites_payload()}

    @app.get("/api/v1/auth/status")
    def auth_status():
        return {"auth_enabled": auth_config.enabled, "tenant": get_current_tenant()}

    @app.get("/api/v1/mesh")
    def mesh_status():
        return app_context.mesh_payload()

    @app.get("/api/v1/mesh/peers")
    def mesh_peers():
        payload = app_context.mesh_payload()
        return {"peers": payload.get("peers", [])}

    @app.post("/api/v1/mesh/peers")
    def add_mesh_peer(body: dict):
        from mesh.meshvpn.site import SitePeer

        peer = SitePeer(
            site_id=body.get("site_id", ""),
            relay_address=body.get("relay_address", ""),
            grpc_address=body.get("grpc_address", ""),
            region=body.get("region", ""),
        )
        if app_context.mesh:
            app_context.mesh.add_peer(peer)
            event_bus.info("mesh", f"Peer added: {peer.site_id}", site=peer.site_id)
        return {"ok": True, "peer": peer.to_dict()}

    @app.post("/api/v1/mesh/probe")
    def probe_mesh_peers():
        if app_context.mesh:
            app_context.mesh.probe_peers()
            event_bus.info("mesh", "Peer probe completed")
        return app_context.mesh_payload()

    @app.get("/api/v1/memory/pool")
    def memory_pool():
        return app_context.memory_pool_payload()

    @app.get("/api/v1/memory/allocations")
    def memory_allocations():
        return {"allocations": app_context.memory_allocations_payload()}

    @app.post("/api/v1/memory/allocate")
    def memory_allocate(body: dict):
        size = float(body.get("size_gb", 0))
        owner = body.get("owner", "")
        alloc = app_context.memory.allocate(
            size_gb=size,
            nodes=app_context.cluster.live_nodes(),
            owner=owner,
        )
        if not alloc:
            return {"ok": False, "error": "insufficient memory"}
        event_bus.info("memory", f"Allocated {size}GB logical memory", allocation_id=alloc.allocation_id)
        return {"ok": True, "allocation": alloc.to_dict()}

    @app.delete("/api/v1/memory/allocations/{allocation_id}")
    def memory_release(allocation_id: str):
        ok = app_context.memory.release(allocation_id)
        if ok:
            event_bus.info("memory", f"Released allocation {allocation_id}")
        return {"ok": ok}

    @app.get("/api/v1/scheduler/benchmark")
    def scheduler_benchmark(nodes: int = 1000, iterations: int = 50):
        from mesh.scheduler.benchmark import benchmark_placement

        return benchmark_placement(node_count=nodes, iterations=iterations).to_dict()

    @app.websocket("/api/v1/stream")
    async def websocket_stream(websocket: WebSocket):
        await websocket.accept()
        queue: list = []

        def on_event(event):
            queue.append(event.to_dict())

        event_bus.subscribe(on_event)
        try:
            while True:
                if queue:
                    for item in queue:
                        await websocket.send_json({"type": "event", "data": item})
                    queue.clear()
                import asyncio
                await asyncio.sleep(0.5)
                if app_context:
                    await websocket.send_json({
                        "type": "cluster",
                        "data": app_context.cluster_status(),
                    })
        except WebSocketDisconnect:
            pass
        finally:
            event_bus.unsubscribe(on_event)

    # Serve built frontend if available
    static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
