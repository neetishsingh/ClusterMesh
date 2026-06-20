# API Specification

Developer-facing SDK and internal service APIs for ClusterMesh.

## Developer SDK (Implemented — Phase 2)

### Task Decorator

```python
from mesh import task, submit

@task(
    cpu=16,              # cores required
    ram="64GB",          # memory required
    gpu=1,               # GPU count (0 = no GPU)
    vram="24GB",         # VRAM required (if gpu > 0)
    cuda="12",           # minimum CUDA version
    network="10Gbps",    # minimum network bandwidth
    pool="gpu",          # resource pool: cpu | memory | gpu | night
    replicas=2,          # run on N nodes simultaneously
    checkpoint=True,     # enable periodic checkpointing
    checkpoint_interval=30,  # seconds between checkpoints
    preemption_ok=True,  # allow preemption (default True)
)
def train_model():
    ...
```

### Job Submission

```python
# Submit and wait for result
result = submit(train_model)

# Submit async, get job handle
job = submit(train_model, async_=True)
job.wait(timeout=3600)
job.cancel()

# Submit with idempotency key
job = submit(train_model, idempotency_key="daily-etl-2026-06-20")
```

### DAG Pipelines

```python
from mesh import pipeline

@pipeline
def etl():
    raw = read_csv("s3://bucket/data.csv")
    filtered = filter_rows(raw, condition="age > 18")
    joined = join(filtered, lookup_table)
    aggregated = aggregate(joined, group_by="region")
    write_parquet(aggregated, "s3://bucket/output/")
```

---

## Internal APIs (Phase 0 — Implemented)

### Models

```python
from mesh.models import (
    Node,              # compute node representation
    NodeState,         # HEALTHY | SUSPECTED | DEAD | PREEMPTED
    NodeResources,     # cpu, ram, gpu, vram, network, battery
    TaskSpec,          # task requirements + config
    ResourceRequirements,  # cpu, ram, gpu, vram, cuda, network
    ResourcePool,      # CPU | MEMORY | GPU | NIGHT
)
```

### Health

```python
from mesh.health import HeartbeatTracker, NodeHealthRegistry

tracker = HeartbeatTracker(
    interval_seconds=2.0,
    suspected_threshold=3,
    dead_threshold=5,
)

registry = NodeHealthRegistry(tracker)
registry.register("LAPTOP-55")
registry.record_heartbeat("LAPTOP-55")
state = registry.get_state("LAPTOP-55")  # NodeState.HEALTHY
```

### Scheduler

```python
from mesh.scheduler import NodeScorer, PlacementEngine

scorer = NodeScorer()
score = scorer.score(node, task_requirements)

engine = PlacementEngine(scorer)
assignment = engine.place(task_spec, eligible_nodes)
# → Placement(node_id="DESKTOP-11", score=0.87)
```

### Simulation

```python
from mesh.sim import SimCluster, SimClock, ChaosController

cluster = SimCluster(
    nodes=[
        SimAgent(node_id="LAPTOP-55", cpu_cores=8, ram_gb=16, preemptible=True),
        SimAgent(node_id="DESKTOP-11", cpu_cores=32, ram_gb=64),
    ],
    clock=SimClock(),
)

cluster.submit(TaskSpec(name="etl", cpu=4, ram_gb=8))
cluster.run(until=60.0)

chaos = ChaosController(cluster)
chaos.kill_node("LAPTOP-55", at=30.0)
cluster.run(until=120.0)
```

---

## gRPC Protocol (Implemented — Phase 3)

### Agent → Driver

| RPC | Direction | Description |
|-----|-----------|-------------|
| `RegisterNode` | Agent → Driver | Join cluster with resource report |
| `Heartbeat` | Agent → Driver | Every 2s health ping |
| `ReportResources` | Agent → Driver | Every 1s resource metrics |
| `PreemptionWarning` | Agent → Driver | User activity detected |
| `TaskProgress` | Agent → Driver | Checkpoint + progress update |
| `TaskComplete` | Agent → Driver | Task finished (success/failure) |

### Driver → Agent

| RPC | Direction | Description |
|-----|-----------|-------------|
| `AssignTask` | Driver → Agent | Schedule task on this node |
| `CancelTask` | Driver → Agent | Cancel running task |
| `PauseTask` | Driver → Agent | Preemption pause |
| `MigrateTask` | Driver → Agent | Move task to another node |
| `InstallLibrary` | Driver → Agent | Cluster-wide library install |

---

## REST API (Planned — Phase 5)

### Dashboard / Management

```
GET    /api/v1/cluster/status          Cluster overview
GET    /api/v1/nodes                   List all nodes
GET    /api/v1/nodes/{id}              Node details
POST   /api/v1/nodes/{id}/kill         Kill node processes
POST   /api/v1/nodes/{id}/pause        Pause node tasks
POST   /api/v1/nodes/{id}/migrate      Migrate all tasks

GET    /api/v1/jobs                    List jobs
GET    /api/v1/jobs/{id}               Job details + DAG
POST   /api/v1/jobs                    Submit job
DELETE /api/v1/jobs/{id}               Cancel job

GET    /api/v1/libraries               Cluster library catalog
POST   /api/v1/libraries/install       Install on pool/nodes

GET    /api/v1/metrics/savings         Cost savings analytics
WS     /api/v1/stream                  Live cluster events
```

---

## Configuration

```yaml
# mesh.yaml
driver:
  heartbeat_interval: 2s
  suspected_threshold: 3
  dead_threshold: 5
  failover_timeout: 10s

scheduler:
  weights:
    cpu: 0.35
    memory: 0.25
    gpu: 0.15
    reliability: 0.15
    network: 0.10
  battery_min_pct: 60
  speculation_multiplier: 1.5

pools:
  night:
    start_hour: 18
    end_hour: 8
    node_types: [laptop]
  gpu:
    require_cuda: true
```
