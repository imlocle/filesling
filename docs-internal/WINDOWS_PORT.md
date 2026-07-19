# Windows Port — Checklist

> **Last updated:** July 2026 — Version 3.5.1
>
> Tracking what's needed to run FileSling on Windows.

---

## Summary

FileSling is ~90% cross-platform already. The core app (Qt UI, Paramiko SFTP, ADB, transfer logic, all controllers/services/workers) runs on any OS. Only 8-10 platform-specific calls needed Windows alternatives.

---

## Platform Abstraction Layer

- [x] Create `src/platform/` package with OS resolution in `__init__.py`
- [x] `src/platform/base.py` — no-op stubs for unsupported platforms
- [x] `src/platform/macos.py` — macOS implementations (caffeinate, osascript, security CLI)
- [x] `src/platform/windows.py` — Windows implementations (keyring, SetThreadExecutionState, Explorer, Qt tray)

---

## Service Refactoring

- [x] `keychain_service.py` → delegates to `src.platform` credential functions
- [x] `notification_service.py` → delegates to `src.platform.notify` and `set_dock_badge`
- [x] `sleep_inhibitor_service.py` → delegates to `src.platform.inhibit_sleep` / `release_sleep`
- [x] `download_controller.py` → uses `src.platform.reveal_in_file_manager`
- [x] `transfer_queue_widget.py` → uses `src.platform.reveal_in_file_manager`

---

## Platform-Specific Items

- [x] **Keychain → Credential Manager** — Windows uses `keyring` library (in `windows.py`)
- [x] **Notifications** — Windows uses `QSystemTrayIcon.showMessage()` with `win11toast` fallback
- [x] **Dock badge → Taskbar badge** — Windows uses Qt's `setBadgeNumber` (Qt 6.5+)
- [x] **Sleep inhibitor** — Windows uses `SetThreadExecutionState` Win32 API
- [x] **Reveal in Finder → Explorer** — Windows uses `explorer /select,`
- [x] **NSBundle guard** — Already guarded with `if sys.platform == "darwin"` + `try/except ImportError`
- [x] **App icon (.ico)** — Generated via `scripts/generate_icons.py` alongside `.icns`

---

## Remaining (Not Started)

- [x] **Theme / Fonts** — Added `Segoe UI` to font stacks in both QSS files
- [x] **Config path** — `APP_DATA_DIR` resolves to `%APPDATA%\FileSling` on Windows, `~/.FileSling` on macOS
- [x] **ADB path detection** — Searches `%LOCALAPPDATA%\Android\Sdk\platform-tools\` and other common Windows locations
- [x] **rsync availability** — `is_rsync_available()` already returns False on Windows; SFTP fallback triggers automatically
- [x] **Path separator audit** — All local paths use `os.path.join`; remote paths correctly use `/` (POSIX)
- [x] **Windows PyInstaller build in CI** — Added `build-windows` job to `.github/workflows/publish.yml`
- [ ] **Windows QSS testing** — Widget spacing, borders, font sizes may look different (needs Windows machine)
- [ ] **Test on Windows 10 and 11** — Full end-to-end testing with SSH, ADB, transfers

---

## Architecture

Don't split the app into `macos/` and `windows/` folders. 95% of the code is already cross-platform. Only ~6 functions differ between platforms.

```
src/
├── platform/
│   ├── __init__.py              Exports platform-resolved functions
│   ├── base.py                  No-op stubs (Linux / unsupported)
│   ├── macos.py                 macOS implementations
│   └── windows.py               Windows implementations
├── services/
│   ├── keychain_service.py      → calls src.platform.store_credential / get_credential
│   ├── notification_service.py  → calls src.platform.notify
│   ├── sleep_inhibitor_service.py → calls src.platform.inhibit_sleep / release_sleep
│   └── ...                      (everything else unchanged)
└── ... (controllers, views, widgets, workers — all unchanged)
```

**Why this pattern:**

- No code duplication — controllers, views, widgets, workers stay where they are
- Only ~6 platform functions per OS
- Easy to add Linux later (add `linux.py`, update `__init__.py`)
- Testable — mock `src.platform` in tests without per-OS test suites

---

## CI/CD Changes (When Ready)

Add a Windows job to `.github/workflows/publish.yml`:

```yaml
build-windows:
  runs-on: windows-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.13"
    - run: pip install -r requirements.txt pyinstaller keyring
    - run: pyinstaller --name=FileSling --windowed --icon=assets/icons/generated/FileSling.ico --add-data="assets;assets" main.py
    - uses: actions/upload-artifact@v4
      with:
        name: FileSling-Windows
        path: dist/FileSling/
```

---

## Packaging Options

| Method                      | Pros                              | Cons                           |
| --------------------------- | --------------------------------- | ------------------------------ |
| PyInstaller `.exe` (folder) | Simple, portable                  | Large folder (~150MB)          |
| PyInstaller one-file `.exe` | Single file                       | Slow startup (unpacks to temp) |
| NSIS installer              | Professional, Add/Remove Programs | More build complexity          |
| MSIX (Windows Store)        | Auto-updates, sandboxed           | Microsoft signing required     |

**Recommendation:** Start with PyInstaller folder mode + zip. Add NSIS installer later if there's demand.

---

## Risks & Unknowns

- **Qt rendering:** Widget spacing and borders may look different. Need manual testing.
- **rsync availability:** Not installed by default on Windows. May need to bundle cwRsync or fall back to SFTP-only.
- **ADB path:** On macOS it's in Homebrew. On Windows it's typically in `%LOCALAPPDATA%\Android\Sdk\platform-tools\`.
- **File permissions:** Windows doesn't have Unix permissions. `sftp.chmod()` calls are fine (remote server is Linux), but local file handling differs.
- **Path separators:** Code already uses `"/"` for remote paths (POSIX). Local paths should use `os.sep` or `pathlib`.
