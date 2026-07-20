# FileSling — Quick Reference

> Copy-paste commands for common development and release tasks.
> **Last updated:** July 2026 — Version 3.7.1

---

## Development Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies (production + dev + iOS)
make dev-install

# Or manually:
pip install -r requirements-dev.txt

# Run the app
make run
```

---

## Code Quality

```bash
# Format (black + isort)
make format

# Lint (flake8)
make lint

# Run tests (437 unit tests with coverage)
make test

# Run tests without coverage (faster)
.venv/bin/python -m pytest tests/ --no-cov -q
```

---

## Release a New Version

### When to bump what

| Change type             | Bump  | Example       |
| ----------------------- | ----- | ------------- |
| Bug fix                 | PATCH | 3.2.1 → 3.2.2 |
| New feature             | MINOR | 3.2.1 → 3.3.0 |
| Breaking / major rework | MAJOR | 3.2.1 → 4.0.0 |

### Release commands

```bash
# One command does everything:
make release V=3.3.0
```

This bumps version in `pyproject.toml` and `src/utils/constants.py`, commits, pushes to dev, merges to main, tags, and pushes the tag. GitHub Actions builds the `.dmg` automatically.

<details>
<summary>Manual steps (if make release isn't available)</summary>

```bash
# 1. On dev branch, bump version in pyproject.toml and src/utils/constants.py
#    Edit: version = "X.Y.Z" and VERSION = "X.Y.Z"

# 2. Commit and push
git add pyproject.toml src/utils/constants.py
git commit -m "bump version to X.Y.Z"
git push origin dev

# 3. Merge to main
git checkout main
git merge dev
git push origin main

# 4. Tag and push (triggers CI/CD → GitHub Release)
git tag vX.Y.Z
git push origin vX.Y.Z

# 5. Back to dev
git checkout dev
```

</details>

### If the build fails

```bash
# Fix the issue on dev, then:
git tag -d vX.Y.Z
git push origin --delete vX.Y.Z

# Merge fix to main
git checkout main
git merge dev
git push origin main

# Re-tag
git tag vX.Y.Z
git push origin vX.Y.Z
git checkout dev
```

---

## Build Locally

```bash
# Build wheel + source distribution
python -m build

# Build standalone .app executable
./scripts/build_exe.sh
```

---

## Update Dependencies

```bash
# Install pip-tools if you don't have it
pip install pip-tools

# Update all to latest compatible versions
pip-compile requirements.in -o requirements.txt --upgrade
pip-compile requirements-dev.in -o requirements-dev.txt --upgrade

# Install updated deps
pip install -r requirements-dev.txt

# Commit lock files
git add requirements.txt requirements-dev.txt
git commit -m "update dependencies"
```

---

## Git Branch Strategy

```
main  ← stable releases (tagged with vX.Y.Z)
  ↑
dev   ← active development (your daily branch)
  ↑
feat/ ← feature branches (optional, for bigger changes)
```

- Work on `dev` (or feature branches off dev)
- Merge to `main` only when releasing
- Tags on `main` trigger CI/CD builds
- Never commit directly to `main`

---

## Project Layout

```
src/
├── clients/        3 files — DeviceClient protocol, ADBClient, IOSClient
├── config/         1 file  — Settings singleton (Pydantic + JSON)
├── controllers/    5 files — main_window, connection, download, file_ops, transfer
├── models/         2 files — errors hierarchy, ServerConfig dataclass
├── platform/       3 files — OS abstraction (macOS, Windows, base stubs)
├── services/       10 files — connection_manager, rsync, ffmpeg, keychain, sleep_inhibitor, menu_bar, etc.
├── utils/          6 files — constants, crash handler, icons, logging, theme, helper
├── views/          2 windows + 7 dialogs
├── widgets/        8 reusable UI components
└── workers/        5 background QThread workers

tests/              Mirrors src/ structure (26 test files, 437 tests)
├── clients/        3 test files
├── config/         1 test file
├── controllers/    4 test files
├── models/         2 test files
├── services/       8 test files
├── utils/          5 test files
├── views/          1 test file
├── widgets/        1 test file
└── workers/        1 test file
```

---

## Useful Paths

| What                  | Where                                  |
| --------------------- | -------------------------------------- |
| App config            | `~/.FileSling/config.json`             |
| Transfer history      | `~/.FileSling/transfer_history.json`   |
| Pending uploads queue | `~/.FileSling/transfer_queue.json`     |
| Error logs            | `~/.FileSling/logs/errors.json`        |
| Crash log             | `~/.FileSling/crash.log`               |
| Version constant      | `src/utils/constants.py` → `VERSION`   |
| Version metadata      | `pyproject.toml` → `[project].version` |
