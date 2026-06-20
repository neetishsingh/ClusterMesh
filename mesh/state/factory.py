"""Create durable state stores from connection URLs."""

from __future__ import annotations

import os
from typing import Union

from mesh.state.sqlite_store import SQLiteStateStore

StateStoreImpl = Union[SQLiteStateStore, object]


def create_state_store(url: str | None = None) -> StateStoreImpl:
    """
    Factory for state backends.

    Supported URLs:
      sqlite:///path/to.db   (default)
      postgres://user:pass@host:5432/dbname
      redis://host:6379/0
    """
    dsn = url or os.environ.get("MESH_STATE_URL", "sqlite:///clustermesh.db")

    if dsn.startswith("sqlite://"):
        if dsn.startswith("sqlite:////"):
            path = "/" + dsn[len("sqlite:////") :]
        elif dsn.startswith("sqlite:///"):
            path = dsn[len("sqlite:///") :]
        else:
            path = dsn[len("sqlite://") :]
        if path in ("", ":memory:") or path.endswith(":memory:"):
            path = ":memory:"
        return SQLiteStateStore(path)

    if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
        from mesh.state.postgres_store import PostgresStateStore

        return PostgresStateStore(dsn)

    if dsn.startswith("redis://") or dsn.startswith("rediss://"):
        from mesh.state.redis_store import RedisStateStore

        return RedisStateStore(dsn)

    raise ValueError(f"Unsupported state store URL: {dsn}")
