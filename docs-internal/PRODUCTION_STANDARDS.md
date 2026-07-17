# Production Standards

> **Last updated:** July 2026
> **Version:** 3.5.1

---

## Current Status

| Category                    | Status       | Notes                                        |
| --------------------------- | ------------ | -------------------------------------------- |
| Architecture & Organization | ✅ Solid     | Clean layered MVC with DeviceClient protocol |
| Packaging & Distribution    | ✅ Complete  | pyproject.toml, CI/CD, GitHub Releases       |
| Dependency Management       | ✅ Complete  | pip-tools with locked versions               |
| CI/CD Automation            | ✅ Complete  | Lint + test on push, build + release on tag  |
| Documentation               | ✅ Good      | Architecture, diagrams, roadmap, guides      |
| Testing & QA                | ✅ Complete  | 448 unit tests, mirrors src/ structure       |
| Code Quality Tools          | ✅ Enforced  | black, isort, flake8 via `make format/lint`  |
| Release Management          | ✅ Automated | `make release V=X.Y.Z`                       |

---

## What's Production-Grade

### Architecture

```
Presentation Layer (Views, Widgets)
    ↓
Controller Layer (5 controllers)
    ↓
Service Layer (10 services)
    ↓
Client Layer (DeviceClient protocol + 3 implementations)
    ↓
Infrastructure (Paramiko SFTP, ADB subprocess, pymobiledevice3 AFC)
```

- Clear separation of concerns with layered architecture
- No business logic in UI code
- `DeviceClient` protocol (`src/clients/`) enables polymorphic device handling
- `ServerConfig` dataclass replaces raw dict access with typed fields
- Service layer encapsulates external dependencies
- Client layer isolated in `src/clients/` with clean protocol boundary

### Error Handling

- Custom exception hierarchy in `src/models/errors.py` (5 categories, 14 exception types)
- Structured error logging to JSON (last 500 entries, `~/.FileSling/logs/errors.json`)
- Global crash handler with dialog + one-click GitHub issue reporting
- Transfer failures don't delete local files
- Connection failures gracefully show server selection dialog

### Threading

- QThread workers with signal/slot pattern (5 worker types)
- `ConnectionWorker` — async SSH connect (eliminates 30s UI freeze)
- 3 dedicated SFTP channels (explorer, metadata, background)
- Separate SFTP sessions per transfer (no shared state)
- Background directory loading, search, and disk usage calculation

### Configuration

- Pydantic model with field validators (host, SSH key, paths, theme)
- Multi-server support with typed `ServerConfig` dataclass
- Auto-connect to default server
- Per-server bookmarks, download directories, and extension filters
- Config stored at `~/.FileSling/config.json`
- Settings export/import as JSON

### Transfer Reliability

- Upload queue persists to `~/.FileSling/transfer_queue.json`
- Failed uploads retry automatically up to 3 times
- Failed downloads retry up to 3 times
- Restored uploads restart after app crash or quit
- rsync delta transfers when available (only sends changed bytes)
- Duplicate detection before upload/download
- Close button hides window (app persists in menu bar)
- ⌘Q confirms only during active transfers, otherwise quits immediately
- Menu bar icon with live activity status dropdown

### Testing

- **448 unit tests** across 26 test files
- Test directory mirrors src/ structure:
  - `tests/clients/` — ADB, iOS, DeviceClient protocol (3 files)
  - `tests/config/` — Settings (1 file)
  - `tests/controllers/` — All 4 non-trivial controllers (4 files)
  - `tests/models/` — Errors, ServerConfig (2 files)
  - `tests/services/` — All 8 services (8 files)
  - `tests/utils/` — Constants, crash handler, helper, icons, theme (5 files)
  - `tests/views/` — Quick Fix dialog (1 file)
  - `tests/widgets/` — Transfer queue widget (1 file)
  - `tests/workers/` — Download worker (1 file)
- Shared fixtures in `conftest.py` (tmp_dir, sample_config, sample_files)
- CI runs on every push to `dev` and PRs to `main`

---

## Known Issues

See [BUGS.md](BUGS.md) for detailed tracking. Summary:

- **8 performance bugs** — NFO reads, ffprobe, and some SFTP calls block the main thread
- **3 threading risks** — Shared SFTP connections without synchronization in some paths
- **5 logic bugs** — NFO sidecar gaps, ADB/iOS edge cases

---

## What's Next (When You're Ready)

### Expand Test Coverage

Current tests cover clients, services, models, utils, and controllers. Next steps:

- Widget tests using `pytest-qt` for remaining widgets
- View tests for dialogs (batch rename, convert settings, folder picker)
- End-to-end connection tests against a local SSH server
- Integration tests for transfer flows (mock SFTP)

### Code Quality Improvements

From the roadmap (Priority 4):

- Extract workers from widgets (DirectoryLoader, ConvertWorker, LoadingSpinner)
- SSH exec helper to reduce 22 repetitions of open_session pattern
- Connection state machine for deterministic lifecycle
- `__all__` exports for each module

---

## Release Process

See `DISTRIBUTION.md` for full details. Quick reference:

```bash
make release V=3.3.0
```

This bumps version, commits, merges to main, tags, and pushes. GitHub Actions handles the rest.

---

## Dependencies

Production (4 packages + 1 optional):

- **PySide6 ≥6.10.0** — Qt UI framework
- **Paramiko ≥3.5.1** — SSH/SFTP
- **Pydantic ≥2.0.0** — Settings validation
- **send2trash ≥1.8.3** — Safe file deletion
- **pymobiledevice3 ≥4.0.0** — iOS device access (optional)

Development tools:

- pytest, pytest-cov, pytest-qt — testing
- black, isort — formatting
- flake8, mypy, pylint — linting
- build, twine, pyinstaller — packaging & distribution
- pip-tools — dependency management
