# Architecture

ClusterMesh (ComputeMesh) is a distributed compute operating system — not a Spark competitor. It sits between employee hardware and cloud providers, turning idle enterprise machines into a self-healing supercomputer.

## Design Principles

1. **Unreliable hardware is the default** — laptops sleep, users open apps, nodes leave the network. Every component must assume failure.
2. **Never lose progress** — checkpointing, replication, and durable state are first-class, not afterthoughts.
3. **Respect the user** — preemptible resources; employee laptops must never feel sluggish.
4. **Durable metadata** — job, node, and task state live in Postgres/Redis/Raft, never only in driver memory.
5. **Simulate before you ship** — the `SimCluster` harness runs 1000-node scenarios in CI on a laptop.

## System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                         UI Layer                            │
│  Dashboard · DAG Viewer · Process Explorer · Library Mgr   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Control Plane                          │
│  Metadata Service · Scheduler Service · Auth Service        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Driver Cluster (HA)                       │
│  Raft Leader Election · DAG Planner · Failure Recovery     │
│  Cluster State · Job States · Task Metadata                │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐           ┌────▼────┐          ┌────▼────┐
   │ Agent   │           │ Agent   │          │ Agent   │
   │ Laptop  │           │ Desktop │          │ GPU WS  │
   └─────────┘           └─────────┘          └─────────┘
```

## Components

### Agent

Installed on every machine via `curl install.sh` or MSI installer.

**Supported platforms:** Windows, Linux, macOS, VMware, EC2, Azure VM, bare metal.

| Sub-service | Responsibility |
|-------------|----------------|
| **Resource Monitor** | Reports CPU, RAM, disk, network, GPU, VRAM, battery, temperature, user activity (every 1s) |
| **Executor** | Runs Python, shell, SQL, containers, Spark-like tasks, ML workloads |
| **Library Manager** | Cluster-level package tracking (version, size, deps, conflicts) |
| **Health Manager** | Sends heartbeats to driver every 2s |

### Driver Node

Equivalent of a Spark Driver. Runs as a 3-node HA cluster with Raft leader election.

| Responsibility | Description |
|----------------|-------------|
| Cluster State | Live view of all nodes and resources |
| Node Health | Heartbeat tracking, SUSPECTED/DEAD transitions |
| Job States | Job lifecycle management |
| Task Metadata | Task assignments, progress, checkpoints |
| DAG Planner | Breaks jobs into stages and tasks |
| Scheduler | Constraint-aware placement with node scoring |
| Failure Recovery | Work stealing, replication failover, rebalancing |
| Data Locality | Prefer nodes close to data |
| Resource Prediction | Forecast available capacity (night pool expansion) |

### Control Plane Services

| Service | Role |
|---------|------|
| **Metadata Service** | Job definitions, DAG specs, library catalog |
| **Scheduler Service** | Placement decisions, pool routing, rebalancing |
| **Auth Service** | Tenancy, node registration, API keys |

### Distributed State Store

All durable state in Postgres, Redis, or a Raft cluster:

- Job state
- Node state
- Task state
- Checkpoints

If the driver dies, a new leader resumes from the store.

## Node Discovery

| Scope | Mechanism |
|-------|-----------|
| Local network | mDNS — laptop discovers laptop, desktop discovers VM |
| Enterprise / multi-site | gRPC over mesh VPN (Tailscale-like) |

Nodes across Bangalore, London, AWS, Azure, and on-prem form one logical cluster.

## Resource Pools

| Pool | Target hardware | Schedule window |
|------|-----------------|-----------------|
| **CPU Pool** | Office desktops | Business hours |
| **Memory Pool** | Large-RAM servers | Always |
| **GPU Pool** | AI workstations | Always (CUDA required) |
| **Night Pool** | Employee laptops | After office hours |

### Dynamic Cluster Formation

| Time | Active nodes |
|------|-------------|
| 9 AM | ~100 |
| 6 PM | ~500 |
| 11 PM | ~1000 |

Cluster auto-expands as laptops become idle.

## Scheduler

The scheduler is the primary differentiator. It understands multi-dimensional constraints:

| Dimension | Example constraint |
|-----------|-------------------|
| CPU | Need 32 cores |
| Memory | Need 128 GB |
| GPU | 2 GPUs, 24 GB VRAM, CUDA 12 |
| Network | 10 Gbps |
| Battery | Exclude if < 60% |
| Reliability | Prefer stable servers over laptops |
| Latency | Prefer same-office nodes for data locality |

### Node Scoring Formula

```
NodeScore = 0.35 × CPU Score
          + 0.25 × Memory Score
          + 0.15 × GPU Score
          + 0.15 × Reliability Score
          + 0.10 × Network Score
```

Scheduler picks the highest-scoring eligible node.

## Data Flows

### Task Submission

```
Developer → mesh.submit(task) → Driver → DAG Planner → Scheduler → Agent Executor
```

### Node Failure Recovery

```
Agent stops heartbeating → Driver marks SUSPECTED (3 misses) → DEAD (5 misses)
  → Work Stealing: orphaned tasks reassigned → Checkpoint resume on new node
```

### Preemption

```
User opens app → Agent CPU 20%→95% → PREEMPTION WARNING → Driver
  → Checkpoint → Pause → Migrate → Resume on different node
```

## Technology Choices (Planned)

| Layer | Technology |
|-------|-----------|
| Agent | Python + Rust (executor hot path) |
| Driver | Python / Go |
| State store | Postgres + Redis |
| HA | Raft (hashicorp/raft or etcd) |
| Discovery | mDNS + Tailscale/WireGuard mesh |
| Agent ↔ Driver | gRPC |
| UI | React + WebSocket live updates |
| SDK | Python (primary), TypeScript (future) |

## Package Layout (Current)

```
mesh/
├── models/       Node, Task, Job, ResourceRequirements, ResourcePool
├── health/       HeartbeatTracker, NodeHealthRegistry
├── scheduler/    NodeScorer, PlacementEngine, PoolRouter
├── recovery/     WorkStealer, CheckpointManager (Phase 2)
└── sim/          SimClock, SimAgent, SimCluster, ChaosController
```
