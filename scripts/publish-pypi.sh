#!/usr/bin/env bash
# Build and upload clustermesh to PyPI.
# Full guide: docs/publish-pypi.md
#
# You do NOT need your PyPI password — use an API token:
#   https://pypi.org/manage/account/token/
#
#   export TWINE_USERNAME=__token__
#   export TWINE_PASSWORD=pypi-XXXXXXXX
#
# TestPyPI:  TWINE_REPOSITORY=testpypi ./scripts/publish-pypi.sh
# Production: ./scripts/publish-pypi.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing build tools"
python3 -m pip install -q --upgrade build twine hatchling

echo "==> Cleaning previous dist/"
rm -rf dist/ build/
find . -maxdepth 1 -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

echo "==> Building sdist + wheel"
python3 -m build

echo "==> Validating artifacts"
python3 -m twine check dist/*

REPO="${TWINE_REPOSITORY:-pypi}"
echo "==> Uploading to ${REPO}"
python3 -m twine upload --non-interactive --repository "${REPO}" dist/*

echo ""
echo "Done. Install with:"
echo "  pip install clustermesh==$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
