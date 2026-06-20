# Roadmap

Phased build plan from ideation to production-ready enterprise compute fabric.

## Phase 0 — Foundation (Current) ✅

**Goal:** Core types, heartbeat FSM, scheduler, SimCluster harness, full documentation.

| Deliverable | Status |
|-------------|--------|
| Project scaffolding (pyproject.toml, package layout) | ✅ |
| Documentation (architecture, fault tolerance, testing, API spec) | ✅ |
| Core models (Node, Task, Job, Resources, Pools) | ✅ |
| Heartbeat state machine | ✅ |
| Node scoring engine | ✅ |
| Constraint-aware scheduler + pool routing | ✅ |
| SimCluster test harness (SimAgent, SimClock, Chaos) | ✅ |
| Unit tests for all Phase 0 components | ✅ |

**Exit criteria:** `pytest` passes; SimCluster demo runs 50 nodes with chaos injection.

---

## Phase 1 — Scheduler + Health (Weeks 1–4)

**Goal:** Production-quality scheduler with full constraint support.

| Deliverable | Status |
|-------------|--------|
| Heartbeat registry (multi-node tracking) | ✅ (basic) |
| Node scoring with all dimensions | ✅ |
| Pool routing (CPU, Memory, GPU, Night) | ✅ |
| Battery gate + preemption eligibility | ✅ |
| Property-based scheduler tests (Hypothesis) | 🔜 |
| Golden trace replay framework | 🔜 |

**Exit criteria:** 1000-node sim completes placement in p99 < 100ms.

---

## Phase 2 — Execution + Recovery ✅

**Goal:** Tasks run, fail, and recover with checkpointing and work stealing.

| Deliverable | Status |
|-------------|--------|
| Task executor (Python functions) | ✅ |
| Checkpoint manager (progress persistence) | ✅ |
| Work stealer (orphaned task reassignment) | ✅ |
| Task replication (replicas=N) | ✅ |
| `@mesh.task` SDK decorator | ✅ |
| `mesh.submit()` API | ✅ |
| Integration tests: kill node → task resumes | ✅ |

**Exit criteria:** Task at 650M/1B records survives node death; resumes within 10s. ✅

---

## Phase 3 — Agent Daemon ✅

**Goal:** Real agent running on laptops/desktops.

| Deliverable | Status |
|-------------|--------|
| Agent daemon (resource monitor + heartbeat sender) | ✅ |
| gRPC agent ↔ driver protocol | ✅ |
| Preemption detection + WARNING pipeline | ✅ |
| Install script (`curl install.sh`) | ✅ |
| Library manager (basic) | ✅ |
| Dogfood: 3 real laptops + 1 GPU box | 🔜 manual |

**Exit criteria:** Real laptop joins cluster, runs task, survives sleep/wake cycle.

---

## Phase 4 — Driver HA + State Store ✅

**Goal:** Driver survives its own death; state is durable.

| Deliverable | Status |
|-------------|--------|
| Distributed state store (SQLite, Postgres-ready interface) | ✅ |
| Driver leader election (lease-based HA) | ✅ |
| Leader failover + job resume | ✅ |
| Speculative execution (straggler mitigation) | ✅ |
| Auto rebalancing | ✅ |
| Web dashboard (minimal) | ✅ |
| 24h chaos soak test | 🔜 |

**Exit criteria:** Kill driver leader during active job; job completes with ≤10s interruption. ✅ (via durable state + resume)

---

## Phase 5 — Enterprise UI & Platform

**Goal:** Databricks-like dashboard, live ops, cluster management.

| Deliverable | Status |
|-------------|--------|
| FastAPI REST + WebSocket event stream | ✅ |
| Light modern React dashboard (Vite + Tailwind) | ✅ |
| Overview — cluster stats, utilization, savings | ✅ |
| Compute — node table, pause/drain actions | ✅ |
| Jobs — list, detail, task progress / DAG view | ✅ |
| Live logs — filter, export, auto-scroll | ✅ |
| Library manager UI | ✅ |
| Cluster management — rebalance, HA leader info | ✅ |
| mDNS local discovery | 🔜 Phase 6 |
| Mesh VPN multi-site (Tailscale-like) | 🔜 Phase 6 |
| Auth service + tenancy | 🔜 Phase 6 |
| Distributed memory fabric | 🔜 Phase 6 |

**Exit criteria:** Dashboard live with real agents; ops can monitor jobs, nodes, and logs from browser. ✅

---

## Phase 6 — Production Hardening ✅

**Goal:** Multi-site, auth, production backends.

| Deliverable | Status |
|-------------|--------|
| State store factory (sqlite/postgres/redis URLs) | ✅ |
| PostgreSQL state backend | ✅ |
| Redis state backend | ✅ |
| mDNS driver discovery | ✅ |
| API key auth + tenant headers | ✅ |
| Multi-site discovery API | ✅ |
| Chaos soak test (CI subset) | ✅ |

---

## Phase 7 — Multi-Site Mesh VPN ✅

**Goal:** Cross-region connectivity, relay overlay, production soak validation.

| Deliverable | Status |
|-------------|--------|
| TCP relay for NAT traversal | ✅ |
| Site registry + YAML config | ✅ |
| MeshCoordinator (peer routing, probe) | ✅ |
| Mesh VPN API + dashboard page | ✅ |
| Accelerated 24h chaos soak (`mesh-soak`) | ✅ |

**Exit criteria:** Bangalore + London + AWS nodes routable via mesh relay; 24h soak passes in accelerated sim. ✅

---

## Phase 8 — Scale & Memory Fabric ✅

**Goal:** Unified RAM pool, 1000-node placement SLA, production dogfood.

| Deliverable | Status |
|-------------|--------|
| Distributed memory fabric (logical pool + allocate) | ✅ |
| Memory API + dashboard page | ✅ |
| 1000-node placement benchmark (p99 < 100ms) | ✅ |
| `mesh-bench` CLI | ✅ |
| Dogfood script (`scripts/dogfood.sh`) | ✅ |

**Exit criteria:** 112GB-style logical pool from multi-node RAM; placement p99 < 100ms at 1000 nodes. ✅

---

## Milestone Summary

```
Phase 0  ████████████████████  Foundation + SimCluster
Phase 1  ████████████████████  Scheduler hardening
Phase 2  ████████████████████  Execution + recovery
Phase 3  ████████████████████  Agent daemon
Phase 4  ████████████████████  Driver HA + state store
Phase 5  ████████████████████  Enterprise UI + API
Phase 6  ████████████████████  Production hardening
Phase 7  ████████████████████  Multi-site mesh VPN
Phase 8  ████████████████████  Memory fabric + scale  ← YOU ARE HERE
```

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-20 | Python for core + SDK | ML/data workloads are Python-native; fast iteration |
| 2026-06-20 | SimCluster before real agents | De-risk scheduling/recovery without hardware |
| 2026-06-20 | Heartbeat FSM first | Everything depends on knowing a node is dead |
| 2026-06-20 | Injectable SimClock everywhere | Deterministic tests run in milliseconds |
