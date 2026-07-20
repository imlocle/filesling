# Dependency Management Guide

> **Last updated:** July 2026 — Version 3.7.1

## Overview

FileSling uses **pip-tools** for dependency management. This provides:

- Reproducible builds — exact versions locked in `.txt` files
- Separated concerns — production vs development dependencies
- Easy updates — human-editable `.in` files compiled to `.txt` lock files
- Transitive dependency tracking — all sub-dependencies documented

## File Structure

```
requirements.in          # Top-level production deps (human-editable)
requirements.txt         # Locked production deps (auto-generated, committed)
requirements-dev.in      # Development deps (inherits production via -r requirements.in)
requirements-dev.txt     # Locked dev deps (auto-generated, committed)
pyproject.toml           # Package metadata + optional dependency groups
```

## Production Dependencies

| Package         | Version | Purpose                      |
| --------------- | ------- | ---------------------------- |
| paramiko        | ≥3.5.1  | SSH/SFTP transfers           |
| pydantic        | ≥2.0.0  | Settings validation          |
| pyside6         | ≥6.10.0 | Qt UI framework              |
| send2trash      | ≥1.8.3  | Safe file deletion           |
| pymobiledevice3 | ≥4.0.0  | iOS device access (optional) |

## Development Dependencies

| Package     | Purpose                         |
| ----------- | ------------------------------- |
| pytest      | Test runner                     |
| pytest-cov  | Coverage reporting              |
| pytest-qt   | Qt widget testing               |
| black       | Code formatter                  |
| isort       | Import sorter                   |
| flake8      | Linter                          |
| pylint      | Static analysis                 |
| mypy        | Type checker                    |
| build       | Build wheel/sdist               |
| twine       | Package upload (unused for now) |
| wheel       | Wheel format support            |
| pip-tools   | Dependency compilation          |
| pyinstaller | Standalone .app builds          |

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

### With iOS Support

```bash
pip install -r requirements.txt
pip install pymobiledevice3
```

## Updating Dependencies

### Update a Specific Package

```bash
# 1. Edit requirements.in with new version constraint
# 2. Recompile lock files
pip-compile requirements.in -o requirements.txt
pip-compile requirements-dev.in -o requirements-dev.txt

# 3. Install and verify
pip install -r requirements-dev.txt
```

### Update All to Latest Compatible

```bash
pip-compile requirements.in -o requirements.txt --upgrade
pip-compile requirements-dev.in -o requirements-dev.txt --upgrade
pip install -r requirements-dev.txt
```

## Adding New Dependencies

### Production Dependency

```bash
# 1. Add to requirements.in (e.g., `requests>=2.28.0`)
# 2. Also add to pyproject.toml [project.dependencies]
# 3. Recompile
pip-compile requirements.in -o requirements.txt
# 4. Install and test
pip install -r requirements.txt
# 5. Commit both .in and .txt files + pyproject.toml
```

### Development Dependency

```bash
# 1. Add to requirements-dev.in
# 2. Also add to pyproject.toml [project.optional-dependencies.dev]
# 3. Recompile
pip-compile requirements-dev.in -o requirements-dev.txt
# 4. Install
pip install -r requirements-dev.txt
# 5. Commit both files
```

## Security Updates

```bash
# Update specific package for a security patch
pip-compile requirements.in --upgrade-package paramiko -o requirements.txt
pip install -r requirements.txt

# Commit with context
git commit -am "security: update paramiko (CVE-XXXX)"
```

## pyproject.toml Optional Groups

The `pyproject.toml` defines optional dependency groups for different use cases:

```toml
[project.optional-dependencies]
ios = ["pymobiledevice3>=4.0.0"]         # iOS device support
dev = ["pytest", "black", "flake8", ...]  # Development tools
test = ["pytest", "pytest-cov", "pytest-qt"]  # Testing only
build = ["pyinstaller", "build", "twine"]     # Build tools
```

Install a specific group:

```bash
pip install -e ".[ios]"
pip install -e ".[dev]"
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

### PySide6 installation issues on Apple Silicon

```bash
# Ensure you're using Python 3.9+ built for arm64
python3 -c "import platform; print(platform.machine())"
# Should print: arm64
```

## FAQ

**Q: Should I commit .txt files?**
A: Yes. Lock files ensure everyone gets the same versions.

**Q: Can I install from .in files directly?**
A: Don't. Use `.txt` files for reproducibility.

**Q: How often should I update?**
A: Monthly for security patches, as-needed for features.

**Q: Why not use Poetry or PDM?**
A: pip-tools is simpler and integrates well with the existing pyproject.toml + requirements workflow. No lock-in to a specific tool.
