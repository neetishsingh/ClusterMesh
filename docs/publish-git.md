# Push ClusterMesh to GitHub

The project is initialized locally with git. Remote: **https://github.com/neetishsingh/ClusterMesh**

## Current status

| Step | Status |
|------|--------|
| `git init` + initial commit on `main` | Done |
| Remote `origin` → `git@github.com:neetishsingh/ClusterMesh.git` | Configured |
| GitHub repo created | **Not yet** — create it once, then push |
| Push to GitHub | Waiting on repo creation |

SSH auth to GitHub works (`neetishsingh` account).

---

## Option A — Create repo in browser (fastest)

1. Open **https://github.com/new**
2. Repository name: `ClusterMesh`
3. Owner: `neetishsingh`
4. Choose **Public** or **Private**
5. **Do not** add README, `.gitignore`, or license (already in local repo)
6. Click **Create repository**

Then push from your machine:

```bash
cd /Users/neetishsingh_p/Desktop/ClusterMesh
git push -u origin main
```

---

## Option B — GitHub CLI

```bash
gh auth login
# follow prompts (GitHub.com → SSH or HTTPS → login)

cd /Users/neetishsingh_p/Desktop/ClusterMesh
gh repo create ClusterMesh --public --source=. --remote=origin --push
```

Use `--private` instead of `--public` for a private repo.

---

## Verify

After push:

```bash
git log -1 --oneline
git remote -v
```

Open: **https://github.com/neetishsingh/ClusterMesh**

---

## What is committed

- Python package (`mesh/`), tests, docs, frontend source
- `LICENSE`, `README.md`, `pyproject.toml`, publish scripts

**Excluded** (via `.gitignore`):

- `.venv/`, `node_modules/`, `dist/`, `build/`
- `clustermesh.db` (local SQLite)
- `.env`, `*.tsbuildinfo`

---

## Future pushes

```bash
git add -A
git commit -m "Your message"
git push
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Repository not found` | Create empty repo on GitHub first (Option A) |
| `Permission denied (publickey)` | Add SSH key: https://github.com/settings/keys |
| `gh auth login` required | Run Option B step 1 |
| Large files rejected | Keep `node_modules/` and `.venv/` out of git (already ignored) |
