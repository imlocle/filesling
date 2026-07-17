# FileSling — Distribution & Release Guide

> **Last updated:** July 2026 — Version 3.5.1

## Overview

FileSling is distributed via GitHub Releases. When you push a version tag, the CI/CD workflow automatically builds the package and creates a GitHub Release.

## Release Workflow

### How It Works

1. You bump the version in `pyproject.toml` and `src/utils/constants.py`
2. You merge `dev` → `main`
3. You push a `v*` tag
4. GitHub Actions builds the distribution and creates a release

### Step-by-Step Release Commands

The fastest way to release is the Makefile shortcut:

```bash
make release V=3.3.0
```

This runs all the steps below automatically — bumps version, commits, merges to main, tags, and pushes. GitHub Actions takes over from there.

<details>
<summary>Manual steps (if you prefer doing it by hand)</summary>

```bash
# 1. Make sure dev is up to date and committed
git checkout dev
git status  # should be clean

# 2. Bump version in pyproject.toml and constants.py
# Edit: version = "X.Y.Z"

# 3. Commit the version bump
git add pyproject.toml src/utils/constants.py
git commit -m "bump version to X.Y.Z"
git push origin dev

# 4. Merge into main
git checkout main
git merge dev
git push origin main

# 5. Tag the release
git tag vX.Y.Z
git push origin vX.Y.Z

# 6. Go back to dev
git checkout dev
```

</details>

### What the CI/CD Does

The `.github/workflows/publish.yml` workflow triggers on `v*` tags and:

1. **build-python** (Ubuntu) — builds `.tar.gz` and `.whl` packages
2. **build-macos** (macOS runner) — builds `FileSling.app` via PyInstaller (includes pymobiledevice3 for iOS support), wraps in `FileSling.dmg`
3. **release** — creates a GitHub Release with all artifacts attached:
   - `FileSling.dmg` — double-click installer for macOS users
   - `filesling-X.Y.Z-py3-none-any.whl` — pip-installable package
   - `filesling-X.Y.Z.tar.gz` — source distribution

No PyPI publishing — FileSling is a desktop app, not a library.

### First Launch Note

Users downloading `FileSling.dmg` will need to run this once (unsigned app):

```bash
xattr -cr /Applications/FileSling.app
```

## Version Numbering

Use semantic versioning: `MAJOR.MINOR.PATCH`

| Bump  | When                              | Example       |
| ----- | --------------------------------- | ------------- |
| PATCH | Bug fixes, small tweaks           | 3.2.0 → 3.2.1 |
| MINOR | New features (non-breaking)       | 3.2.0 → 3.3.0 |
| MAJOR | Breaking changes, major redesigns | 3.2.0 → 4.0.0 |

### Examples

- Fixed a crash when disconnecting → **PATCH**
- Added iOS device support → **MINOR**
- Added rsync backend, video convert, detail panel → **MINOR**
- Renamed app from Shuttle to FileSling, new config format → **MAJOR**

## Quality Checks (CI)

The `.github/workflows/quality.yml` workflow runs on:

- Every push to `dev`
- Every PR to `main` or `dev`

It checks:

1. **Formatting** — `black --check` and `isort --check-only`
2. **Lint** — `flake8`
3. **Tests** — `pytest` (448 tests)

All must pass before merging to main.

## Building Locally

### Source Distribution + Wheel

```bash
python -m build
# Output: dist/filesling-X.Y.Z.tar.gz and dist/filesling-X.Y.Z-py3-none-any.whl
```

### Standalone Executable (PyInstaller)

```bash
./scripts/build_exe.sh
# Output: dist/FileSling.app
```

The build script bundles:

- All Python dependencies (paramiko, pydantic, PySide6, pymobiledevice3)
- Assets (icons, stylesheets)
- Hidden imports configured for PyInstaller compatibility

## Installation Methods

```bash
# From DMG (recommended for users)
# Download from GitHub Releases, drag to /Applications

# From wheel file
pip install filesling-X.Y.Z-py3-none-any.whl

# From source (development mode)
pip install -e .

# Run directly
python main.py
```

## Fixing a Failed Release

If the GitHub Actions build fails after you push a tag:

```bash
# 1. Fix the issue on dev
git checkout dev
# ... make fixes, commit, push ...

# 2. Delete the broken tag
git tag -d vX.Y.Z
git push origin --delete vX.Y.Z

# 3. Merge fix to main
git checkout main
git merge dev
git push origin main

# 4. Re-tag and push
git tag vX.Y.Z
git push origin vX.Y.Z

# 5. Back to dev
git checkout dev
```

## Pre-Release Checklist

- [ ] All changes committed and pushed to dev
- [ ] Tests passing (`make test` — 448 tests)
- [ ] Lint passing (`make lint`)
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `src/utils/constants.py`
- [ ] App runs locally without errors (`make run`)
- [ ] README updated if there are user-facing changes
- [ ] CHANGELOG updated with new entries
- [ ] Merged dev → main
- [ ] Tag pushed
