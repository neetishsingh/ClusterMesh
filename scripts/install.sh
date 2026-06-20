#!/usr/bin/env bash
# ClusterMesh worker installer — pip-based
# Usage: curl -fsSL .../install.sh | bash -s -- 192.168.1.10:50050
set -euo pipefail

DRIVER="${1:-${MESH_DRIVER_ADDRESS:-}}"
PYTHON="${PYTHON:-python3}"

echo "========================================"
echo "  ClusterMesh Worker Installer"
echo "========================================"

if ! command -v "$PYTHON" &>/dev/null; then
  echo "Error: Python 3.11+ required."
  exit 1
fi

echo "Installing clustermesh from PyPI (or local wheel)..."
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install clustermesh --quiet 2>/dev/null || {
  echo "PyPI install failed — install from source: pip install ."
  exit 1
}

if [ -z "$DRIVER" ]; then
  echo ""
  echo "Installed. Join a cluster with:"
  echo "  clustermesh join YOUR_DRIVER_IP:50050 --open"
  exit 0
fi

echo ""
echo "Starting worker → $DRIVER"
echo "Local UI: http://127.0.0.1:50052"
echo ""
exec clustermesh join "$DRIVER" --open
