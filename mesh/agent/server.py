from __future__ import annotations

from concurrent import futures
import json
import logging
import threading

import grpc

from mesh.agent.executor import AgentTaskRunner
from mesh.agent.library import LibraryManager
from mesh.proto import mesh_pb2, mesh_pb2_grpc

logger = logging.getLogger(__name__)


class AgentServicer(mesh_pb2_grpc.AgentServicer):
    """gRPC service that receives task assignments from the driver."""

    def __init__(self, runner: AgentTaskRunner, libraries: LibraryManager | None = None) -> None:
        self.runner = runner
        self.libraries = libraries or LibraryManager()

    def AssignTask(self, request, context):
        assignment = {
            "task_id": request.task_id,
            "job_id": request.job_id,
            "task_name": request.task_name,
            "cpu_cores": request.cpu_cores,
            "ram_gb": request.ram_gb,
            "gpu_count": request.gpu_count,
            "checkpoint": request.checkpoint,
            "checkpoint_interval": request.checkpoint_interval,
            "total_work": request.total_work,
            "resume_progress": request.resume_progress,
            "resume_state_json": request.resume_state_json,
        }
        ok = self.runner.assign(assignment)
        return mesh_pb2.Ack(ok=ok, message="assigned" if ok else "already running")

    def CancelTask(self, request, context):
        self.runner.cancel(request.task_id)
        return mesh_pb2.Ack(ok=True, message="cancelled")

    def PauseTask(self, request, context):
        self.runner.pause(request.task_id)
        return mesh_pb2.Ack(ok=True, message=f"paused: {request.reason}")

    def InstallLibrary(self, request, context):
        ver = request.version.strip()
        if ver.lower() in ("latest", "*"):
            ver = ""
        try:
            lib, log = self.libraries.install(request.package_name, ver)
            tail = log[-4000:] if len(log) > 4000 else log
            return mesh_pb2.Ack(
                ok=True,
                message=f"Installed {lib.name} {lib.version}\n{tail}".strip(),
            )
        except Exception as exc:
            return mesh_pb2.Ack(ok=False, message=str(exc))

    def RunShellCommand(self, request, context):
        from mesh.agent.shell import run_shell_command

        result = run_shell_command(
            request.command,
            working_dir=request.working_dir,
            timeout_seconds=request.timeout_seconds or 60,
        )
        return mesh_pb2.ShellCommandResponse(
            ok=result["ok"],
            exit_code=result["exit_code"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            message=result["message"],
            duration_seconds=result["duration_seconds"],
        )


class AgentServer:
    def __init__(
        self,
        address: str,
        runner: AgentTaskRunner,
        libraries: LibraryManager | None = None,
    ) -> None:
        self.address = address
        self.runner = runner
        self.libraries = libraries
        self._server: grpc.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self, blocking: bool = False) -> None:
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        mesh_pb2_grpc.add_AgentServicer_to_server(
            AgentServicer(self.runner, self.libraries), self._server
        )
        port = self.address.split(":")[-1]
        self._server.add_insecure_port(f"[::]:{port}")
        self._server.start()
        logger.info("Agent gRPC server listening on %s", self.address)
        if blocking:
            self._server.wait_for_termination()

    def stop(self) -> None:
        if self._server:
            self._server.stop(grace=2)
