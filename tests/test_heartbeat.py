"""Tests for heartbeat FSM."""

import pytest

from mesh.health.heartbeat import HeartbeatTracker, NodeHealthRegistry
from mesh.models.enums import NodeState
from mesh.sim.clock import SimClock


@pytest.fixture
def clock():
    return SimClock()


@pytest.fixture
def tracker(clock):
    return HeartbeatTracker(
        interval_seconds=2.0,
        suspected_threshold=3,
        dead_threshold=5,
        clock=clock.now,
    )


class TestHeartbeatTracker:
    def test_new_node_is_healthy(self, tracker):
        tracker.register("NODE-1")
        assert tracker.get_state("NODE-1") == NodeState.HEALTHY

    def test_heartbeat_resets_to_healthy(self, tracker, clock):
        tracker.register("NODE-1")
        clock.advance(10)
        tracker.record_heartbeat("NODE-1")
        assert tracker.evaluate("NODE-1") == NodeState.HEALTHY

    def test_suspected_after_3_misses(self, tracker, clock):
        tracker.register("NODE-1")
        clock.advance(6)  # 3 × 2s
        assert tracker.evaluate("NODE-1") == NodeState.SUSPECTED

    def test_dead_after_5_misses(self, tracker, clock):
        tracker.register("NODE-1")
        clock.advance(10)  # 5 × 2s
        assert tracker.evaluate("NODE-1") == NodeState.DEAD

    def test_suspected_between_3_and_4_misses(self, tracker, clock):
        tracker.register("NODE-1")
        clock.advance(7)  # 3.5 intervals
        assert tracker.evaluate("NODE-1") == NodeState.SUSPECTED

    def test_time_to_suspected_sla(self, tracker):
        assert tracker.time_to_suspected() == 6.0

    def test_time_to_dead_sla(self, tracker):
        assert tracker.time_to_dead() == 10.0

    def test_unregistered_node_is_dead(self, tracker):
        assert tracker.evaluate("UNKNOWN") == NodeState.DEAD

    def test_mark_preempted(self, tracker):
        tracker.register("NODE-1")
        tracker.mark_preempted("NODE-1")
        assert tracker.get_state("NODE-1") == NodeState.PREEMPTED


class TestNodeHealthRegistry:
    def test_state_change_callback(self, tracker, clock):
        registry = NodeHealthRegistry(tracker=tracker)
        changes = []
        registry.on_state_change(lambda nid, old, new: changes.append((nid, old, new)))
        registry.register("NODE-1")

        clock.advance(10)
        registry.evaluate_all()

        assert len(changes) >= 1
        assert changes[-1][0] == "NODE-1"
        assert changes[-1][2] == NodeState.DEAD

    def test_get_dead_nodes(self, tracker, clock):
        registry = NodeHealthRegistry(tracker=tracker)
        registry.register("NODE-1")
        registry.register("NODE-2")

        clock.advance(10)
        registry.evaluate_all()

        dead = registry.get_dead_nodes()
        assert "NODE-1" in dead
        assert "NODE-2" in dead
