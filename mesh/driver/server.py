from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

import grpc

from mesh.api.events import event_bus
from mesh.driver.cluster import DriverCluster, RemoteAgent
from mesh.models.enums import NodeState, ResourcePool
from mesh.models.node import Node, NodeResources
from mesh.proto import mesh_pb2, mesh_pb2_grpc

logger = logging.getLogger(__name__)


def _snapshot_to_resources(msg: mesh_pb2.ResourceReport) -> NodeResources:
    battery = msg.battery_pct if msg.battery_pct >= 0 else None
    return NodeResources(
        cpu_cores_total=msg.cpu_cores_total,
        cpu_cores_free=msg.cpu_cores_free,
        ram_gb_total=msg.ram_gb_total,
        ram_gb_free=msg.ram_gb_free,
        gpu_count=msg.gpu_count,
        vram_gb_free=msg.vram_gb_free,
        cuda_version=msg.cuda_version or None,
        network_gbps=msg.network_gbps,
        battery_pct=battery,
        cpu_utilization=msg.cpu_utilization,
        user_active=msg.user_active,
    )


def _make_remote_agent(node_id: str, agent_address: str) -> RemoteAgent:
    channel = grpc.insecure_channel(agent_address)
    stub = mesh_pb2_grpc.AgentStub(channel)

    def assign_task(req: mesh_pb2.TaskAssignment) -> mesh_pb2.Ack:
        return stub.AssignTask(req, timeout=10)

    def cancel_task(req: mesh_pb2.TaskCancelRequest) -> mesh_pb2.Ack:
        return stub.CancelTask(req, timeout=5)

    def pause_task(req: mesh_pb2.TaskPauseRequest) -> mesh_pb2.Ack:
        return stub.PauseTask(req, timeout=5)

    def install_library(req: mesh_pb2.LibraryInstallRequest) -> mesh_pb2.Ack:
        return stub.InstallLibrary(req, timeout=120)

    def run_shell(req: mesh_pb2.ShellCommandRequest) -> mesh_pb2.ShellCommandResponse:
        timeout = max(10, (req.timeout_seconds or 60) + 5)
        return stub.RunShellCommand(req, timeout=timeout)

    return RemoteAgent(
        node_id=node_id,
        agent_address=agent_address,
        assign_task=assign_task,
        cancel_task=cancel_task,
        pause_task=pause_task,
        install_library=install_library,
        run_shell=run_shell,
    )


class DriverServicer(mesh_pb2_grpc.DriverServicer):
    """gRPC service for agent → driver communication."""

    def __init__(self, cluster: DriverCluster, job_manager: Optional[object] = None) -> None:
        self.cluster = cluster
        self.job_manager = job_manager

    def RegisterNode(self, request, context):
        resources = _snapshot_to_resources(request.resources)
        tags = {
            "os": request.os_name,
            "libraries": ",".join(request.libraries[:100]),
        }
        if request.resources.host_metrics_json:
            tags["host_metrics"] = request.resources.host_metrics_json
        node = Node(
            node_id=request.node_id,
            hostname=request.hostname,
            resources=resources,
            preemptible=request.preemptible,
            location=request.location or "default",
            pool=ResourcePool.NIGHT if request.preemptible else ResourcePool.CPU,
            reliability_score=0.7 if request.preemptible else 0.9,
            tags=tags,
        )
        remote = _make_remote_agent(request.node_id, request.agent_address)
        self.cluster.register_node(node, remote=remote)
        event_bus.info("driver", f"Node registered: {request.node_id}", node_id=request.node_id, hostname=request.hostname)
        return mesh_pb2.RegisterResponse(
            accepted=True,
            message="welcome",
            heartbeat_interval_seconds=self.cluster.heartbeat_interval,
        )

    def Heartbeat(self, request, context):
        state = self.cluster.record_heartbeat(request.node_id)
        return mesh_pb2.HeartbeatResponse(ok=True, node_state=state.name)

    def ReportResources(self, request, context):
        resources = _snapshot_to_resources(request)
        self.cluster.update_node_resources(
            request.node_id,
            resources,
            host_metrics_json=request.host_metrics_json or "",
        )
        return mesh_pb2.Ack(ok=True)

    def PreemptionWarning(self, request, context):
        logger.warning(
            "Preemption on %s: cpu=%.0f%% reason=%s",
            request.node_id,
            request.cpu_utilization * 100,
            request.reason,
        )
        from mesh.api.events import event_bus
        event_bus.warn("preemption", f"Preemption on {request.node_id}: {request.reason}", node_id=request.node_id)
        self.cluster.update_node_state(request.node_id, NodeState.PREEMPTED)
        if self.job_manager is not None:
            self.job_manager.handle_preemption(request.node_id)
        return mesh_pb2.Ack(ok=True, message="preemption handled")

    def TaskProgress(self, request, context):
        task = self.cluster.tasks.get(request.task_id)
        if task:
            task.progress = request.progress
            if request.state_json:
                task.state_data = json.loads(request.state_json)
            self.cluster.checkpoint_manager.save(
                task,
                state_data=task.state_data,
                timestamp=time.time(),
            )
        return mesh_pb2.Ack(ok=True)

    def TaskComplete(self, request, context):
        from mesh.models.enums import TaskState
        from mesh.models.job import JobState

        task = self.cluster.tasks.get(request.task_id)
        if not task:
            return mesh_pb2.Ack(ok=False, message="unknown task")

        if request.success:
            task.state = TaskState.COMPLETED
            if self.job_manager is not None:
                job = self.job_manager._find_job_for_task(task)
                if job:
                    result = json.loads(request.result_json) if request.result_json else None
                    self.job_manager._on_task_complete(task, job, result)
        else:
            task.state = TaskState.FAILED
            if self.job_manager is not None:
                job = self.job_manager._find_job_for_task(task)
                if job:
                    self.job_manager._on_task_failed(task, job, request.error)

        return mesh_pb2.Ack(ok=True)


class DriverServer:
    def __init__(
        self,
        address: str = "0.0.0.0:50050",
        cluster: Optional[DriverCluster] = None,
        job_manager: Optional[object] = None,
    ) -> None:
        self.address = address
        self.cluster = cluster or DriverCluster()
        self.job_manager = job_manager
        self._server: grpc.Server | None = None
        self._health_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, blocking: bool = False) -> None:
        from concurrent import futures

        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
        mesh_pb2_grpc.add_DriverServicer_to_server(
            DriverServicer(self.cluster, self.job_manager), self._server
        )
        self._server.add_insecure_port(self.address)
        self._server.start()
        logger.info("Driver gRPC server listening on %s", self.address)

        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()

        if blocking:
            self._server.wait_for_termination()

    def _health_loop(self) -> None:
        while not self._stop.is_set():
            self.cluster.evaluate_health()
            self._stop.wait(1.0)

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.stop(grace=2)


def main() -> None:
    import argparse
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="ClusterMesh Driver Server")
    parser.add_argument("--address", default="0.0.0.0:50050", help="gRPC listen address")
    parser.add_argument("--db", default=os.environ.get("MESH_STATE_DB", "clustermesh.db"),
                        help="SQLite state database path")
    parser.add_argument("--dashboard-port", type=int, default=int(os.environ.get("MESH_DASHBOARD_PORT", "8080")),
                        help="Dashboard HTTP port (0 to disable)")
    args = parser.parse_args()

    from mesh.api.server import MeshPlatform

    platform = MeshPlatform(
        grpc_address=args.address,
        api_port=args.dashboard_port if args.dashboard_port > 0 else 0,
        db_path=args.db,
    )
    platform.start()
    if args.dashboard_port <= 0:
        logging.info("Dashboard disabled")
    else:
        logging.info("Dashboard: http://localhost:%d", args.dashboard_port)
    logging.info("Driver HA enabled — state: %s", args.db)
    platform.run_forever()


if __name__ == "__main__":
    main()
