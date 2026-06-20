# Fault Tolerance

Fault tolerance is where ClusterMesh can be **better than Spark**. Enterprise hardware is unreliable by nature — laptops sleep, users preempt resources, networks partition. This document defines all 10 recovery mechanisms and their SLAs.

## The Core Problem

```
Task-23 running on LAPTOP-55
         │
         ▼
  Laptop goes offline (sleep, shutdown, network loss)
         │
         ▼
  What happens to Task-23?
```

ClusterMesh answer: **progress is preserved, task resumes elsewhere, lost time is bounded.**

---

## Solution 1: Heartbeats

Every agent sends a heartbeat to the driver every **2 seconds**.

| Missed heartbeats | Node state |
|-------------------|------------|
| 0–2 | HEALTHY |
| 3 | SUSPECTED |
| 5+ | DEAD |

### SLA

| Metric | Target |
|--------|--------|
| Time to SUSPECTED | ≤ 6s (3 × 2s) |
| Time to DEAD | ≤ 10s (5 × 2s) |

### Implementation

`mesh.health.heartbeat.HeartbeatTracker` — per-node FSM with injectable clock for deterministic testing.

---

## Solution 2: Task Checkpointing

Tasks periodically save progress to durable storage:

- Progress counters
- State variables
- Partition offsets
- Intermediate results

### Example

```
Task: process 1 billion records
Progress at checkpoint: 650,000,000 complete
Node dies.
Restart from: 650,000,000 (not 0)
```

### SLA

| Metric | Target |
|--------|--------|
| Max progress loss | ≤ 1 checkpoint interval |
| Checkpoint write latency | p99 < 500ms |

### Implementation (Phase 2)

`mesh.recovery.checkpoint.CheckpointManager`

---

## Solution 3: Task Replication

Critical jobs run on multiple nodes simultaneously.

```python
@task(replicas=2)
def critical_etl():
    ...
```

```
Task runs on Node5 AND Node11
Node5 dies → Node11 continues → zero interruption
```

### Rules

- Only one replica's result is committed (first-to-finish or primary/secondary)
- Replicas must land on different failure domains (different hosts/racks)

---

## Solution 4: Work Stealing

When a node dies, its tasks are immediately reassigned:

```
Node dies with Task1, Task2, Task3
  → Node8 steals Task1
  → Node12 steals Task2
  → Node20 steals Task3
```

### SLA

| Metric | Target |
|--------|--------|
| Time to reassign after DEAD | ≤ 5s |
| No task loss | 100% of orphaned tasks reassigned |

### Implementation (Phase 2)

`mesh.recovery.work_stealing.WorkStealer`

---

## Solution 5: Speculative Execution

Like Spark's straggler mitigation:

```
Task on Node5 is slow (straggler detected)
  → Duplicate launched on Node15
  → Whichever finishes first wins
  → Loser is cancelled
```

### Trigger

Task runtime exceeds `median × speculation_multiplier` (default 1.5×).

---

## Solution 6: Distributed State Store

**Never keep metadata only in driver memory.**

| State | Store |
|-------|-------|
| Job state | Postgres |
| Node state | Redis (hot) + Postgres (durable) |
| Task state | Postgres |
| Checkpoints | Object storage / Postgres |

If the driver dies, a new leader reads state from the store and resumes.

---

## Solution 7: Driver HA

Single driver is a single point of failure.

```
Driver1 (leader) ── Raft ── Driver2 (follower) ── Driver3 (follower)

Driver1 dies → Driver2 elected leader → resumes in-flight jobs
```

### SLA

| Metric | Target |
|--------|--------|
| Failover time | ≤ 10s |
| In-flight job loss | 0 |

---

## Solution 8: Automatic Rebalancing

Continuous load balancing across nodes:

```
Node1: 64 cores, 2 free  ← overloaded
Node2: 64 cores, 60 free   ← underutilized
  → Scheduler migrates tasks from Node1 to Node2
```

Triggered when utilization variance exceeds threshold (default: 30%).

---

## Solution 9: Preemptible Resources

Employee starts using their laptop:

```
CPU: 20% → 95%
Agent sends: PREEMPTION WARNING
Scheduler: Checkpoint → Pause → Move → Resume
User impact: none (their machine is freed immediately)
```

### Preemption Pipeline

```
1. Agent detects user activity / CPU spike
2. PREEMPTION WARNING sent to driver
3. Driver initiates checkpoint on affected tasks
4. Tasks paused on preempted node
5. Scheduler finds new node
6. Tasks resumed on new node
```

### SLA

| Metric | Target |
|--------|--------|
| Time from WARNING to pause | ≤ 2s |
| User CPU returned to baseline | ≤ 3s |

---

## Solution 10: Distributed Memory Fabric

Expose aggregate free memory across nodes as a logical pool:

```
Node1: 32 GB free
Node2: 64 GB free
Node3: 16 GB free
  → Logical pool: 112 GB
```

Driver allocates across nodes for memory-heavy tasks that exceed single-node capacity.

> **Status:** Phase 5 — very difficult, huge differentiator.

---

## Failure Scenario Matrix

| Scenario | Mechanisms activated | Expected outcome |
|----------|---------------------|------------------|
| Laptop sleeps mid-task | Heartbeat → Work Stealing → Checkpoint | Resume within 10s, ≤1 checkpoint loss |
| User opens Chrome | Preemption → Checkpoint → Migrate | User unaffected, task continues elsewhere |
| Driver leader dies | Driver HA → State Store | Failover ≤10s, zero job loss |
| Network partition | Heartbeat → SUSPECTED (not immediate DEAD) | No double-scheduling |
| Straggler task | Speculative Execution | Faster replica wins |
| Critical ETL job | Replication | Zero interruption on node death |
| 50 nodes die at once | Work Stealing (batch) | All tasks reassigned within 5s |
| 24h batch job | Checkpoint + Replication + Work Stealing | Job completes despite continuous churn |

## Testing Each Mechanism

See [testing-strategy.md](./testing-strategy.md) for the full test matrix mapped to each solution.
