"""PostgreSQL-backed durable state store."""

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    job_id TEXT,
    data JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    task_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS leadership (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    driver_id TEXT NOT NULL,
    term INTEGER NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
"""


class PostgresStateStore:
    """Production-grade state store using PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise ImportError(
                "Postgres backend requires psycopg — pip install clustermesh[postgres]"
            ) from exc

        self.dsn = dsn
        self._lock = threading.Lock()
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(_SCHEMA)

    def save_job(self, job: Job) -> None:
        data = json.dumps(job_to_dict(job))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO jobs (job_id, data) VALUES (%s, %s::jsonb) "
                    "ON CONFLICT (job_id) DO UPDATE SET data = EXCLUDED.data",
                    (job.job_id, data),
                )

    def load_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM jobs WHERE job_id = %s", (job_id,))
                row = cur.fetchone()
        return job_from_dict(row[0]) if row else None

    def list_jobs(self) -> list[Job]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM jobs")
                rows = cur.fetchall()
        return [job_from_dict(r[0]) for r in rows]

    def save_task(self, task: TaskSpec) -> None:
        data = json.dumps(task_to_dict(task))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks (task_id, job_id, data) VALUES (%s, %s, %s::jsonb) "
                    "ON CONFLICT (task_id) DO UPDATE SET data = EXCLUDED.data",
                    (task.task_id, task.job_id, data),
                )

    def load_task(self, task_id: str) -> Optional[TaskSpec]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM tasks WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
        return task_from_dict(row[0]) if row else None

    def list_tasks(self) -> list[TaskSpec]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM tasks")
                rows = cur.fetchall()
        return [task_from_dict(r[0]) for r in rows]

    def save_checkpoint(self, cp: Checkpoint) -> None:
        data = json.dumps(checkpoint_to_dict(cp))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO checkpoints (task_id, data) VALUES (%s, %s::jsonb) "
                    "ON CONFLICT (task_id) DO UPDATE SET data = EXCLUDED.data",
                    (cp.task_id, data),
                )

    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM checkpoints WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
        return checkpoint_from_dict(row[0]) if row else None

    def save_node(self, node: Node) -> None:
        data = json.dumps(node_to_dict(node))
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO nodes (node_id, data) VALUES (%s, %s::jsonb) "
                    "ON CONFLICT (node_id) DO UPDATE SET data = EXCLUDED.data",
                    (node.node_id, data),
                )

    def load_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM nodes WHERE node_id = %s", (node_id,))
                row = cur.fetchone()
        return node_from_dict(row[0]) if row else None

    def list_nodes(self) -> list[Node]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT data FROM nodes")
                rows = cur.fetchall()
        return [node_from_dict(r[0]) for r in rows]

    def try_acquire_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        now = time.time()
        expires = now + ttl_seconds
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT driver_id, term, expires_at FROM leadership WHERE id = 1"
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "INSERT INTO leadership (id, driver_id, term, expires_at) "
                        "VALUES (1, %s, %s, %s)",
                        (driver_id, term, expires),
                    )
                    return True
                _, current_term, expires_at = row
                if expires_at < now or term > current_term:
                    cur.execute(
                        "UPDATE leadership SET driver_id = %s, term = %s, expires_at = %s "
                        "WHERE id = 1",
                        (driver_id, term, expires),
                    )
                    return True
                return row[0] == driver_id and term >= current_term

    def renew_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        expires = time.time() + ttl_seconds
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT driver_id, term FROM leadership WHERE id = 1")
                row = cur.fetchone()
                if row is None or row[0] != driver_id or row[1] != term:
                    return False
                cur.execute(
                    "UPDATE leadership SET expires_at = %s WHERE id = 1",
                    (expires,),
                )
                return True

    def get_leader(self) -> Optional[tuple[str, int]]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT driver_id, term, expires_at FROM leadership WHERE id = 1"
                )
                row = cur.fetchone()
        if row and row[2] >= time.time():
            return row[0], row[1]
        return None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
