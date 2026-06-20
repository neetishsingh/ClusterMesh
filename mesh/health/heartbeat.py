from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from mesh.models.enums import NodeState


ClockFn = Callable[[], float]


@dataclass
class HeartbeatTracker:
    """
    Per-node heartbeat FSM.

    Default: heartbeat every 2s, SUSPECTED after 3 misses, DEAD after 5.
    """

    interval_seconds: float = 2.0
    suspected_threshold: int = 3
    dead_threshold: int = 5
    clock: ClockFn = field(default_factory=lambda: __import__("time").time)

    _last_heartbeat: dict[str, float] = field(default_factory=dict, repr=False)
    _states: dict[str, NodeState] = field(default_factory=dict, repr=False)
    _explicit_dead: set[str] = field(default_factory=set, repr=False)

    def register(self, node_id: str) -> None:
        now = self.clock()
        self._last_heartbeat[node_id] = now
        self._states[node_id] = NodeState.HEALTHY
        self._explicit_dead.discard(node_id)

    def record_heartbeat(self, node_id: str) -> NodeState:
        now = self.clock()
        self._last_heartbeat[node_id] = now
        self._states[node_id] = NodeState.HEALTHY
        self._explicit_dead.discard(node_id)
        return NodeState.HEALTHY

    def missed_count(self, node_id: str) -> int:
        if node_id not in self._last_heartbeat:
            return self.dead_threshold
        elapsed = self.clock() - self._last_heartbeat[node_id]
        return int(elapsed // self.interval_seconds)

    def evaluate(self, node_id: str) -> NodeState:
        if node_id in self._explicit_dead:
            self._states[node_id] = NodeState.DEAD
            return NodeState.DEAD

        if node_id not in self._last_heartbeat:
            return NodeState.DEAD

        missed = self.missed_count(node_id)
        if missed >= self.dead_threshold:
            state = NodeState.DEAD
        elif missed >= self.suspected_threshold:
            state = NodeState.SUSPECTED
        else:
            state = NodeState.HEALTHY

        self._states[node_id] = state
        return state

    def get_state(self, node_id: str) -> NodeState:
        return self._states.get(node_id, NodeState.OFFLINE)

    def mark_dead(self, node_id: str) -> None:
        self._states[node_id] = NodeState.DEAD
        self._explicit_dead.add(node_id)

    def mark_preempted(self, node_id: str) -> None:
        self._states[node_id] = NodeState.PREEMPTED

    def time_to_suspected(self) -> float:
        return self.interval_seconds * self.suspected_threshold

    def time_to_dead(self) -> float:
        return self.interval_seconds * self.dead_threshold


@dataclass
class NodeHealthRegistry:
    """Tracks health for all nodes in the cluster."""

    tracker: HeartbeatTracker = field(default_factory=HeartbeatTracker)
    _callbacks: list[Callable[[str, NodeState, NodeState], None]] = field(
        default_factory=list, repr=False
    )

    def on_state_change(
        self, callback: Callable[[str, NodeState, NodeState], None]
    ) -> None:
        self._callbacks.append(callback)

    def register(self, node_id: str) -> None:
        self.tracker.register(node_id)

    def record_heartbeat(self, node_id: str) -> NodeState:
        old = self.tracker.get_state(node_id)
        self.tracker.record_heartbeat(node_id)
        new = NodeState.HEALTHY
        if old != new:
            self._notify(node_id, old, new)
        return new

    def evaluate_all(self) -> dict[str, NodeState]:
        results = {}
        for node_id in list(self.tracker._last_heartbeat.keys()):
            old = self.tracker.get_state(node_id)
            new = self.tracker.evaluate(node_id)
            results[node_id] = new
            if old != new:
                self._notify(node_id, old, new)
        return results

    def get_state(self, node_id: str) -> NodeState:
        return self.tracker.evaluate(node_id)

    def get_dead_nodes(self) -> list[str]:
        return [
            nid
            for nid in self.tracker._last_heartbeat
            if self.tracker.evaluate(nid) == NodeState.DEAD
        ]

    def force_state(self, node_id: str, new_state: NodeState) -> None:
        old = self.tracker.get_state(node_id)
        if new_state == NodeState.DEAD:
            self.tracker.mark_dead(node_id)
        else:
            self.tracker._states[node_id] = new_state
            self.tracker._explicit_dead.discard(node_id)
        if old != new_state:
            self._notify(node_id, old, new_state)

    def _notify(self, node_id: str, old: NodeState, new: NodeState) -> None:
        for cb in self._callbacks:
            cb(node_id, old, new)
