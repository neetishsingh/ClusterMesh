"""Tests for worker runtime state and API."""

from fastapi.testclient import TestClient

from mesh.worker.server import create_worker_app
from mesh.worker.state import WorkerState


class TestWorkerState:
    def test_to_dict_includes_dashboard_url(self):
        state = WorkerState(driver_address="192.168.1.5:50050", node_id="n1")
        state.mark_registered("n1")
        d = state.to_dict()
        assert d["dashboard_url"] == "http://192.168.1.5:8080"
        assert d["registered"] is True
        assert d["node_state"] == "HEALTHY"

    def test_mark_failed(self):
        state = WorkerState()
        state.mark_failed("connection refused")
        assert state.registered is False
        assert state.last_error == "connection refused"


class TestWorkerAPI:
    def test_status_endpoint(self):
        state = WorkerState(node_id="test-node", driver_address="10.0.0.1:50050")
        client = TestClient(create_worker_app(state))
        r = client.get("/api/v1/worker/status")
        assert r.status_code == 200
        assert r.json()["node_id"] == "test-node"

    def test_index_html(self):
        state = WorkerState()
        client = TestClient(create_worker_app(state))
        r = client.get("/")
        assert r.status_code == 200
        assert "ClusterMesh Worker" in r.text
