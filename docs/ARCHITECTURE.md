# Architecture

> **Last updated:** June 2026 — Version 3.2.1

## Overview

FileSling is a macOS file manager that sends files to connected devices (SSH servers, Android phones/tablets, iPhones/iPads) through drag-and-drop. Built with Python and PySide6.

For visual diagrams of the system, see [System Diagram](SYSTEM_DIAGRAM.md).

## Project Structure

```
src/
├── clients/
│   ├── adb_client.py                  ADB client (Android via USB/WiFi)
│   ├── device_client.py               DeviceClient Protocol (duck-typed interface)
│   └── ios_client.py                  iOS AFC client (iPhone/iPad via USB)
├── config/
│   └── settings.py                    Pydantic config model + singleton
├── controllers/
│   ├── connection_controller.py       SSH/ADB/iOS connection lifecycle
│   ├── download_controller.py         Download queue and worker management
│   ├── file_operations_controller.py  Rename, move, delete, create folder
│   ├── main_window_controller.py      Routes UI events → services
│   └── transfer_controller.py         Upload queue management + persistence
├── models/
│   ├── errors.py                      Custom exception hierarchy
│   └── server_config.py              Typed ServerConfig dataclass
├── services/
│   ├── activity_history_service.py    Persistent activity log
│   ├── connection_manager_service.py  SSH/SFTP lifecycle + health monitoring
│   ├── ffmpeg_service.py              Remote video conversion via SSH
│   ├── file_deletion_service.py       Safe deletion via send2trash
│   ├── keychain_service.py            macOS Keychain credential storage
│   ├── notification_service.py        macOS notifications + Dock badge
│   ├── remote_file_service.py         Centralized connection-lost detection
│   └── rsync_service.py              rsync fast-path transfers over SSH
├── utils/
│   ├── constants.py                   App-wide constants and defaults
│   ├── crash_handler.py               Global exception handler + crash log
│   ├── helper.py                      Path helpers
│   ├── icons.py                       File type icon generation (colored, theme-safe)
│   ├── logging_signal.py              Qt signal logger + JSON error log
│   └── theme.py                       Theme management
├── views/
│   ├── dialogs/
│   │   ├── batch_rename_dialog.py     Multi-file find/replace rename
│   │   ├── convert_settings_dialog.py Video conversion settings (codec, CRF, etc.)
│   │   ├── folder_picker_dialog.py    Remote folder browser for Move To
│   │   ├── quick_fix_dialog.py        Container change, timestamp fix, subtitle removal
│   │   └── server_selection_dialog.py Server picker on launch / server switch
│   ├── main_window.py                 Main app window (toolbar, explorer, queue)
│   ├── settings_window.py             Settings editor (connection, files, appearance)
│   └── splash_screen.py               Startup splash
├── widgets/
│   ├── bookmarks_bar.py               Quick-access folder bookmarks
│   ├── connection_form_widget.py      Reusable SSH/ADB/iOS connection form
│   ├── detail_panel.py                Side panel with metadata + stream info
│   ├── file_explorer_widget.py        Remote file browser (tree, drag-drop, search)
│   ├── inline_rename_editor.py        In-place file rename editor
│   ├── transfer_queue_widget.py       Visual transfer queue panel
│   └── video_convert_manager.py       Remote ffmpeg conversion manager
└── workers/
    ├── connection_worker.py           Async SSH connection in background
    ├── disk_usage_worker.py           Background disk space calculation
    ├── download_worker.py             Background SFTP/ADB download
    ├── search_worker.py               Background recursive file search
    └── transfer_worker.py             Background SFTP/ADB upload
```

## Connection Backends

The app supports three connection types behind the same explorer UI via the `DeviceClient` protocol (`src/clients/device_client.py`):

### SSH (Remote Servers)

- Uses Paramiko `SFTPClient`
- Key-based authentication (with passphrase support)
- Password-based authentication as fallback
- macOS Keychain integration for credential storage
- 3 dedicated SFTP channels for concurrency (explorer, metadata, background)
- Per-transfer SFTP sessions for uploads/downloads (no contention)
- rsync fast path when available (delta transfers, only changed bytes)

### ADB (Android Devices via USB or WiFi)

- Uses `ADBClient` class (`src/clients/adb_client.py`) implementing `DeviceClient` protocol
- Commands: `adb shell ls`, `adb push`, `adb pull`, `adb shell mv/rm/mkdir`
- No persistent connection — each command is a subprocess call
- Requires Developer Mode + USB Debugging on device
- WiFi mode: `adb connect <ip>:5555` for wireless transfers (Android 11+ pairing supported)

### iOS (iPhone/iPad via USB)

- Uses `IOSClient` class (`src/clients/ios_client.py`) implementing `DeviceClient` protocol
- Talks AFC (Apple File Conduit) protocol via `pymobiledevice3`
- Accesses the Media partition: DCIM (camera roll), Downloads, Photos
- No jailbreak required; device must be unlocked and trusted
- Optional dependency bundled in .dmg builds

## Data Flow

### Upload (drag-and-drop)

```
Finder drop → FileExplorerWidget.dropEvent()
  → Always targets current_path (no sub-folder highlighting for external drops)
  → MainWindow._handle_remote_drop()
    → Checks for duplicates (sftp.stat per file)
    → If duplicates found: shows dialog (overwrite / skip / cancel)
    → Calculates size, adds to TransferQueueWidget
    → TransferController.queue_transfer()
      → Queues transfer
      → Persists active/pending queue to ~/.FileSling/transfer_queue.json
      → Processes sequentially:
        → SSH key auth? Try rsync first (delta, compression, resume)
          → If rsync fails → fallback to SFTP silently
        → Opens dedicated SFTP session (or uses ADB/iOS client)
        → TransferWorker runs on QThread (src/workers/)
        → Skips already-uploaded files (resume support)
        → Optionally compresses folders before upload
        → Emits progress percentage
        → Retries failed uploads up to 3 times
        → On success: deletes local file (if configured), sends notification
        → Updates Dock badge
        → Moves to next queued item
```

### Directory Browsing

```
Navigate/Refresh → FileExplorerWidget.refresh()
  → Shows loading spinner
  → DirectoryLoader runs on QThread
    → SFTP: sftp.listdir() + sftp.stat()
    → ADB: adb shell ls -la
    → iOS: AFC listdir
  → Results displayed in tree widget with colored file type icons
  → Tooltips show full path and size
  → Disk usage bar updated for current path filesystem
```

### Download (right-click)

```
Right-click → "⬇️ Download" (single) or "⬇️ Download All" (multi-select)
  → DownloadController.download_item() / download_items()
    → Checks if file exists locally (duplicate detection)
    → If exists: asks overwrite or skip (single) / auto-skips (batch)
    → Opens dedicated SFTP session
    → DownloadWorker runs on QThread
      → sftp.get() or adb pull
      → Emits progress percentage
      → Saves to configured download directory (per-server or global)
      → Retries up to 3 times on failure
    → Sends macOS notification on completion
    → Optionally reveals in Finder
```

### Remote Video Conversion

```
Right-click video → "Convert to H.264/H.265/VP9"
  → VideoConvertManager.request_conversion()
    → Checks if ffmpeg installed on server
    → Opens ConvertSettingsDialog (codec, preset, CRF, audio, container)
    → Launches ffmpeg via dedicated SSH connection (won't block explorer)
    → Progress shown in activity panel
    → Replaces original file when done
    → Logged in activity history (action: "convert")
```

## SFTP Channel Architecture

```
ConnectionManagerService opens 3 channels at connect time:

┌─────────────────────────────────────────────────────────────┐
│  SSH Transport (single TCP connection)                       │
├─────────────────────────────────────────────────────────────┤
│  sftp_client     — Main thread: explorer UI operations      │
│  sftp_metadata   — Detail panel: NFO reads, ffprobe         │
│  sftp_background — DirectoryLoader, DiskUsageWorker         │
├─────────────────────────────────────────────────────────────┤
│  Per-transfer sessions (opened/closed per upload/download)  │
│  Per-conversion SSH connection (dedicated, independent)     │
└─────────────────────────────────────────────────────────────┘
```

This eliminates thread contention — Paramiko SFTP is NOT thread-safe, so each concurrent operation needs its own channel.

## Threading

| Thread           | Purpose                                       | SFTP Channel Used  |
| ---------------- | --------------------------------------------- | ------------------ |
| Main (UI)        | Qt event loop, all widget updates             | sftp_client        |
| DirectoryLoader  | Background directory listing (per-navigation) | sftp_background    |
| DetailPanel      | NFO reads, ffprobe (synchronous on channel)   | sftp_metadata      |
| DiskUsageWorker  | Background disk space calculation             | sftp_background    |
| ConnectionWorker | Async SSH connection (avoids 30s freeze)      | (none — connects)  |
| TransferWorker   | Background file upload (per-transfer)         | own session        |
| DownloadWorker   | Background file download (per-download)       | own session        |
| SearchWorker     | Background recursive search                   | sftp_background    |
| \_ConvertWorker  | Remote ffmpeg execution                       | own SSH connection |
| HealthTimer      | Connection keepalive + latency (15s interval) | sftp_client        |

## Configuration

- Singleton `Settings` class loads from `~/.FileSling/config.json`
- Pydantic `SettingsConfig` model with field validation
- Multi-server support with default server for auto-connect
- `ServerConfig` dataclass (`src/models/server_config.py`) for typed server access
- Server configs store: connection type, credentials, base directory, per-server download dir, extension filters, bookmarks
- Transfer history stored in `~/.FileSling/transfer_history.json` (last 200 records)
- Pending and in-progress upload queue recovery stored in `~/.FileSling/transfer_queue.json`
- Error logs stored in `~/.FileSling/logs/errors.json` (last 500 entries)
- Settings can be exported/imported as JSON for sharing between machines

## Main Window UI

- Server quick-switch dropdown in the toolbar (with "Manage Servers…" at bottom)
- Power button turns green when connected (no separate status bar)
- Explorer remains the primary workspace
- Activity panel shows uploads, downloads, and conversions
- Queue ordering: active on top → queued → completed at bottom
- Clickable breadcrumb path bar for quick navigation to parent folders
- Transfer method dot indicator (green=rsync, blue=SFTP, orange=ADB)
- Detail panel (toggle with ⌘I) showing metadata and stream info
- Bookmarks bar for quick folder access
- Diagnostics logs available from `View → Diagnostics Log...`
- Transfer history available from `View → Transfer History...`
- Latency indicator shown inline in toolbar (color-coded)
- macOS menu bar with File, Edit, View, Help menus
- Window size and position remembered between sessions
- Downloads auto-reveal in Finder on completion (configurable)
- macOS notifications on transfer complete/fail
- Dock badge shows pending transfer count
- Exit confirmation with "Quit After Jobs Finish" during active transfers

## Theming

- Three modes: Follow System, Light, Dark (configurable in Settings → Appearance)
- Stylesheets: `assets/styles/modern_theme.qss` (dark), `assets/styles/macos_light.qss` (light)
- `src/utils/theme.py` resolves system preference and applies the correct stylesheet
- UI elements use object names for theme-aware colors
- File icons use custom-drawn colored pixmaps (`src/utils/icons.py`) visible in both light and dark modes
- Folder icons use native macOS `QStyle.standardIcon`

## Error Handling

- Custom exception hierarchy in `src/models/errors.py`:
  - `FileSlingError` → `ConnectionError`, `TransferError`, `ConfigurationError`, `FileSystemError`, `ValidationError`
  - Specialized subclasses: `SSHConnectionError`, `AuthenticationError`, `FileUploadError`, `TransferVerificationError`, etc.
- Errors logged to `~/.FileSling/logs/errors.json` (last 500 entries)
- Global crash handler catches unhandled exceptions and shows a user-friendly dialog
- Crash reports saved to `~/.FileSling/crash.log` with one-click GitHub issue reporting
- Previous session crashes detected on next launch with option to view report
- Transfer failures don't delete local files
- Failed uploads are retried automatically before being marked failed
- Failed downloads are retried automatically up to 3 times
- Interrupted queued uploads are restored on next launch and restarted
- Connection drops trigger auto-reconnect (15s health check interval)
- Connection failures show server selection dialog

## Dependencies

| Package         | Version | Purpose                      |
| --------------- | ------- | ---------------------------- |
| PySide6         | ≥6.10.0 | Qt UI framework              |
| Paramiko        | ≥3.5.1  | SSH/SFTP                     |
| Pydantic        | ≥2.0.0  | Settings validation          |
| send2trash      | ≥1.8.3  | Safe file deletion           |
| pymobiledevice3 | ≥4.0.0  | iOS device access (optional) |
