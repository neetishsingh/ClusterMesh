"""Local worker dashboard — shows status of this machine in the mesh."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mesh.worker.state import WorkerState

STATIC_DIR = Path(__file__).parent / "static"


def create_worker_app(state: WorkerState) -> FastAPI:
    app = FastAPI(title="ClusterMesh Worker", version="0.9.0")

    @app.get("/api/v1/worker/status")
    def worker_status():
        return state.to_dict()

    @app.get("/health")
    def health():
        return {"ok": True, "registered": state.registered}

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

    return app


def run_worker_ui(state: WorkerState, host: str = "127.0.0.1", port: int | None = None) -> None:
    import uvicorn

    port = port or state.ui_port
    app = create_worker_app(state)
    uvicorn.run(app, host=host, port=port, log_level="warning")
