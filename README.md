# ClusterMesh (ComputeMesh)

**An operating system for enterprise compute** — turn every laptop, desktop, VM, and GPU workstation into a single elastic, fault-tolerant compute cloud.

> Full vision: [Sparkpool](./Sparkpool) · Architecture: [docs/architecture.md](./docs/architecture.md) · Roadmap: [docs/roadmap.md](./docs/roadmap.md)

## The Problem

Organizations sit on thousands of idle cores:

| Resource | Typical utilization |
|----------|---------------------|
| CPU | 10–20% |
| RAM | 30–50% |
| GPU | 5–10% |

Databricks, Kubernetes, Spark, and Ray all require **dedicated** compute. Nobody fully solves:

> *"Use all idle enterprise hardware automatically and safely."*

ClusterMesh does.

## What We're Building

```
                    Control Plane
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
 Metadata Service    Scheduler Service    Auth Service
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                     Driver Cluster (Raft HA)
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
   Agent-1             Agent-2              Agent-3
  Laptop               Desktop                 VM
```

**Killer features:** idle compute harvesting · GPU sharing · live discovery · fault-tolerant scheduling · work stealing · preemption handling · checkpoint recovery · multi-office clustering

## Join a worker (any Python machine)

```bash
pip install clustermesh
clustermesh join DRIVER_IP:50050 --open    # local worker UI on :50052
```

See [docs/join-mesh.md](./docs/join-mesh.md) for full details.

## Quick Start (development)

```bash
# Install in development mode
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run a simulated 50-node cluster demo
python -m mesh.sim.demo

# Phase 5: platform with React dashboard (build UI first)
cd frontend && npm install && npm run build && cd ..
mesh-platform --port 8080 --db clustermesh.db   # driver + API + UI
# Phase 6 options
mesh-platform --port 8080 --mdns --site bangalore          # advertise via mDNS
mesh-platform --store-url postgres://user:pass@localhost/clustermesh
mesh-platform --api-key your-secret-key                    # require auth on API
mesh-agent --discover                                      # auto-find driver on LAN

# Phase 7: multi-site mesh VPN
mesh-platform --mesh-config config/sites.example.yaml --site bangalore
mesh-relay --listen 0.0.0.0:6000 --target 127.0.0.1:50050   # standalone relay
mesh-soak --hours 24 --nodes 50                              # accelerated 24h chaos test
mesh-bench --nodes 1000                                       # placement SLA benchmark
./scripts/dogfood.sh                                           # local dogfood run
```

## Project Structure

```
ClusterMesh/
├── docs/                  # Architecture, testing strategy, roadmap
├── mesh/                  # Core Python package
│   ├── models/            # Node, Task, Job, Resource types
│   ├── health/            # Heartbeat FSM, node health tracking
│   ├── scheduler/         # Scoring, placement, pool routing
│   ├── execution/         # TaskExecutor, TaskContext
│   ├── recovery/          # Checkpointing, work stealing, replication
│   ├── driver/            # JobManager, DriverCluster, gRPC server
│   ├── agent/             # Daemon, monitor, preemption, library
│   ├── proto/             # gRPC protobuf definitions
│   ├── tasks/             # Task registry + built-ins
│   ├── sdk/               # @task decorator, submit() API
│   └── sim/               # SimAgent, SimCluster, chaos injection
├── tests/                 # Unit + integration tests
├── frontend/              # React dashboard (Vite + Tailwind)
└── Sparkpool              # Original product vision document
```

## Current Status (Phase 8) ✅

| Component | Status |
|-----------|--------|
| Phases 0–7 (full platform + mesh VPN) | ✅ Done |
| Distributed memory fabric | ✅ Done |
| 1000-node placement SLA (`mesh-bench`) | ✅ Done |
| Memory dashboard + dogfood script | ✅ Done |

## Developer SDK

```python
from mesh import task, submit, TaskContext

@task(cpu=4, ram="8GB", checkpoint=True, total_work=1_000_000)
def process_records(ctx: TaskContext):
    for i in range(int(ctx.progress), 1_000_000):
        ctx.set_progress(i + 1, records=i + 1)
    return "done"

# Sync submit — blocks until complete
result = submit(process_records)

# Async submit — returns JobHandle
job = submit(process_records, async_=True)
result = job.wait(timeout=3600)
```

See [docs/api-spec.md](./docs/api-spec.md) for the full SDK specification.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](./docs/architecture.md) | System design, components, data flows |
| [Fault Tolerance](./docs/fault-tolerance.md) | All 10 recovery mechanisms in detail |
| [Testing Strategy](./docs/testing-strategy.md) | Test pyramid, scenarios, SLAs |
| [Roadmap](./docs/roadmap.md) | Phased build plan with milestones |
| [API Spec](./docs/api-spec.md) | Developer SDK and internal APIs |
| [Join mesh](./docs/join-mesh.md) | `pip install clustermesh` and worker CLI |
| [Publish to PyPI](./docs/publish-pypi.md) | Build, token setup, and upload guide |

## License

MIT — see [LICENSE](./LICENSE).
