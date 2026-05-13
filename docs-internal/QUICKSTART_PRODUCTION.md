# Shuttle — Quick Reference

> Copy-paste commands for common development and release tasks.

---

## Development Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements-dev.txt

# Or install as editable package
pip install -e ".[dev]"

# Run the app
python main.py
```

---

## Release a New Version

### When to bump what

| Change type             | Bump  | Example       |
| ----------------------- | ----- | ------------- |
| Bug fix                 | PATCH | 1.1.0 → 1.1.1 |
| New feature             | MINOR | 1.1.0 → 1.2.0 |
| Breaking / major rework | MAJOR | 1.1.0 → 2.0.0 |

### Release commands

```bash
# 1. On dev branch, bump version in pyproject.toml
#    Edit: version = "X.Y.Z"

# 2. Commit and push
git add pyproject.toml
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

# Build standalone executable
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

## Code Quality (Optional)

```bash
# Format
black src main.py
isort src main.py

# Lint
flake8 src main.py
mypy src main.py

# Test (when tests exist)
pytest tests/ --cov=src
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
