# Shuttle — Distribution & Release Guide

## Overview

Shuttle is distributed via GitHub Releases. When you push a version tag, the CI/CD workflow automatically builds the package and creates a GitHub Release.

## Release Workflow

### How It Works

1. You bump the version in `pyproject.toml` and `/src/utils/constants.py`
2. You merge `dev` → `main`
3. You push a `v*` tag
4. GitHub Actions builds the distribution and creates a release

### Step-by-Step Release Commands

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

### What the CI/CD Does

The `.github/workflows/publish.yml` workflow triggers on `v*` tags and:

1. **build-python** (Ubuntu) — builds `.tar.gz` and `.whl` packages
2. **build-macos** (macOS runner) — builds `Shuttle.app` via PyInstaller, wraps in `Shuttle.dmg`
3. **release** — creates a GitHub Release with all artifacts attached:
   - `Shuttle.dmg` — double-click installer for macOS users
   - `shuttle-X.Y.Z-py3-none-any.whl` — pip-installable package
   - `shuttle-X.Y.Z.tar.gz` — source distribution

No PyPI publishing — Shuttle is a desktop app, not a library.

### First Launch Note

Users downloading `Shuttle.dmg` will need to run this once (unsigned app):

```bash
xattr -cr /Applications/Shuttle.app
```

## Version Numbering

Use semantic versioning: `MAJOR.MINOR.PATCH`

| Bump  | When                              | Example       |
| ----- | --------------------------------- | ------------- |
| PATCH | Bug fixes, small tweaks           | 1.1.0 → 1.1.1 |
| MINOR | New features (non-breaking)       | 1.1.0 → 1.2.0 |
| MAJOR | Breaking changes, major redesigns | 1.2.0 → 2.0.0 |

### Examples

- Fixed a crash when disconnecting → **PATCH**
- Added Android USB support → **MINOR**
- Added upload retry, queue persistence, per-server default bookmarks, and UI layout updates → **MINOR**
- Renamed app from PiSync to Shuttle, new config format → **MAJOR**

## Suggested 2.2.0 Release Notes

Use these as a starting point for the next GitHub Release:

- Added per-server bookmarks and per-server default start folders
- Added upload queue persistence so queued uploads can recover after restart
- Added automatic upload retry with up to 3 attempts
- Updated disk usage bar to follow the currently browsed filesystem, including mounted drives
- Made the Transfers panel larger and expandable
- Moved Activity Log out of the main screen into `View → Diagnostics Log...`
- Removed duplicate explorer title from the main window
- Kept partial byte-level resume and download queue persistence as future work

## Building Locally

### Source Distribution + Wheel

```bash
python -m build
# Output: dist/shuttle-X.Y.Z.tar.gz and dist/shuttle-X.Y.Z-py3-none-any.whl
```

### Standalone Executable (PyInstaller)

```bash
./scripts/build_exe.sh
# Output: standalone binary in dist/
```

## Installation Methods

```bash
# From wheel file
pip install shuttle-X.Y.Z-py3-none-any.whl

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
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `src/utils/constants.py`
- [ ] App runs locally without errors (`python main.py`)
- [ ] README updated if there are user-facing changes
- [ ] Merged dev → main
- [ ] Tag pushed
