# Joining a Machine to ComputeMesh

Any machine with **Python 3.11+** can join the cluster with a single pip install.

> **Note:** The package is prepared for PyPI but may not be published yet. If `pip install clustermesh` fails, install from source (`pip install .` in the repo) or see [publish-pypi.md](./publish-pypi.md).

## One-command join (recommended)

On the **driver** machine (once):

```bash
pip install clustermesh
clustermesh platform --port 8080 --site my-site
# Dashboard: http://localhost:8080
```

On **every worker** machine:

```bash
pip install clustermesh
clustermesh join 192.168.1.10:50050 --open
```

This will:

1. Install all Python dependencies automatically (`grpcio`, `psutil`, `fastapi`, …)
2. Start the **mesh-agent** and register with the driver
3. Open a **local worker UI** at http://127.0.0.1:50052 showing CPU, memory, processes, and cluster connection status

The worker appears in the main dashboard under **Compute** within a few seconds.

## CLI reference

| Command | Description |
|---------|-------------|
| `pip install clustermesh` | Install package + dependencies |
| `clustermesh join DRIVER:50050` | Join cluster as worker + local UI |
| `clustermesh join --discover` | Auto-find driver on LAN (needs `--mdns` on platform) |
| `clustermesh platform --port 8080` | Run driver + full dashboard |
| `clustermesh version` | Show version |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MESH_DRIVER_ADDRESS` | — | Driver `host:50050` |
| `MESH_NODE_ID` | hostname | Node identifier |
| `MESH_LOCATION` | `default` | Site label |
| `MESH_AGENT_ADDRESS` | `localhost:50051` | Agent gRPC bind |
| `MESH_PREEMPTIBLE` | `true` | Yield when user is active |

## Ports

| Port | Service |
|------|---------|
| 8080 | Cluster dashboard + API (driver) |
| 50050 | Driver gRPC (agents register here) |
| 50051 | Agent gRPC (tasks assigned here) |
| 50052 | **Local worker UI** (this machine only) |
| 6000 | Mesh relay (cross-site) |

## Optional extras

```bash
pip install "clustermesh[discovery]"   # mDNS auto-discovery
pip install pyspark                       # PySpark notebook cells on worker
```

## Verify

```bash
curl http://DRIVER_IP:8080/api/v1/nodes
curl http://127.0.0.1:50052/api/v1/worker/status   # on worker
```

## Legacy: mesh-agent

The lower-level command still works:

```bash
mesh-agent --driver 192.168.1.10:50050 --location my-site
```

Use `clustermesh join` for the worker UI and simpler onboarding.
