# Production Standards

> **Last updated:** May 2026
> **Version:** 3.0.0

---

## Current Status

| Category                    | Status       | Notes                                       |
| --------------------------- | ------------ | ------------------------------------------- |
| Architecture & Organization | ✅ Solid     | Clean layered architecture                  |
| Packaging & Distribution    | ✅ Complete  | pyproject.toml, CI/CD, GitHub Releases      |
| Dependency Management       | ✅ Complete  | pip-tools with locked versions              |
| CI/CD Automation            | ✅ Basic     | Build + release on tag push                 |
| Documentation               | ✅ Good      | Architecture, roadmap, internal guides      |
| Testing & QA                | ✅ Complete  | 132 unit tests, pytest, CI on push to dev   |
| Code Quality Tools          | ✅ Enforced  | black, isort, flake8 via `make format/lint` |
| Release Management          | ✅ Automated | `make release V=X.Y.Z`                      |

---

## What's Production-Grade

### Architecture

```
Presentation Layer (Views, Widgets)
    ↓
Controller Layer (MainWindowController, TransferController)
    ↓
Application Layer (ManualTransferController)
    ↓
Service Layer (ConnectionManager, ADBClient, FileDeletion)
    ↓
Infrastructure (Paramiko SFTP, ADB subprocess, Filesystem)
```

- Clear separation of concerns
- No business logic in UI code
- Service layer encapsulates external dependencies
- ADBClient mimics SFTPClient interface for polymorphism

### Error Handling

- Custom exception hierarchy in `errors.py`
- Structured error logging to JSON (last 500 entries)
- Transfer failures don't delete local files
- Connection failures gracefully show server selection

### Threading

- QThread workers with signal/slot pattern
- Separate SFTP sessions per transfer (no shared state)
- Background directory loading and search
- No locks needed due to session isolation

### Configuration

- Pydantic model with validation
- Multi-server support
- Auto-connect to default server
- Per-server bookmarks and default start folders
- Config stored at `~/.FileSling/config.json`

### Transfer Reliability

- Upload queue persists active and pending items to `~/.FileSling/transfer_queue.json`
- Failed uploads retry automatically up to 3 times
- Restored uploads restart from the beginning after app crash or quit
- Partial byte-level resume is still future work

---

## What's Next (When You're Ready)

### Expand Test Coverage

Current tests cover services, models, and utilities. Next steps:

- Integration tests for transfer flows (mock SFTP)
- Widget tests using `pytest-qt` (requires display)
- End-to-end connection tests against a local SSH server

### CI Quality Gates

Already implemented in `.github/workflows/quality.yml`:

- Runs on every push to `dev` and PRs to `main`
- Checks formatting (black, isort)
- Runs flake8 lint
- Runs full test suite

---

## Release Process

See `DISTRIBUTION.md` for full details. Quick reference:

```bash
make release V=3.0.0
```

This bumps version, commits, merges to main, tags, and pushes. GitHub Actions handles the rest.

---

## Dependencies

Production (4 packages):

- **PySide6** — Qt UI framework
- **Paramiko** — SSH/SFTP
- **Pydantic** — Settings validation
- **send2trash** — Safe file deletion

Development tools:

- pytest, pytest-cov, pytest-qt — testing
- black, isort — formatting
- flake8, mypy, pylint — linting
- build, twine, pyinstaller — packaging & distribution
- pip-tools — dependency management
