# Dependency Management Guide

## Overview

Shuttle uses **pip-tools** for dependency management. This provides:

- Reproducible builds — exact versions locked in `.txt` files
- Separated concerns — production vs development dependencies
- Easy updates — human-editable `.in` files compiled to `.txt` lock files
- Transitive dependency tracking — all sub-dependencies documented

## File Structure

```
requirements.in          # Top-level production deps (human-editable)
requirements.txt         # Locked production deps (auto-generated, committed)
requirements-dev.in      # Development deps (inherits production)
requirements-dev.txt     # Locked dev deps (auto-generated, committed)
```

## Production Dependencies

| Package    | Purpose             |
| ---------- | ------------------- |
| paramiko   | SSH/SFTP transfers  |
| pydantic   | Settings validation |
| pyside6    | Qt UI framework     |
| send2trash | Safe file deletion  |

## Installation

### First Time Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Production Only

```bash
pip install -r requirements.txt
```

## Updating Dependencies

### Update a Specific Package

```bash
# 1. Edit requirements.in with new version constraint
# 2. Recompile lock files
pip-compile requirements.in -o requirements.txt
pip-compile requirements-dev.in -o requirements-dev.txt

# 3. Install and verify
pip install -r requirements.txt
```

### Update All to Latest Compatible

```bash
pip-compile requirements.in -o requirements.txt --upgrade
pip-compile requirements-dev.in -o requirements-dev.txt --upgrade
```

## Adding New Dependencies

### Production Dependency

```bash
# 1. Add to requirements.in (e.g., `requests>=2.28.0`)
# 2. Recompile
pip-compile requirements.in -o requirements.txt
# 3. Install and test
pip install -r requirements.txt
# 4. Commit both .in and .txt files
```

### Development Dependency

```bash
# 1. Add to requirements-dev.in
# 2. Recompile
pip-compile requirements-dev.in -o requirements-dev.txt
# 3. Install
pip install -r requirements-dev.txt
# 4. Commit both files
```

## Security Updates

```bash
# Update specific package for a security patch
pip-compile requirements.in --upgrade-package paramiko -o requirements.txt
pip install -r requirements.txt

# Commit with context
git commit -am "security: update paramiko (CVE-XXXX)"
```

## Troubleshooting

### "pip-compile command not found"

```bash
pip install pip-tools
```

### Compilation fails with conflicts

```bash
# Check for incompatible constraints
pip-compile --verbose requirements.in

# Relax constraints if needed (e.g., >=3.5.1 instead of ==3.5.1)
```

## FAQ

**Q: Should I commit .txt files?**
A: Yes. Lock files ensure everyone gets the same versions.

**Q: Can I install from .in files directly?**
A: Don't. Use `.txt` files for reproducibility.

**Q: How often should I update?**
A: Monthly for security patches, as-needed for features.
