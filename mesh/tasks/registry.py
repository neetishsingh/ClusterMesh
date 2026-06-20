"""Shared task registry for driver and agent dispatch by name."""

from __future__ import annotations

from typing import Any, Callable

_registry: dict[str, Callable] = {}


def register(name: str, fn: Callable) -> Callable:
    _registry[name] = fn
    return fn


def get(name: str) -> Callable:
    if name not in _registry:
        raise KeyError(f"Task not registered: {name!r}")
    return _registry[name]


def list_tasks() -> list[str]:
    return sorted(_registry.keys())


def clear() -> None:
    _registry.clear()


def register_mesh_task(mesh_task: Any) -> None:
    _registry[mesh_task.name] = mesh_task.fn
