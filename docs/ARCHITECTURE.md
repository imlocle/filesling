# PiSync Architecture

## Overview

PiSync is a remote file manager built with Python and PySide6. It connects to any SSH server, lets you browse its filesystem, and transfer files via drag-and-drop from Finder.

## Project Structure

```
src/
├── application/           Business logic
│   └── manual_transfer_controller.py   Transfer queue management
├── components/            UI windows and dialogs
│   ├── main_window.py                  Main application window
│   ├── server_selection_dialog.py      Server picker
│   ├── settings_window.py              Settings editor
│   └── splash_screen.py                Startup splash
├── config/                Configuration
│   └── settings.py                     Pydantic settings model + singleton
├── controllers/           Orchestration
│   ├── main_window_controller.py       Routes UI events to services
│   └── transfer_worker.py              Background SFTP upload worker
├── models/                Data types
│   └── errors.py                       Custom exception hierarchy
├── services/              External I/O
│   ├── connection_manager_service.py   SSH/SFTP connection lifecycle
│   └── file_deletion_service.py        Safe file deletion (send2trash)
├── utils/                 Shared utilities
│   ├── constants.py                    App name, config filename
│   ├── helper.py                       Path helpers, size formatting
│   └── logging_signal.py              Qt signal-based logger + JSON error log
└── widgets/               Reusable UI components
    ├── file_explorer_widget.py         Remote file browser with drag-drop
    └── transfer_queue_widget.py        Visual transfer queue panel
```

## Data Flow

### Transfer (drag-and-drop)

```
User drops file on explorer
    → FileExplorerWidget.dropEvent()
    → MainWindow._handle_remote_drop()
        → Calculates size, adds to TransferQueueWidget
        → Calls ManualTransferController.transfer_to_pi()
            → Queues the transfer
            → Starts processing (if idle)
                → Opens dedicated SFTP session
                → Creates TransferWorker on QThread
                → Worker uploads files, emits progress
                → On completion: deletes local file (if configured)
                → Moves to next queued item
```

### Connection

```
App launches
    → Settings loads default_server_id
    → If default set: load server config, auto-connect
    → If not: show ServerSelectionDialog
    → ConnectionManagerService.connect()
        → SSH connect with retry (3 attempts)
        → Open SFTP session
        → Bind to FileExplorerWidget
```

## Threading Model

```
Main Thread (UI)
    └── Qt event loop, all UI updates

Transfer Thread (per-transfer)
    └── TransferWorker.run() — SFTP upload
    └── Own SFTP session (separate from explorer)

Directory Loader Thread (per-navigation)
    └── DirectoryLoader.run() — SFTP listdir + stat
    └── Uses explorer's SFTP session
```

Each transfer gets its own SFTP channel via `open_sftp_session()`. The explorer uses the main SFTP client. They don't share state.

## Configuration

Stored at `~/.PiSync/config.json`. Supports multiple servers with a default for auto-connect.

Key fields:

- `servers` — dict of server configs (name, ip, user, key, port, remote_base_dir)
- `default_server_id` — auto-connect on launch
- `delete_after_transfer` — move local files to trash after upload
- `file_extensions` — allowed upload extensions
- `skip_patterns` — files to hide in explorer

## Dependencies

- **PySide6** — Qt UI framework
- **Paramiko** — SSH/SFTP
- **Pydantic** — Settings validation
- **send2trash** — Safe file deletion
