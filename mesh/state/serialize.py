"""Serialize cluster objects for durable storage."""

from __future__ import annotations

from dataclasses import asdict, fields
from enum import Enum
from typing import Any

from mesh.models.enums import NodeState, ResourcePool, TaskState
from mesh.models.job import Job, JobState
from mesh.models.node import Node, NodeResources
from mesh.models.task import ResourceRequirements, TaskSpec
from mesh.recovery.checkpoint import Checkpoint


def _enum_to_str(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, dict):
        return {k: _enum_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_enum_to_str(v) for v in obj]
    return obj


def job_to_dict(job: Job) -> dict:
    d = asdict(job)
    d["state"] = job.state.name
    return d


def job_from_dict(d: dict) -> Job:
    return Job(
        job_id=d["job_id"],
        name=d.get("name", ""),
        state=JobState[d["state"]],
        task_ids=list(d.get("task_ids", [])),
        result=d.get("result"),
        error=d.get("error"),
        idempotency_key=d.get("idempotency_key"),
        completed_task_id=d.get("completed_task_id"),
    )


def task_to_dict(task: TaskSpec) -> dict:
    d = {
        "task_id": task.task_id,
        "name": task.name,
        "job_id": task.job_id,
        "replica_index": task.replica_index,
        "state": task.state.name,
        "assigned_node": task.assigned_node,
        "progress": task.progress,
        "total_work": task.total_work,
        "state_data": task.state_data,
        "replicas": task.replicas,
        "checkpoint": task.checkpoint,
        "checkpoint_interval": task.checkpoint_interval,
        "preemption_ok": task.preemption_ok,
        "pool": task.pool.name if task.pool else None,
        "requirements": asdict(task.requirements),
    }
    return d


def task_from_dict(d: dict) -> TaskSpec:
    pool = ResourcePool[d["pool"]] if d.get("pool") else None
    req = d.get("requirements", {})
    return TaskSpec(
        name=d["name"],
        requirements=ResourceRequirements(**req),
        pool=pool,
        replicas=d.get("replicas", 1),
        checkpoint=d.get("checkpoint", False),
        checkpoint_interval=d.get("checkpoint_interval", 30.0),
        preemption_ok=d.get("preemption_ok", True),
        task_id=d["task_id"],
        job_id=d.get("job_id"),
        replica_index=d.get("replica_index", 0),
        state=TaskState[d["state"]],
        assigned_node=d.get("assigned_node"),
        progress=d.get("progress", 0.0),
        total_work=d.get("total_work", 1.0),
        state_data=dict(d.get("state_data", {})),
    )


def node_to_dict(node: Node) -> dict:
    r = node.resources
    return {
        "node_id": node.node_id,
        "hostname": node.hostname,
        "state": node.state.name,
        "reliability_score": node.reliability_score,
        "latency_score": node.latency_score,
        "pool": node.pool.name,
        "preemptible": node.preemptible,
        "location": node.location,
        "tags": node.tags,
        "resources": asdict(r),
    }


def node_from_dict(d: dict) -> Node:
    r = d["resources"]
    return Node(
        node_id=d["node_id"],
        hostname=d["hostname"],
        resources=NodeResources(**r),
        state=NodeState[d["state"]],
        reliability_score=d.get("reliability_score", 0.8),
        latency_score=d.get("latency_score", 0.9),
        pool=ResourcePool[d.get("pool", "CPU")],
        preemptible=d.get("preemptible", False),
        location=d.get("location", "default"),
        tags=dict(d.get("tags", {})),
    )


def checkpoint_to_dict(cp: Checkpoint) -> dict:
    return asdict(cp)


def checkpoint_from_dict(d: dict) -> Checkpoint:
    return Checkpoint(**d)
