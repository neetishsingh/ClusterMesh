# Publishing `clustermesh` to PyPI

This guide covers how to build and upload the **clustermesh** package to [PyPI](https://pypi.org/project/clustermesh/). Use it when you are ready to publish — no rush if credentials are not set up yet.

## Current status

| Item | Status |
|------|--------|
| Package name | `clustermesh` (available on PyPI as of prep) |
| Version | `0.9.0` (in `pyproject.toml` and `mesh/__init__.py`) |
| Build artifacts | Created locally under `dist/` after `python -m build` |
| PyPI upload | **Not published yet** — waiting on PyPI account / API token |
| Install from PyPI | `pip install clustermesh` works **after** the first upload |

Until the package is on PyPI, install from source or a local wheel:

```bash
# From repo root
pip install .

# Or from a built wheel
python -m build
pip install dist/clustermesh-0.9.0-py3-none-any.whl
```

---

## You do not need your PyPI password to upload

PyPI uploads use an **API token**, not your account password.

1. Log in at https://pypi.org (password reset below if needed).
2. Create a token at https://pypi.org/manage/account/token/
3. Export it in your shell before publishing:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmcCJ...   # paste full token once
```

- Username is always the literal string `__token__`.
- Password is the token value (starts with `pypi-`).
- Tokens are shown **once** when created — copy immediately or create a new one.

Optional: store credentials in `~/.pypirc` (see [Persistent credentials](#persistent-credentials-optional) below).

---

## Lost or forgotten PyPI password

1. Open https://pypi.org/account/login/
2. Click **Forgot password?**
3. Enter the email used when you registered.
4. Use the reset link in email to set a new password.
5. After login, create an API token (you still upload with the token, not the password).

If you never registered, create an account first: https://pypi.org/account/register/

---

## One-time setup

### 1. PyPI account

- Production: https://pypi.org/account/register/
- Test (recommended first): https://test.pypi.org/account/register/

### 2. API token

Production token: https://pypi.org/manage/account/token/

- **First release:** scope = **Entire account** (creates the `clustermesh` project).
- **Later releases:** scope = **Project: clustermesh** is enough.

TestPyPI token: https://test.pypi.org/manage/account/token/

### 3. Build tools (local)

```bash
cd /path/to/ClusterMesh
python3 -m pip install build twine hatchling
```

---

## Build only (no upload)

Use this anytime to verify the package before publishing:

```bash
cd /path/to/ClusterMesh
rm -rf dist build
python -m build
python -m twine check dist/*
```

Expected output:

```
Successfully built clustermesh-0.9.0.tar.gz and clustermesh-0.9.0-py3-none-any.whl
Checking dist/clustermesh-0.9.0-py3-none-any.whl: PASSED
Checking dist/clustermesh-0.9.0.tar.gz: PASSED
```

### Test install in a clean venv

```bash
python3 -m venv /tmp/clustermesh-test
/tmp/clustermesh-test/bin/pip install dist/clustermesh-0.9.0-py3-none-any.whl
/tmp/clustermesh-test/bin/clustermesh version
# → clustermesh 0.9.0
```

---

## Publish with the helper script

From the repo root:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX

./scripts/publish-pypi.sh
```

The script will:

1. Install `build`, `twine`, `hatchling`
2. Clean and rebuild `dist/`
3. Run `twine check`
4. Upload to PyPI (or TestPyPI if `TWINE_REPOSITORY=testpypi`)

### TestPyPI first (recommended)

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX    # TestPyPI token

TWINE_REPOSITORY=testpypi ./scripts/publish-pypi.sh

pip install -i https://test.pypi.org/simple/ clustermesh==0.9.0
```

### Manual upload (without script)

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

---

## After publishing

Anyone can install and join a cluster:

```bash
pip install clustermesh
clustermesh platform --port 8080 --site my-site    # driver
clustermesh join DRIVER:50050 --open               # worker
```

Verify on PyPI: https://pypi.org/project/clustermesh/

---

## Releasing a new version

PyPI **rejects** re-uploading the same version. For each release:

1. Bump version in **both**:
   - `pyproject.toml` → `[project] version`
   - `mesh/__init__.py` → `__version__`
2. Rebuild and upload:

```bash
python -m build
./scripts/publish-pypi.sh
```

Follow semver (e.g. `0.9.1` for fixes, `0.10.0` for features).

---

## What is included in the wheel

| Included | Not included |
|----------|----------------|
| `clustermesh` CLI | Full React dashboard (`frontend/`) |
| Worker mini-UI (`mesh/worker/static/index.html`) | Site config YAML (use `--mesh-config`) |
| gRPC proto + generated stubs | Dev dependencies |
| Driver, agent, scheduler, notebook API | |

The full dashboard is built separately (`cd frontend && npm run build`) and served by `clustermesh platform` when the built assets are present.

---

## Persistent credentials (optional)

Create `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmcCJ...

[testpypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmcCJ...
```

Then upload without exporting env vars:

```bash
python -m twine upload dist/*
python -m twine upload --repository testpypi dist/*
```

Keep this file private (`chmod 600 ~/.pypirc`). Prefer env vars in CI.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `403 Invalid or non-existent authentication` | Wrong token or expired; create a new token |
| `403 The user isn't allowed to upload to project` | Token scope too narrow; use project or account scope |
| `400 File already exists` | Version already on PyPI; bump version and rebuild |
| `HTTPError 404` on `pip install clustermesh` | Not published yet; use local `pip install .` |
| `twine check` README warning | Ensure `README.md` renders; fix broken markdown |
| Upload works but import fails | Test with clean venv; check `python -m build` logs |

---

## Security notes

- Never commit API tokens or `.pypirc` to git.
- Do not paste tokens into chat or issue trackers.
- Revoke compromised tokens at https://pypi.org/manage/account/token/
- Use TestPyPI for dry runs before production upload.

---

## Quick checklist

- [ ] PyPI account exists (password reset if needed)
- [ ] API token created and saved
- [ ] `python -m build` succeeds
- [ ] `twine check dist/*` passes
- [ ] Clean venv install + `clustermesh version` works
- [ ] (Optional) Upload to TestPyPI and test install
- [ ] Upload to production PyPI
- [ ] Confirm https://pypi.org/project/clustermesh/ shows `0.9.0`
