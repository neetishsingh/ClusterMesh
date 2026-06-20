# Push ClusterMesh to GitHub

The project is initialized locally with git. Remote: **https://github.com/neetishsingh/ClusterMesh**

## Current status

| Step | Status |
|------|--------|
| `git init` + initial commit on `main` | Done |
| Remote `origin` → `git@github.com:neetishsingh/ClusterMesh.git` | Configured |
| GitHub repo created | **Not yet** — create it once, then push |
| Push to GitHub | Done — https://github.com/neetishsingh/ClusterMesh |

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
| `Permission denied to deploykey` | Your default SSH key is a **deploy key** (read-only, one repo). Use HTTPS instead (see below) |
| `Permission denied (publickey)` | Add SSH key: https://github.com/settings/keys |
| `Invalid username or token` (HTTPS) | Run `gh auth login` then `gh auth setup-git` |
| `gh auth login` required | Run Option B step 1 |
| Large files rejected | Keep `node_modules/` and `.venv/` out of git (already ignored) |

### Deploy key error (most common on this machine)

If push fails with:

```text
ERROR: Permission to neetishsingh/ClusterMesh.git denied to deploykey
```

Your `~/.ssh/id_ed25519` key is registered as a **deploy key** on another repo (`applic`), not as your personal GitHub SSH key. Deploy keys cannot push to other repositories.

**Fix — use HTTPS via GitHub CLI** (already logged in as `neetishsingh`):

```bash
gh auth login          # once, if not logged in
gh auth setup-git      # wires git to use gh token
git remote set-url origin https://github.com/neetishsingh/ClusterMesh.git
git push -u origin main
```

**Alternative — new personal SSH key:**

```bash
ssh-keygen -t ed25519 -C "neetishsingh97@gmail.com" -f ~/.ssh/id_ed25519_github
```

Add `~/.ssh/id_ed25519_github.pub` at https://github.com/settings/ssh/new, then create `~/.ssh/config`:

```sshconfig
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
```

Then use SSH remote: `git@github.com:neetishsingh/ClusterMesh.git`
