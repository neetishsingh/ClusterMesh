"""Redis-backed durable state store."""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

from mesh.models.job import Job
from mesh.models.node import Node
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import Checkpoint
from mesh.state.serialize import (
    checkpoint_from_dict,
    checkpoint_to_dict,
    job_from_dict,
    job_to_dict,
    node_from_dict,
    node_to_dict,
    task_from_dict,
    task_to_dict,
)

_PREFIX = "mesh:"


class RedisStateStore:
    """Fast in-memory durable store using Redis."""

    def __init__(self, url: str) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "Redis backend requires redis — pip install clustermesh[redis]"
            ) from exc

        self._r = redis.from_url(url, decode_responses=True)
        self._lock = threading.Lock()

    def _keys(self, kind: str) -> list[str]:
        return list(self._r.scan_iter(match=f"{_PREFIX}{kind}:*"))

    def save_job(self, job: Job) -> None:
        self._r.set(f"{_PREFIX}job:{job.job_id}", json.dumps(job_to_dict(job)))

    def load_job(self, job_id: str) -> Optional[Job]:
        raw = self._r.get(f"{_PREFIX}job:{job_id}")
        return job_from_dict(json.loads(raw)) if raw else None

    def list_jobs(self) -> list[Job]:
        return [
            job_from_dict(json.loads(self._r.get(k)))
            for k in self._keys("job")
            if self._r.get(k)
        ]

    def save_task(self, task: TaskSpec) -> None:
        self._r.set(f"{_PREFIX}task:{task.task_id}", json.dumps(task_to_dict(task)))

    def load_task(self, task_id: str) -> Optional[TaskSpec]:
        raw = self._r.get(f"{_PREFIX}task:{task_id}")
        return task_from_dict(json.loads(raw)) if raw else None

    def list_tasks(self) -> list[TaskSpec]:
        return [
            task_from_dict(json.loads(self._r.get(k)))
            for k in self._keys("task")
            if self._r.get(k)
        ]

    def save_checkpoint(self, cp: Checkpoint) -> None:
        self._r.set(f"{_PREFIX}cp:{cp.task_id}", json.dumps(checkpoint_to_dict(cp)))

    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        raw = self._r.get(f"{_PREFIX}cp:{task_id}")
        return checkpoint_from_dict(json.loads(raw)) if raw else None

    def save_node(self, node: Node) -> None:
        self._r.set(f"{_PREFIX}node:{node.node_id}", json.dumps(node_to_dict(node)))

    def load_node(self, node_id: str) -> Optional[Node]:
        raw = self._r.get(f"{_PREFIX}node:{node_id}")
        return node_from_dict(json.loads(raw)) if raw else None

    def list_nodes(self) -> list[Node]:
        return [
            node_from_dict(json.loads(self._r.get(k)))
            for k in self._keys("node")
            if self._r.get(k)
        ]

    def try_acquire_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        key = f"{_PREFIX}leadership"
        now = time.time()
        expires = now + ttl_seconds
        with self._lock:
            raw = self._r.get(key)
            if raw is None:
                payload = json.dumps({"driver_id": driver_id, "term": term, "expires_at": expires})
                return bool(self._r.set(key, payload, nx=True))
            data = json.loads(raw)
            if data["expires_at"] < now or term > data["term"]:
                payload = json.dumps({"driver_id": driver_id, "term": term, "expires_at": expires})
                self._r.set(key, payload)
                return True
            return data["driver_id"] == driver_id and term >= data["term"]

    def renew_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        key = f"{_PREFIX}leadership"
        expires = time.time() + ttl_seconds
        with self._lock:
            raw = self._r.get(key)
            if not raw:
                return False
            data = json.loads(raw)
            if data["driver_id"] != driver_id or data["term"] != term:
                return False
            data["expires_at"] = expires
            self._r.set(key, json.dumps(data))
            return True

    def get_leader(self) -> Optional[tuple[str, int]]:
        raw = self._r.get(f"{_PREFIX}leadership")
        if not raw:
            return None
        data = json.loads(raw)
        if data["expires_at"] >= time.time():
            return data["driver_id"], data["term"]
        return None

    def close(self) -> None:
        self._r.close()
