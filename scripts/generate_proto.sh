#!/usr/bin/env bash
# Regenerate gRPC Python stubs from mesh.proto
set -euo pipefail
cd "$(dirname "$0")/.."
python -m grpc_tools.protoc \
  -I mesh/proto \
  --python_out=mesh/proto \
  --grpc_python_out=mesh/proto \
  mesh/proto/mesh.proto
# Fix import path in generated grpc module
sed -i.bak 's/import mesh_pb2/from mesh.proto import mesh_pb2/' mesh/proto/mesh_pb2_grpc.py
rm -f mesh/proto/mesh_pb2_grpc.py.bak
echo "✓ Generated mesh/proto/mesh_pb2.py and mesh_pb2_grpc.py"
