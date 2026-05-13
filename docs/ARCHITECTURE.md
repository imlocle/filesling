# Architecture

## Overview

Shuttle is a macOS file manager that sends files to connected devices (SSH servers, Android phones/tablets) through drag-and-drop. Built with Python and PySide6.

## Project Structure

```
src/
├── application/                    Business logic
│   └── manual_transfer_controller.py   Transfer queue (queues, processes, retries)
├── components/                     UI windows
│   ├── main_window.py              Main app window (toolbar, explorer, log, queue)
│   ├── server_selection_dialog.py  Server picker on launch
│   ├── settings_window.py          Settings editor (connection, behavior, files)
│   └── splash_screen.py            Startup splash
├── config/
│   └── settings.py                 Pydantic config model + singleton
├── controllers/
│   ├── main_window_controller.py   Routes UI events → services
│   └── transfer_worker.py          Background SFTP/ADB upload worker
├── models/
│   └── errors.py                   Custom exception hierarchy
├── services/
│   ├── adb_client.py               ADB client (mimics SFTPClient interface)
│   ├── connection_manager_service.py   SSH/SFTP connection lifecycle
│   └── file_deletion_service.py    Safe deletion via send2trash
├── utils/
│   ├── constants.py                App-wide constants and defaults
│   ├── helper.py                   Path helpers, size formatting
│   └── logging_signal.py          Qt signal logger + JSON error log
└── widgets/
    ├── connection_form_widget.py   Reusable SSH/ADB connection form
    ├── file_explorer_widget.py     Remote file browser (tree, drag-drop, search)
    └── transfer_queue_widget.py    Visual transfer queue panel
```

## Connection Backends

The app supports two connection types behind the same explorer UI:

### SSH (Remote Servers)

- Uses Paramiko `SFTPClient`
- Key-based authentication
- Separate SFTP sessions for explorer vs transfers (thread-safe)

### ADB (Android Devices via USB)

- Uses `ADBClient` class that mimics `SFTPClient` interface
- Commands: `adb shell ls`, `adb push`, `adb pull`, `adb shell mv/rm/mkdir`
- No persistent connection — each command is a subprocess call
- Requires Developer Mode + USB Debugging on device

## Data Flow

### Upload (drag-and-drop)

```
Finder drop → FileExplorerWidget.dropEvent()
  → MainWindow._handle_remote_drop()
    → Checks for duplicates (sftp.stat per file)
    → If duplicates found: shows dialog (overwrite / skip / cancel)
    → Calculates size, adds to TransferQueueWidget
    → ManualTransferController.transfer_to_pi()
      → Queues transfer
      → Processes sequentially:
        → Opens dedicated SFTP session (or uses ADB)
        → TransferWorker runs on QThread
        → Emits progress percentage
        → On success: deletes local file (if configured)
        → Moves to next queued item
```

### Directory Browsing

```
Navigate/Refresh → FileExplorerWidget.refresh()
  → Shows loading spinner
  → DirectoryLoader runs on QThread
    → SFTP: sftp.listdir() + sftp.stat()
    → ADB: adb shell ls -la
  → Results displayed in tree widget
  → Disk usage bar updated
```

## Threading

| Thread          | Purpose                                       |
| --------------- | --------------------------------------------- |
| Main (UI)       | Qt event loop, all widget updates             |
| DirectoryLoader | Background directory listing (per-navigation) |
| TransferWorker  | Background file upload (per-transfer)         |
| SearchWorker    | Background recursive search                   |

Each transfer gets its own SFTP session via `open_sftp_session()`. The explorer uses the main SFTP client. They don't share state — no locks needed.

## Configuration

- Singleton `Settings` class loads from `~/.Shuttle/config.json`
- Pydantic `SettingsConfig` model with validation
- Multi-server support with default server for auto-connect
- Server configs store connection type, credentials, and base directory

## Error Handling

- Custom exception hierarchy in `errors.py`
- Errors logged to `logs/errors.json` (last 500 entries)
- Transfer failures don't delete local files
- Connection failures show server selection dialog

## Dependencies

| Package    | Purpose             |
| ---------- | ------------------- |
| PySide6    | Qt UI framework     |
| Paramiko   | SSH/SFTP            |
| Pydantic   | Settings validation |
| send2trash | Safe file deletion  |
