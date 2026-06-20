#!/usr/bin/env bash
# Dogfood ComputeMesh on local hardware — platform + agent + sample job.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate 2>/dev/null || {
  python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" -q
}

DB="${MESH_STATE_DB:-dogfood.db}"
PORT="${MESH_DASHBOARD_PORT:-8080}"
SITE="${MESH_SITE:-local-dev}"
CONFIG="${MESH_CONFIG:-config/sites.example.yaml}"

echo "==> Building UI..."
(cd frontend && npm run build --silent 2>/dev/null) || echo "    (skip frontend build)"

echo "==> Starting platform (site=$SITE)..."
mesh-platform --port "$PORT" --db "$DB" --site "$SITE" --mesh-config "$CONFIG" &
PLATFORM_PID=$!
sleep 3

cleanup() {
  kill "$PLATFORM_PID" 2>/dev/null || true
  kill "$AGENT_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Starting agent..."
mesh-agent --driver "localhost:50050" --location "$SITE" &
AGENT_PID=$!
sleep 2

echo "==> Cluster status:"
curl -sf "http://localhost:$PORT/api/v1/cluster/status" | python3 -m json.tool

echo ""
echo "==> Memory pool:"
curl -sf "http://localhost:$PORT/api/v1/memory/pool" | python3 -m json.tool

echo ""
echo "Dashboard: http://localhost:$PORT"
echo "Press Ctrl+C to stop."

wait "$PLATFORM_PID"
