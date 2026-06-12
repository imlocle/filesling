# Architecture

## Overview

FileSling is a macOS file manager that sends files to connected devices (SSH servers, Android phones/tablets) through drag-and-drop. Built with Python and PySide6.

For visual diagrams of the system, see [System Diagram](SYSTEM_DIAGRAM.md).

## Project Structure

```
src/
├── config/
│   └── settings.py                 Pydantic config model + singleton
├── controllers/
│   ├── main_window_controller.py   Routes UI events → services
│   └── transfer_controller.py      Transfer queue management
├── models/
│   └── errors.py                   Custom exception hierarchy
├── services/
│   ├── adb_client.py               ADB client (mimics SFTPClient interface)
│   ├── connection_manager_service.py   SSH/SFTP connection lifecycle + health monitoring
│   ├── file_deletion_service.py    Safe deletion via send2trash
│   ├── activity_history_service.py  Persistent activity log (uploads, downloads, renames, deletes, moves)
│   ├── ios_client.py               iOS AFC client (mimics SFTPClient interface)
│   ├── notification_service.py     macOS notifications + Dock badge
│   ├── keychain_service.py         macOS Keychain credential storage
│   ├── rsync_service.py            rsync fast-path transfers over SSH
│   └── ffmpeg_service.py           Remote video conversion via SSH
├── utils/
│   ├── constants.py                App-wide constants and defaults
│   ├── crash_handler.py            Global exception handler + crash log
│   ├── helper.py                   Path helpers
│   ├── icons.py                    File type icon generation (colored, theme-safe)
│   ├── logging_signal.py           Qt signal logger + JSON error log
│   └── theme.py                    Theme management
├── views/                          Full windows and dialogs
│   ├── main_window.py              Main app window (toolbar, explorer, queue)
│   ├── server_selection_dialog.py  Server picker on launch
│   ├── settings_window.py          Settings editor (connection, files, appearance)
│   └── splash_screen.py            Startup splash
├── widgets/                        Reusable UI components
│   ├── connection_form_widget.py   Reusable SSH/ADB connection form
│   ├── file_explorer_widget.py     Remote file browser (tree, drag-drop, search)
│   └── transfer_queue_widget.py    Visual transfer queue panel
└── workers/                        Background thread workers
    ├── download_worker.py          Background SFTP/ADB download worker
    └── transfer_worker.py          Background SFTP/ADB upload worker
```

## Connection Backends

The app supports two connection types behind the same explorer UI:

### SSH (Remote Servers)

- Uses Paramiko `SFTPClient`
- Key-based authentication (with passphrase support)
- Password-based authentication as fallback
- Separate SFTP sessions for explorer vs transfers (thread-safe)

### ADB (Android Devices via USB or WiFi)

- Uses `ADBClient` class that mimics `SFTPClient` interface
- Commands: `adb shell ls`, `adb push`, `adb pull`, `adb shell mv/rm/mkdir`
- No persistent connection — each command is a subprocess call
- Requires Developer Mode + USB Debugging on device
- WiFi mode: `adb connect <ip>:5555` for wireless transfers (Android 11+ pairing supported)

### iOS (iPhone/iPad via USB)

- Uses `IOSClient` class that mimics `SFTPClient` interface
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
    → ManualTransferController.queue_transfer()
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
  → Results displayed in tree widget with colored file type icons
  → Tooltips show full path and size
  → Disk usage bar updated for current path filesystem
```

### Download (right-click)

```
Right-click → "⬇️ Download" (single) or "⬇️ Download All" (multi-select)
  → MainWindowController.download_item() / download_items()
    → Checks if file exists locally (duplicate detection)
    → If exists: asks overwrite or skip (single) / auto-skips (batch)
    → Opens dedicated SFTP session
    → DownloadWorker runs on QThread
      → sftp.get() or adb pull
      → Emits progress percentage
      → Saves to configured download directory (per-server or global)
      → Retries up to 3 times on failure
    → Sends macOS notification on completion
```

## Threading

| Thread          | Purpose                                       | Location              |
| --------------- | --------------------------------------------- | --------------------- |
| Main (UI)       | Qt event loop, all widget updates             | views/, widgets/      |
| DirectoryLoader | Background directory listing (per-navigation) | widgets/file_explorer |
| TransferWorker  | Background file upload (per-transfer)         | workers/              |
| DownloadWorker  | Background file download (per-download)       | workers/              |
| SearchWorker    | Background recursive search                   | widgets/file_explorer |
| HealthTimer     | Connection keepalive + latency (15s interval) | controllers/          |

Each transfer gets its own SFTP session via `open_sftp_session()`. The explorer uses the main SFTP client. They don't share state — no locks needed.

## Configuration

- Singleton `Settings` class loads from `~/.FileSling/config.json`
- Pydantic `SettingsConfig` model with validation
- Multi-server support with default server for auto-connect
- Server configs store connection type, credentials, base directory, per-server download dir, and extension filters
- Bookmarked folders and default start folder are stored per server
- Transfer history stored in `~/.FileSling/transfer_history.json` (last 200 records)
- Pending and in-progress upload queue recovery stored in `~/.FileSling/transfer_queue.json`
- Error logs stored in `~/.FileSling/logs/errors.json` (last 500 entries)
- Settings can be exported/imported as JSON for sharing between machines

## Main Window UI

- Server quick-switch dropdown in the toolbar (with "Manage Servers…" at bottom)
- Power button turns green when connected (no separate status bar)
- Explorer remains the primary workspace
- Activity panel (renamed from "Transfers") shows uploads, downloads, and conversions
- Queue ordering: active on top → queued → completed at bottom
- Clickable breadcrumb path bar for quick navigation to parent folders
- Diagnostics logs are hidden by default and available from `View → Diagnostics Log...`
- Transfer history available from `View → Transfer History...`
- Latency indicator shown inline in toolbar (color-coded)
- Transfer method dot indicator (green=rsync, blue=SFTP, orange=ADB)
- macOS menu bar with File, Edit, View, Help menus
- Window size and position remembered between sessions
- Downloads auto-reveal in Finder on completion
- macOS notifications on transfer complete/fail
- Dock badge shows pending transfer count

## Theming

- Three modes: Follow System, Light, Dark (configurable in Settings → Appearance)
- Stylesheets: `assets/styles/modern_theme.qss` (dark), `assets/styles/macos_light.qss` (light)
- `src/utils/theme.py` resolves system preference and applies the correct stylesheet
- UI elements use object names (e.g., `connection_connected`, `connection_warning`, `connection_slow`) for theme-aware colors
- File icons use custom-drawn colored pixmaps (`src/utils/icons.py`) visible in both light and dark modes
- Folder icons use native macOS `QStyle.standardIcon`

## Error Handling

- Custom exception hierarchy in `errors.py`
- Errors logged to `~/.FileSling/logs/errors.json` (last 500 entries)
- Global crash handler catches unhandled exceptions and shows a user-friendly dialog
- Crash reports saved to `~/.FileSling/crash.log` with one-click GitHub issue reporting
- Previous session crashes detected on next launch with option to view report
- Transfer failures don't delete local files
- Failed uploads are retried automatically before being marked failed
- Failed downloads are retried automatically up to 3 times
- Interrupted queued uploads are restored on next launch and restarted from the beginning
- Connection drops trigger auto-reconnect (15s health check interval)
- Connection failures show server selection dialog

## Dependencies

| Package         | Purpose                 |
| --------------- | ----------------------- |
| PySide6         | Qt UI framework         |
| Paramiko        | SSH/SFTP                |
| Pydantic        | Settings validation     |
| send2trash      | Safe file deletion      |
| pymobiledevice3 | iOS device access (AFC) |
