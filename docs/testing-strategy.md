# Testing Strategy

ClusterMesh's value proposition lives in **correct behavior under failure and preemption**, not happy-path throughput. The test strategy reflects that.

## Philosophy

```
         ┌─────────────────────┐
         │  Chaos / Soak E2E   │  ← proves the vision
         ├─────────────────────┤
         │  Multi-agent Sim    │  ← proves scheduling + recovery
         ├─────────────────────┤
         │  Pure unit/property │  ← proves algorithms in isolation
         └─────────────────────┘
```

Five principles:

1. **Correctness under failure** — node dies, driver dies, network partitions
2. **Correctness under preemption** — user activity, battery drop, GPU needed locally
3. **Scheduling correctness** — heterogeneous nodes, pools, constraints
4. **No silent data loss** — checkpoints, replication, durable state
5. **Observable recovery** — "Lost Time: 3 seconds" must be measurable and bounded

## Test Infrastructure

### SimClock

Injectable clock for deterministic tests. Heartbeat intervals and failure detection run in milliseconds, not seconds.

```python
clock = SimClock()
clock.advance(seconds=6)  # instant jump → 3 missed heartbeats
```

### SimAgent

In-process fake agent:

```python
SimAgent(
    node_id="LAPTOP-55",
    cpu_cores=16,
    ram_gb=32,
    gpu=None,
    reliability=0.95,
    preemptible=True,
    battery_pct=80,
)
```

### SimCluster

Orchestrates N SimAgents with a driver-side scheduler:

```python
cluster = SimCluster(node_count=50)
cluster.submit(task_spec)
cluster.chaos.kill_node("LAPTOP-55", at=30.0)
cluster.run(until=120.0)
assert cluster.task_completed("task-1")
```

### ChaosController

Scriptable failure injection:

```python
chaos.kill_node("LAPTOP-55", at=t+30)
chaos.partition("office-a", "office-b", duration=60)
chaos.preempt("DESKTOP-11", cpu_spike=0.95)
chaos.battery_drain("LAPTOP-22", to_pct=40)
```

Chaos scenarios can be defined in YAML and replayed in CI.

## Priority Test Suites

### Tier 1 — Core Correctness (Phase 1) ✅

| # | Test | Assertion |
|---|------|-----------|
| 1 | Heartbeat FSM | 3 misses → SUSPECTED, 5 → DEAD |
| 2 | Constraint placement | Task needing 128GB never on 32GB node |
| 3 | Node scoring | Highest NodeScore wins; ties are deterministic |
| 4 | Pool routing | Night pool excludes daytime laptops |
| 5 | Battery gate | battery < 60% → node excluded |
| 6 | Preemption flow | WARNING → checkpoint → pause → migrate → resume |
| 7 | Work stealing | Dead node's tasks reassigned ≤ 5s |
| 8 | Checkpoint resume | Progress at 650M/1B → resume at 650M, not 0 |
| 9 | Replica failover | Primary dies → secondary continues |
| 10 | Driver HA | Leader dies → new leader resumes jobs |

### Tier 2 — Integration Realism (Phase 2–3)

| # | Test | Assertion |
|---|------|-----------|
| 11 | Dynamic cluster sizing | 100→500→1000 nodes, scheduler consistent |
| 12 | Library conflicts | No dependency hell across pools |
| 13 | Multi-site discovery | Cross-region nodes in one cluster |
| 14 | Speculative execution | Straggler duplicate; first finish wins |
| 15 | Auto rebalancing | Load variance decreases over time |
| 16 | DAG stage failure | Failed stage retries; downstream blocked |
| 17 | Auth + tenancy | Team A cannot access Team B resources |

### Tier 3 — Chaos / Soak (Phase 4)

| # | Test | Assertion |
|---|------|-----------|
| 18 | Random node kill | 20% nodes/hour during 24h job → completes |
| 19 | Network partition | No double-scheduling, no lost tasks |
| 20 | Clock skew | ±30s skew, heartbeat logic correct |
| 21 | Thundering herd | 500 laptops at 6PM, no meltdown |
| 22 | Preemption storm | 50 simultaneous preemptions → stabilizes |
| 23 | Driver + agent death | State recovered from durable store |

## SLAs (Hard Numbers)

Every test asserts against these targets:

| Metric | Target |
|--------|--------|
| Time to SUSPECTED | ≤ 6s |
| Time to DEAD | ≤ 10s |
| Task reassignment after DEAD | ≤ 5s |
| Max checkpoint progress loss | ≤ 1 interval |
| Preemption response | ≤ 2s from WARNING |
| Driver failover | ≤ 10s |
| Scheduler decision latency (1000 nodes) | p99 < 100ms |
| Recovery lost time (UI metric) | ≤ 5s |

## Property-Based Invariants

Using Hypothesis for scheduler invariants:

- **Conservation:** total assigned CPU ≤ total available CPU
- **Monotonicity:** killing a node never decreases scheduled task count
- **Idempotency:** same job + idempotency key → one execution
- **Checkpoint monotonicity:** resumed progress ≥ last checkpoint, always

## Golden Trace Replay

Record a simulated run (heartbeats, schedule decisions, failures, recoveries). Replay against new scheduler versions to catch regressions without re-running chaos.

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration / sim tests
pytest tests/integration/

# With coverage
pytest --cov=mesh --cov-report=term-missing

# Specific suite
pytest tests/test_heartbeat.py -v
```

## CI Pipeline (Planned)

```yaml
# .github/workflows/test.yml
- Unit tests (fast, every push)
- SimCluster integration (50 nodes, every push)
- Chaos soak (100 nodes, 1h simulated, nightly)
- Property tests (Hypothesis, every push)
```
