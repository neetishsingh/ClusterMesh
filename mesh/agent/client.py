from __future__ import annotations

import json
import logging
import time

import grpc

from mesh.agent.monitor import ResourceMonitor, ResourceSnapshot
from mesh.proto import mesh_pb2, mesh_pb2_grpc

logger = logging.getLogger(__name__)


class DriverClient:
    """gRPC client for agent → driver communication."""

    def __init__(self, driver_address: str, node_id: str) -> None:
        self.driver_address = driver_address
        self.node_id = node_id
        self._channel: grpc.Channel | None = None
        self._stub: mesh_pb2_grpc.DriverStub | None = None
        self.heartbeat_interval = 2.0

    def connect(self) -> None:
        self._channel = grpc.insecure_channel(self.driver_address)
        self._stub = mesh_pb2_grpc.DriverStub(self._channel)

    def close(self) -> None:
        if self._channel:
            self._channel.close()

    @property
    def stub(self) -> mesh_pb2_grpc.DriverStub:
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        return self._stub

    def register(
        self,
        hostname: str,
        agent_address: str,
        os_name: str,
        location: str,
        preemptible: bool,
        snapshot: ResourceSnapshot,
        libraries: list[str],
    ) -> mesh_pb2.RegisterResponse:
        req = mesh_pb2.RegisterRequest(
            node_id=self.node_id,
            hostname=hostname,
            agent_address=agent_address,
            os_name=os_name,
            location=location,
            preemptible=preemptible,
            resources=self._resource_msg(snapshot),
            libraries=libraries,
        )
        resp = self.stub.RegisterNode(req, timeout=10)
        if resp.accepted:
            self.heartbeat_interval = resp.heartbeat_interval_seconds or 2.0
        return resp

    def heartbeat(self) -> mesh_pb2.HeartbeatResponse:
        req = mesh_pb2.HeartbeatRequest(node_id=self.node_id, timestamp=time.time())
        return self.stub.Heartbeat(req, timeout=5)

    def report_resources(self, snapshot: ResourceSnapshot) -> mesh_pb2.Ack:
        msg = self._resource_msg(snapshot)
        msg.node_id = self.node_id
        return self.stub.ReportResources(msg, timeout=5)

    def preemption_warning(self, cpu_utilization: float, reason: str) -> mesh_pb2.Ack:
        req = mesh_pb2.PreemptionRequest(
            node_id=self.node_id,
            cpu_utilization=cpu_utilization,
            reason=reason,
        )
        return self.stub.PreemptionWarning(req, timeout=5)

    def task_progress(self, task_id: str, progress: float, total_work: float, state: dict) -> mesh_pb2.Ack:
        req = mesh_pb2.TaskProgressReport(
            task_id=task_id,
            node_id=self.node_id,
            progress=progress,
            total_work=total_work,
            state_json=json.dumps(state),
        )
        return self.stub.TaskProgress(req, timeout=5)

    def task_complete(
        self, task_id: str, success: bool, result: object = None, error: str = ""
    ) -> mesh_pb2.Ack:
        req = mesh_pb2.TaskCompleteReport(
            task_id=task_id,
            node_id=self.node_id,
            success=success,
            result_json=json.dumps(result) if result is not None else "",
            error=error or "",
        )
        return self.stub.TaskComplete(req, timeout=5)

    def _resource_msg(self, s: ResourceSnapshot) -> mesh_pb2.ResourceReport:
        return mesh_pb2.ResourceReport(
            node_id=self.node_id,
            cpu_cores_total=s.cpu_cores_total,
            cpu_cores_physical=s.cpu_cores_physical or s.cpu_cores_total,
            cpu_cores_free=s.cpu_cores_free,
            ram_gb_total=s.ram_gb_total,
            ram_gb_free=s.ram_gb_free,
            gpu_count=s.gpu_count,
            vram_gb_free=s.vram_gb_free,
            cuda_version=s.cuda_version or "",
            network_gbps=s.network_gbps,
            battery_pct=s.battery_pct or -1,
            cpu_utilization=s.cpu_utilization,
            user_active=s.user_active,
            host_metrics_json=s.host_metrics_json or "",
        )
