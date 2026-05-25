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
| Testing & QA                | ❌ Missing   | No test suite yet                           |
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

### Testing (HIGH value)

Add a `tests/` directory with pytest:

```bash
pip install pytest pytest-cov
pytest tests/ --cov=src
```

Focus on:

- Settings validation (Pydantic model edge cases)
- Error hierarchy (correct exceptions raised)
- Helper utilities (path formatting, size calculations)

Skip UI tests initially — they require Qt display server setup.

### Code Formatting (LOW effort)

Already configured and working via Makefile:

```bash
make format   # runs black + isort
make lint     # runs flake8
```

### Linting (MEDIUM effort)

Already working:

```bash
make lint
# Or directly:
.venv/bin/python -m flake8 src main.py
.venv/bin/python -m mypy src main.py
```

### CI Quality Gates (FUTURE)

When you have tests and formatted code, add a second workflow that runs on push to `dev`:

```yaml
# .github/workflows/quality.yml
name: Quality Checks
on:
  push:
    branches: [dev]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install black isort flake8
      - run: black --check src main.py
      - run: isort --check-only src main.py
      - run: flake8 src main.py
```

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

Development tools (configured, optional):

- pytest, pytest-cov — testing
- black, isort — formatting
- flake8, mypy, pylint — linting
- build — packaging
