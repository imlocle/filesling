# FileSling — Distribution & Release Guide

## Overview

FileSling is distributed via GitHub Releases. When you push a version tag, the CI/CD workflow automatically builds the package and creates a GitHub Release.

## Release Workflow

### How It Works

1. You bump the version in `pyproject.toml` and `/src/utils/constants.py`
2. You merge `dev` → `main`
3. You push a `v*` tag
4. GitHub Actions builds the distribution and creates a release

### Step-by-Step Release Commands

The fastest way to release is the Makefile shortcut:

```bash
make release V=3.0.0
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
2. **build-macos** (macOS runner) — builds `FileSling.app` via PyInstaller, wraps in `FileSling.dmg`
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
| PATCH | Bug fixes, small tweaks           | 1.1.0 → 1.1.1 |
| MINOR | New features (non-breaking)       | 1.1.0 → 1.2.0 |
| MAJOR | Breaking changes, major redesigns | 1.2.0 → 2.0.0 |

### Examples

- Fixed a crash when disconnecting → **PATCH**
- Added Android USB support → **MINOR**
- Added upload retry, queue persistence, per-server default bookmarks, and UI layout updates → **MINOR**
- Renamed app from PiSync to FileSling, new config format → **MAJOR**

## Suggested 3.0.0 Release Notes

- Multi-select transfers: Download All, Move All, Delete All from context menu
- Batch rename with find/replace across multiple files
- macOS notifications on transfer complete/fail with optional sound
- Dock badge showing pending transfer count
- Connection health monitoring with auto-reconnect on drop
- Latency indicator in status bar (color-coded: green/orange/red)
- File type icons (colored, visible in both light and dark themes)
- File info tooltip on hover (full path + size)
- Drag-and-drop onto folders uploads directly into them
- Drag remote files to Finder to download
- Upload resume: skips already-uploaded files on retry
- Download retry: auto-retries failed downloads up to 3 times
- Compress folders before upload (optional)
- SSH key passphrase support
- Password-based SSH authentication as fallback
- macOS Keychain integration for secure credential storage
- Per-server download directory and file extension filters
- Export/import settings as JSON
- Fixed crash when closing during initial server selection

## Building Locally

### Source Distribution + Wheel

```bash
python -m build
# Output: dist/filesling-X.Y.Z.tar.gz and dist/filesling-X.Y.Z-py3-none-any.whl
```

### Standalone Executable (PyInstaller)

```bash
./scripts/build_exe.sh
# Output: standalone binary in dist/
```

## Installation Methods

```bash
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
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `src/utils/constants.py`
- [ ] App runs locally without errors (`python main.py`)
- [ ] README updated if there are user-facing changes
- [ ] Merged dev → main
- [ ] Tag pushed
