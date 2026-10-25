# Sahayak (सहायक) — Git & GitHub Team Playbook
## Tri-Laptop Multi-Developer Collaboration Guide (Zero-Conflict Protocol)
### Project: Sahayak Phase 1 Implementation

---

## ⚡ Frequently Used Commands (Daily Quick Reference)

Keep this section handy for everyday operations on any laptop:

```bash
# --- 1. Check Status & Branch ---
git status                          # See modified, staged, and untracked files
git branch                          # See all local branches (* shows current)
git branch -a                       # See local AND remote GitHub branches

# --- 2. Stage & Commit ---
git add <file-or-folder>            # Stage specific file or folder (e.g. git add app/api/)
git add .                           # Stage ALL modified files in project
git commit -m "feat: your message"  # Commit with a clear message
git commit -am "feat: your message" # Shortcut: stage tracked files + commit in one command

# --- 3. Push to GitHub ---
git push origin <your-branch>       # Push your branch to GitHub (e.g. git push origin feat/gateway)
git push                            # Push to currently tracked remote branch

# --- 4. Sync with Main (Keep Branch Up to Date) ---
git fetch origin                    # Download latest updates from GitHub without merging
git pull origin main                # Fetch + merge latest changes from main into your branch

# --- 5. Stashing (Save Work Without Committing) ---
git stash                           # Shelve all current uncommitted changes
git stash list                      # View saved stashes
git stash pop                       # Restore your shelved changes back to working directory

# --- 6. View History ---
git log --oneline -n 10             # View last 10 commits in clean 1-line format
git diff                            # See unstaged line-by-line changes
git diff --staged                   # See staged changes ready to commit
```

---

## 🚀 Phase 0: One-Time Repository Initialization (Laptop 1 / Lead)

Run **once** when starting the project:

```bash
# 1. Navigate to project root
cd C:\Users\mohit\finance

# 2. Initialize Git with default branch 'main'
git init -b main

# 3. Create .gitignore to prevent committing junk files
cat << 'EOF' > .gitignore
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
env/
venv/
*.log
.pytest_cache/
.coverage
htmlcov/
EOF

# 4. Stage and commit initial project structure & contracts.py
git add .
git commit -m "chore: initial repository structure with frozen contracts"

# 5. Connect to GitHub remote and push
git remote add origin https://github.com/<YOUR-GITHUB-USERNAME>/sahayak.git
git push -u origin main
```

---

## 💻 Phase 1: Initial Setup for Each Laptop

Once `main` is pushed to GitHub, each laptop clones the repo and creates its dedicated branch:

### Laptop 1 (Dev A — Gateway & WhatsApp):
```bash
# 1. Clone repository
git clone https://github.com/<YOUR-GITHUB-USERNAME>/sahayak.git
cd sahayak

# 2. Create and switch to your feature branch
git checkout -b feat/gateway

# 3. Verify active branch
git branch
# Output should show: * feat/gateway
```

### Laptop 2 (Dev B — Database & Margin Core):
```bash
# 1. Clone repository
git clone https://github.com/<YOUR-GITHUB-USERNAME>/sahayak.git
cd sahayak

# 2. Create and switch to your feature branch
git checkout -b feat/db-core

# 3. Verify active branch
git branch
# Output should show: * feat/db-core
```

### Laptop 3 (Dev C — Vision AI & OCR Worker):
```bash
# 1. Clone repository
git clone https://github.com/<YOUR-GITHUB-USERNAME>/sahayak.git
cd sahayak

# 2. Create and switch to your feature branch
git checkout -b feat/vision

# 3. Verify active branch
git branch
# Output should show: * feat/vision
```

---

## 🔄 Phase 2: Daily Workflow & Commit Standards

### Step-by-Step Daily Routine (Every Laptop):

```bash
# STEP 1: Before starting work, ensure you have latest changes
git checkout <your-branch>          # e.g., git checkout feat/gateway
git fetch origin
git pull origin main                # Pull any approved updates from main

# STEP 2: Code in your assigned directory only!
# Laptop 1 -> app/api/ & tests/test_gateway.py
# Laptop 2 -> app/db/ & tests/test_database_rls.py
# Laptop 3 -> app/workers/ & tests/test_vision_worker.py

# STEP 3: Stage only your files
git add app/<your-folder>/
git add tests/<your-test-file>

# STEP 4: Commit using conventional commit format
git commit -m "feat(api): implement hmac signature verification for whatsapp webhook"

# STEP 5: Push your branch to GitHub
git push -u origin <your-branch>
```

### Recommended Commit Message Prefixes:
* `feat:` A new feature (e.g. `feat(db): add row-level security policy for invoices`)
* `fix:` A bug fix (e.g. `fix(vision): handle zero-byte image uploads gracefully`)
* `test:` Adding or updating tests (e.g. `test(gateway): add mock deduplication unit test`)
* `refactor:` Code refactoring without behavior change (e.g. `refactor(workers): optimize clahe contrast filter`)
* `chore:` Maintenance or tooling (e.g. `chore: update requirements.txt`)

---

## 🔀 Phase 3: The Strict Zero-Conflict Merge Sequence

> **CRITICAL RULE:** Do NOT merge all laptops simultaneously. Merge in this exact 3-step sequence:

```
  STEP 1: Merge Laptop 2 (Database & Models) ──> `main`
          │
          ▼
  STEP 2: Laptop 3 pulls updated `main`, tests worker, merges ──> `main`
          │
          ▼
  STEP 3: Laptop 1 pulls updated `main`, tests gateway, merges ──> `main`
```

---

### Step 1: Merging Laptop 2 (`feat/db-core`) First
Laptop 2 holds the database models and migrations that Laptop 1 and 3 depend on.

```bash
# On Laptop 2:
git checkout main
git pull origin main                # Make sure main is updated
git merge feat/db-core              # Merge your branch into local main
git push origin main                # Push merged main to GitHub
```
*(Or create a Pull Request on GitHub: `feat/db-core` ➔ `main` and click "Merge")*

---

### Step 2: Merging Laptop 3 (`feat/vision`) Second
Laptop 3 must test its Vision Worker against Laptop 2's new database models before merging.

```bash
# On Laptop 3:
# 1. Switch to your feature branch and pull new code from main
git checkout feat/vision
git fetch origin
git merge origin/main -m "chore: sync with main (db models from Laptop 2)"

# 2. Run local tests to ensure Vision worker connects to DB models
pytest tests/test_vision_worker.py

# 3. Merge into main and push
git checkout main
git pull origin main
git merge feat/vision
git push origin main
```

---

### Step 3: Merging Laptop 1 (`feat/gateway`) Third
Laptop 1 connects the outer WhatsApp Gateway to the complete backend (DB + Worker).

```bash
# On Laptop 1:
# 1. Switch to your feature branch and pull new code from main
git checkout feat/gateway
git fetch origin
git merge origin/main -m "chore: sync with main (db + vision worker)"

# 2. Run the complete test suite across all 3 modules
pytest tests/ -v

# 3. Merge into main and push
git checkout main
git pull origin main
git merge feat/gateway
git push origin main
```

---

## 🛠️ Phase 4: Emergency Troubleshooting & Problem Solving

### Problem 1: "I made changes to a file by mistake and want to discard them"
```bash
git restore <path/to/file>          # Discard changes in a single file
git restore .                       # Discard ALL uncommitted changes in current directory
```

### Problem 2: "I committed by mistake and want to undo the commit (keep code)"
```bash
git reset --soft HEAD~1             # Undoes the last commit, keeps your changes staged
```

### Problem 3: "I committed junk and want to completely erase the last commit"
```bash
git reset --hard HEAD~1             # WARNING: Completely destroys the last commit and files
```

### Problem 4: "Merge Conflict Occurred"
```bash
# 1. See which files have conflicts
git status                          # Look for "both modified"

# 2. Open the file in your IDE (Antigravity). Look for conflict markers:
# <<<<<<< HEAD (Current code)
# =======
# >>>>>>> feat/branch (Incoming code)

# 3. Edit the file to keep the correct lines and delete the markers.

# 4. Mark conflict as resolved and finish merge:
git add <resolved-file>
git commit -m "fix: resolve merge conflict between main and feat/branch"
git push origin <your-branch>
```

### Problem 5: "My branch is completely messed up, I want to reset it to GitHub's state"
```bash
git fetch origin
git reset --hard origin/<your-branch>
```

---

## 🧪 Final Verification Command (Run on any Laptop after Merge)

```bash
# On any machine on branch `main`:
git checkout main
git pull origin main

# Run the complete end-to-end integration test suite
pytest tests/test_gateway.py tests/test_database_rls.py tests/test_vision_worker.py -v
```

> **Target:** All unit tests return green (`PASSED`). Phase 1 is complete!
