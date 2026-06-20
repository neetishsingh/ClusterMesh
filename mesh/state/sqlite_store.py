from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
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


class SQLiteStateStore:
    """File-backed durable state — no external Postgres/Redis required."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    job_id TEXT,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    task_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leadership (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    driver_id TEXT NOT NULL,
                    term INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                );
            """)
            self._conn.commit()

    def save_job(self, job: Job) -> None:
        data = json.dumps(job_to_dict(job))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (job_id, data) VALUES (?, ?)",
                (job.job_id, data),
            )
            self._conn.commit()

    def load_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return job_from_dict(json.loads(row[0])) if row else None

    def list_jobs(self) -> list[Job]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM jobs").fetchall()
        return [job_from_dict(json.loads(r[0])) for r in rows]

    def save_task(self, task: TaskSpec) -> None:
        data = json.dumps(task_to_dict(task))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (task_id, job_id, data) VALUES (?, ?, ?)",
                (task.task_id, task.job_id, data),
            )
            self._conn.commit()

    def load_task(self, task_id: str) -> Optional[TaskSpec]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return task_from_dict(json.loads(row[0])) if row else None

    def list_tasks(self) -> list[TaskSpec]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM tasks").fetchall()
        return [task_from_dict(json.loads(r[0])) for r in rows]

    def save_checkpoint(self, cp: Checkpoint) -> None:
        data = json.dumps(checkpoint_to_dict(cp))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO checkpoints (task_id, data) VALUES (?, ?)",
                (cp.task_id, data),
            )
            self._conn.commit()

    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM checkpoints WHERE task_id = ?", (task_id,)
            ).fetchone()
        return checkpoint_from_dict(json.loads(row[0])) if row else None

    def save_node(self, node: Node) -> None:
        data = json.dumps(node_to_dict(node))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO nodes (node_id, data) VALUES (?, ?)",
                (node.node_id, data),
            )
            self._conn.commit()

    def load_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
        return node_from_dict(json.loads(row[0])) if row else None

    def list_nodes(self) -> list[Node]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM nodes").fetchall()
        return [node_from_dict(json.loads(r[0])) for r in rows]

    def try_acquire_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        now = time.time()
        expires = now + ttl_seconds
        with self._lock:
            row = self._conn.execute(
                "SELECT driver_id, term, expires_at FROM leadership WHERE id = 1"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO leadership (id, driver_id, term, expires_at) VALUES (1, ?, ?, ?)",
                    (driver_id, term, expires),
                )
                self._conn.commit()
                return True
            _, current_term, expires_at = row
            if expires_at < now or term > current_term:
                self._conn.execute(
                    "UPDATE leadership SET driver_id = ?, term = ?, expires_at = ? WHERE id = 1",
                    (driver_id, term, expires),
                )
                self._conn.commit()
                return True
            return row[0] == driver_id and term >= current_term

    def renew_leadership(self, driver_id: str, term: int, ttl_seconds: float) -> bool:
        expires = time.time() + ttl_seconds
        with self._lock:
            row = self._conn.execute(
                "SELECT driver_id, term FROM leadership WHERE id = 1"
            ).fetchone()
            if row is None or row[0] != driver_id or row[1] != term:
                return False
            self._conn.execute(
                "UPDATE leadership SET expires_at = ? WHERE id = 1",
                (expires,),
            )
            self._conn.commit()
            return True

    def get_leader(self) -> Optional[tuple[str, int]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT driver_id, term, expires_at FROM leadership WHERE id = 1"
            ).fetchone()
        if row and row[2] >= time.time():
            return row[0], row[1]
        return None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
