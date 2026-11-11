# Architecture

> **Last updated:** November 2026: Version 3.7.2

## Overview

FileSling is a desktop file manager for macOS and Windows that sends files to connected devices and servers over SSH/SFTP, Android Debug Bridge, and Apple File Conduit. It is built with Python and PySide6.

For visual diagrams of the system, see [System diagrams](system-diagram.md).

## Project Structure

```
src/
├── clients/
│   ├── adb_client.py                  ADB client (Android via USB/WiFi)
│   ├── device_client.py               DeviceClient Protocol (duck-typed interface)
│   ├── ios_client.py                  iOS AFC client (iPhone/iPad via USB)
│   └── ssh_command_client.py          Shared Paramiko session lifecycle helper
├── config/
│   └── settings.py                    Pydantic config model + singleton
├── controllers/
│   ├── connection_controller.py       SSH/ADB/iOS connection lifecycle
│   ├── destination_profile_controller.py Saved destination profile workflows
│   ├── download_controller.py         Download queue and worker management
│   ├── file_operations_controller.py  Rename, move, delete, create folder
│   ├── media_tools_controller.py      Media dialogs and repair workflows
│   ├── main_window_controller.py      Routes UI events → services
│   └── transfer_controller.py         Upload queue coordination
├── models/
│   ├── activity.py                    Activity history record
│   ├── destination_profile.py         Saved connection and upload destination
│   ├── errors.py                      Custom exception hierarchy
│   ├── media.py                       Media inspection and repair options
│   ├── server_config.py               Typed server settings model
│   └── transfer.py                    Queued upload model
├── repositories/
│   ├── activity_history_repository.py Activity JSON persistence
│   ├── settings_repository.py         Settings JSON persistence
│   └── transfer_queue_repository.py   Crash recovery queue persistence
├── platform/
│   ├── base.py                        No-op stubs (unsupported platforms)
│   ├── macos.py                       macOS: Keychain, notifications, sleep, Finder
│   └── windows.py                     Windows: credential manager, notifications, sleep, Explorer
├── services/
│   ├── activity_history_service.py    Persistent activity log
│   ├── batch_rename_service.py        Collision handling and batch renames
│   ├── connection_manager_service.py  SSH/SFTP lifecycle + health monitoring
│   ├── destination_profile_service.py Validates and persists destination presets
│   ├── ffmpeg_service.py              Remote video conversion via SSH
│   ├── file_deletion_service.py       Safe deletion via send2trash
│   ├── imdb_service.py                IMDb metadata lookup (OMDb primary, TMDB fallback)
│   ├── keychain_service.py            Platform credential storage
│   ├── media_file_service.py          Video rename operations with matching NFO sidecars
│   ├── notification_service.py        Platform notifications and activity badge
│   ├── nfo_metadata_cache_service.py  Current-folder sidecar metadata cache
│   ├── remote_file_service.py         Centralized connection-lost detection
│   ├── remote_media_service.py        Remote ffprobe and ffmpeg operations
│   ├── rclone_service.py              Optional parallel SFTP uploads
│   ├── rsync_service.py              rsync fast-path transfers over SSH
│   ├── sleep_inhibitor_service.py     Prevents macOS sleep during transfers
│   ├── transfer_queue_service.py      Queue serialization and recovery rules
│   └── menu_bar_service.py            macOS menu bar icon + activity dropdown
├── utils/
│   ├── constants.py                   App-wide constants and defaults
│   ├── crash_handler.py               Global exception handler + crash log
│   ├── file_size.py                   Shared file sizing and byte formatting
│   ├── helper.py                      Path helpers
│   ├── icons.py                       File type icon generation (colored, theme-safe)
│   ├── json_file.py                   Atomic JSON read/write helpers
│   ├── logging_signal.py              Qt signal logger + JSON error log
│   ├── media_path.py                  TV metadata hints from media paths
│   └── theme.py                       Theme management
├── views/
│   ├── dialogs/
│   │   ├── batch_metadata_dialog.py   Batch NFO editing for multiple files
│   │   ├── batch_rename_dialog.py     Multi-file find/replace rename
│   │   ├── convert_settings_dialog.py Video conversion settings (codec, CRF, etc.)
│   │   ├── destination_profiles_dialog.py Manage saved upload destinations
│   │   ├── folder_picker_dialog.py    Remote folder browser for Move To
│   │   ├── media_info_dialog.py       Stream info viewer + tag editor
│   │   ├── quick_fix_dialog.py        Container change, timestamps, audio/subtitle selection
│   │   ├── track_selection_widget.py  Shared audio and subtitle track picker
│   │   └── server_selection_dialog.py Server picker on launch / server switch
│   ├── main_window.py                 Main app window (toolbar, explorer, queue)
│   └── settings_window.py             Settings editor (connection, files, appearance)
├── widgets/
│   ├── bookmarks_bar.py               Quick-access folder bookmarks
│   ├── connection_form_widget.py      Reusable SSH/ADB/iOS connection form
│   ├── detail_panel.py                Side panel with metadata + stream info
│   ├── file_explorer_widget.py        Remote file browser (tree, drag-drop, search)
│   ├── inline_rename_editor.py        In-place file rename editor
│   ├── loading_spinner.py             Shared animated loading indicator
│   ├── toggle_switch.py               macOS-style animated toggle switch widget
│   ├── tree_widgets.py                Drag-drop and sortable tree items
│   ├── transfer_queue_widget.py       Visual transfer queue panel
│   └── video_convert_manager.py       Remote ffmpeg conversion manager
└── workers/
    ├── connection_worker.py           Async SSH connection in background
    ├── convert_worker.py              Background remote video conversion
    ├── disk_usage_worker.py           Background disk space calculation
    ├── directory_loader.py            Background local and remote listing
    ├── download_worker.py             Background SFTP/ADB download
    ├── imdb_worker.py                 Background IMDb/OMDb/TMDB metadata fetch
    ├── jellyfin_refresh_worker.py    Background Jellyfin library refresh request
    ├── nfo_cache_worker.py            Background NFO sidecar prefetch and parsing
    ├── quick_fix_worker.py            Background remote ffmpeg repair
    ├── search_worker.py               Background recursive file search
    └── transfer_worker.py             Background SFTP/ADB upload
```

## Layer Responsibilities

- Views and widgets build the interface, render state, and forward user actions.
- Controllers coordinate UI state and worker lifetimes.
- Services own reusable application rules and coordinate clients.
- Repositories read and write persisted documents. Settings, activity history, and
  transfer recovery follow `controller/service → repository` boundaries.
- Clients contain SFTP, ADB, and iOS protocol details. Workers run blocking operations
  away from the UI thread.

The main persistence paths are `Settings → SettingsRepository`,
`ActivityHistoryService → ActivityHistoryRepository`, and
`TransferController → TransferQueueService → TransferQueueRepository`.
`MediaToolsController` coordinates media dialogs and workers, while
`RemoteMediaService` owns remote ffprobe/NFO parsing and ffmpeg command construction.

Destination profiles store a connection ID, remote folder, duplicate policy, and
optional Jellyfin scan override. They reuse the server's credentials and transfer
integrity checks.
The profile service validates records, while the settings repository persists them
inside the existing user configuration file.

## Connection Backends

The app supports three connection types behind the same explorer UI via the `DeviceClient` protocol (`src/clients/device_client.py`):

### SSH (Remote Servers)

- Uses Paramiko `SFTPClient`
- Key-based authentication (with passphrase support)
- Password-based authentication as fallback
- Platform credential store integration for saved passwords and passphrases
- SSH host keys must already be trusted in the system `known_hosts` file
- 3 dedicated SFTP channels for concurrency (explorer, metadata, background)
- Per-transfer SFTP sessions for uploads/downloads (no contention)
- rsync fast path when available (delta transfers, only changed bytes)

### ADB (Android Devices via USB or WiFi)

- Uses `ADBClient` class (`src/clients/adb_client.py`) implementing `DeviceClient` protocol
- Commands: `adb shell ls`, `adb push`, `adb pull`, `adb shell mv/rm/mkdir`
- No persistent connection: each command is a subprocess call
- Requires Developer Mode + USB Debugging on device
- WiFi mode: `adb connect <ip>:5555` for wireless transfers (Android 11+ pairing supported)

### iOS (iPhone/iPad via USB)

- Uses `IOSClient` class (`src/clients/ios_client.py`) implementing `DeviceClient` protocol
- Talks AFC (Apple File Conduit) protocol via `pymobiledevice3`
- Accesses the Media partition: DCIM (camera roll), Downloads, Photos
- No jailbreak required; device must be unlocked and trusted
- Optional dependency is installed in the macOS release build for iOS support

## Data Flow

### Upload (drag-and-drop)

```
Finder drop → FileExplorerWidget.dropEvent()
  → Always targets current_path (no sub-folder highlighting for external drops)
  → MainWindow._handle_remote_drop()
    → Checks for duplicates (sftp.listdir_attr, batch)
    → If duplicates found: shows dialog (overwrite / skip / cancel)
    → Calculates size, adds to TransferQueueWidget
    → TransferController.queue_transfer()
      → Queues transfer
      → TransferQueueService persists active/pending state through TransferQueueRepository
        to ~/.FileSling/transfer_queue.json
      → Acquires sleep inhibition (caffeinate -i)
      → Processes sequentially:
        → SSH key auth? Try rclone first (parallel SFTP transfers)
          → Verify output with SHA-256
          → If rclone fails → try rsync (delta transfer)
          → If rsync fails → fallback to SFTP
        → Opens dedicated SFTP session (or uses ADB/iOS client)
        → TransferWorker runs on QThread (src/workers/)
        → SFTP writes to a temporary remote file and verifies SHA-256 before replace
        → Skips only files whose content hash already matches
        → Optionally compresses folders before upload
        → Emits progress percentage
        → Retries failed uploads up to 3 times
        → On success: deletes local file (if configured), sends notification
        → Updates Dock badge
        → Moves to next queued item
      → Releases sleep inhibition when all jobs complete
```

Selecting a destination profile activates its saved connection and navigates to its
configured folder. Profile selection is blocked while uploads are queued or active.
Duplicate handling can prompt, skip existing names, or proceed with the existing
verified replacement flow.

Remote directory listings collect NFO filenames. After a listing finishes,
`NfoCacheWorker` reads and parses those sidecars on the dedicated metadata channel.
`NfoMetadataCacheService` keeps values for the current folder; the detail panel uses
the cache for NFO fields and reloads it after metadata edits. Stream probing still
uses ffprobe when a file is selected.

### Directory Browsing

```
Navigate/Refresh → FileExplorerWidget.refresh()
  → Shows loading spinner
  → DirectoryLoader runs on QThread
    → SFTP: sftp.listdir_attr() (single call, batch sizes)
    → ADB: adb shell ls -la (streaming)
    → iOS: AFC listdir
  → Results displayed progressively (batch_ready signal)
  → Tree sorted after all batches arrive
  → Disk usage bar updated for current path filesystem
```

### Batch Rename

```
FileExplorerWidget emits batch_rename_requested
  → FileOperationsController shows BatchRenameDialog
  → BatchRenameService resolves collisions and renames the selected paths
  → ActivityHistoryService records each successful rename
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
    → Progress shown in activity panel (percentage only)
    → Replaces original file when done
    → Logged in activity history (action: "convert")
```

### Quick Fix (no re-encoding)

```
Right-click video → "🔧 Quick Fix..."
  → MediaToolsController asks RemoteMediaService to probe subtitle tracks
  → QuickFixDialog: container change, fix timestamps, subtitle selection
  → QuickFixWorker runs the selected command on a background thread
  → Shows "🔧 Fixing" in activity panel
  → ffmpeg -c copy (instant, no quality loss)
  → Logged in activity history on completion
```

Media probing and subtitle inspection currently run synchronously through the explorer's
SSH transport. Quick Fix execution itself runs in `QuickFixWorker`; moving the probes to
their own worker remains a responsiveness improvement.

### Batch Metadata Editing

```
Multi-select videos → right-click → "✏️ Edit Metadata (N videos)"
  → BatchMetadataDialog: shared fields (Artist, Series, Season, Episode #, etc.)
  → Episode # and Sort Title auto-increment per file
  → Reads existing NFOs and merges (per-file titles preserved)
  → Writes .nfo sidecar files for all selected files
```

### IMDb Metadata Fetch

```
MediaInfoDialog (Tags tab) → enter IMDb ID → "🔍 Fetch"
  → IMDbWorker runs on QThread (keeps UI responsive)
    → imdb_service.fetch_metadata(imdb_id, omdb_key, tmdb_key)
      → Normalizes the ID (accepts tt0983514, bare digits, or IMDb URL)
      → Primary: OMDb lookup (urllib GET → JSON)
        → On success: map fields, resolve episode → show name (2nd OMDb call)
        → On "not found" (MetadataNotFoundError): fall through to fallback
        → On auth/network error: stop and report
      → Fallback: TMDB /find?external_source=imdb_id (only if a TMDB key is set)
        → Resolves movie / tv / episode result
        → For episodes: 1 follow-up /tv/{show_id} call for show name + genres
        → Genre IDs resolved to names via cached /genre/{type}/list
  → Fetched fields populate the tag inputs for review
  → User reviews, edits, and clicks Save → writes .nfo sidecar
```

Metadata is fetched via provider APIs (OMDb, TMDB) using the standard-library
`urllib`: no scraping of imdb.com and no extra HTTP dependency in the bundle.

### Auto-Reconnect (bounded, async)

```
Dead socket detected (health timer) OR explorer listdir fails (remote_error)
  → ConnectionController guard check:
      → if _reconnecting or _reconnect_disabled → ignore (no stacking / no loop)
      → if attempts >= MAX_AUTO_RECONNECT_ATTEMPTS → _give_up_reconnect()
  → SSH: _begin_reconnect()
      → disconnect() locally (drop dead session), set _reconnecting = True
      → _start_async_connect() spins ConnectionWorker on a QThread
        → worker.connect(should_cancel=isInterruptionRequested)
          → retry loop with interruptible sliced sleep
      → on success: _on_reconnect_succeeded() (main thread)
              → rebind SFTP channels and refresh the remote directory
              → reset attempts only after the first directory listing succeeds
              → clear reconnect state after that listing completes
      → on failure: _on_reconnect_failed() (main thread)
          → give up if capped, else mark disconnected
  → ADB/iOS: _reconnect_local(): synchronous (fast USB), same cap + give-up
  → shutdown(): requestInterruption → quit → wait(5s) → terminate if stuck
```

## SFTP Channel Architecture

```
ConnectionManagerService opens 3 channels at connect time:

┌─────────────────────────────────────────────────────────────┐
│  SSH Transport (single TCP connection)                       │
├─────────────────────────────────────────────────────────────┤
│  sftp_client    : Main thread: explorer UI operations      │
│  sftp_metadata  : Detail panel: NFO reads, ffprobe         │
│  sftp_background: DirectoryLoader, DiskUsageWorker         │
├─────────────────────────────────────────────────────────────┤
│  Per-transfer sessions (opened/closed per upload/download)  │
│  Per-conversion SSH connection (dedicated, independent)     │
│  Per-Quick-Fix SSH session (background thread)              │
└─────────────────────────────────────────────────────────────┘
```

This eliminates thread contention: Paramiko SFTP is NOT thread-safe, so each concurrent operation needs its own channel.

## Threading

| Thread           | Purpose                                       | SFTP Channel Used  |
| ---------------- | --------------------------------------------- | ------------------ |
| Main (UI)        | Qt event loop, all widget updates             | sftp_client        |
| DirectoryLoader  | Background directory listing (per-navigation) | sftp_background    |
| DetailPanel      | NFO reads, ffprobe (synchronous on channel)   | sftp_metadata      |
| DiskUsageWorker  | Background disk space calculation             | sftp_background    |
| ConnectionWorker | Async SSH connect + reconnect (interruptible) | (none: connects)  |
| TransferWorker   | Background file upload (per-transfer)         | own session        |
| DownloadWorker   | Background file download (per-download)       | own session        |
| SearchWorker     | Background recursive search                   | sftp_background    |
| IMDbWorker       | OMDb/TMDB metadata fetch over HTTP            | (none: HTTP)      |
| JellyfinRefreshWorker | Debounced library refresh request over HTTP | (none: HTTP)      |
| ConvertWorker    | Remote ffmpeg execution                       | own SSH connection |
| QuickFixWorker   | Quick Fix ffmpeg execution                    | own SSH session    |
| HealthTimer      | Connection keepalive + latency (15s interval) | sftp_client        |

### Threading Pattern: Quick Fix

Quick Fix uses the safe `worker.done → thread.quit → thread.finished` pattern:

1. `thread.started` → `worker.run()` (runs on worker thread)
2. Worker stores result in instance attributes, emits `done` signal
3. `worker.done` → `thread.quit` (Qt queues this properly)
4. `thread.finished` → `on_thread_finished()` (guaranteed main thread: safe for UI)
5. Cleanup: `worker.deleteLater()`, `thread.deleteLater()`

This avoids cross-thread violations (no `self.thread().quit()` from within the worker, no UI calls from worker thread).

## Configuration

- Singleton `Settings` class loads from `~/.FileSling/config.json`
- Pydantic `SettingsConfig` model with field validation
- Multi-server support with default server for auto-connect
- `ServerConfig` dataclass (`src/models/server_config.py`) for typed server access
- Server configs store connection type, base directory, per-server download dir, extension filters, bookmarks, and Jellyfin refresh settings
- Passwords, passphrases, and API keys are migrated to the platform credential store
- Config JSON is written atomically with private file and directory permissions
- Global config stores non-secret settings for IMDb metadata lookup
- Transfer history stored in `~/.FileSling/transfer_history.json` (last 200 records)
- Pending and in-progress upload queue recovery stored in `~/.FileSling/transfer_queue.json`
- Error logs stored in `~/.FileSling/logs/errors.json` (last 500 entries)
- Settings can be exported/imported as JSON for sharing between machines; credential-store secrets are excluded

## Main Window UI

- Server quick-switch dropdown in the toolbar (with "Manage Servers…" at bottom)
- Power button turns green when connected (no separate status bar)
- Explorer remains the primary workspace
- Activity panel shows uploads, downloads, conversions, and quick fixes
- Queue ordering: active on top → queued → done (latest first)
- Clickable breadcrumb path bar for quick navigation to parent folders
- Transfer method dot indicator (green=rsync, blue=SFTP, orange=ADB)
- Detail panel (toggle with ⌘I) showing metadata and stream info
- Bookmarks bar for quick folder access
- Diagnostics logs available from `View → Diagnostics Log...`
- Transfer history available from `View → Activity History...`
- Latency indicator shown inline in toolbar (color-coded)
- Platform menu bar with File, Edit, View, Help menus
- Window size and position remembered between sessions
- Downloads can reveal in the platform file manager on completion
- Transfer notifications use platform integrations
- Activity indicator shows pending transfer count where supported
- Close button hides window (app stays alive in menu bar)
- Dock icon click (macOS) or taskbar click (Windows) re-shows the window
- Menu bar or tray icon with live activity status, Open, and Quit
- ⌘Q shows confirmation only if transfers are active, otherwise quits immediately
- Sleep inhibition during active transfers where supported by the platform

## Settings UI

- Tabbed interface: Connection, Files, Appearance
- Connection tab scrollable for smaller monitors
- macOS-style toggle switches (`ToggleSwitch` widget) for all boolean settings
- Theme dropdown applies immediately (live preview)
- "Test Connection" button in footer alongside Cancel/Save
- Per-server settings: download directory, extension filter
- Per-server Jellyfin URL and API key can trigger a debounced library scan after uploads
- Metadata Lookup section (Files tab): OMDb key (primary) + TMDB key (fallback), password-masked

## Theming

- Three modes: Follow System, Light, Dark (configurable in Settings → Appearance)
- Theme changes apply immediately without saving
- Stylesheets: `assets/styles/modern_theme.qss` (dark), `assets/styles/macos_light.qss` (light)
- `src/utils/theme.py` resolves system preference and applies the correct stylesheet
- macOS-style toggle switches with animated knob (green on, grey off)
- Pill-shaped buttons, inputs, dropdowns, bookmarks
- File icons use custom-drawn colored pixmaps (`src/utils/icons.py`)
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
- SFTP replacement files are staged and SHA-256 verified before they become the destination
- A reconnect attempt is counted as recovered only after the first directory listing succeeds
- Failed uploads are retried automatically before being marked failed
- Failed downloads are retried automatically up to 3 times
- Interrupted queued uploads are restored on next launch and restarted
- Connection drops trigger bounded auto-reconnect (15s health check interval):
  - SSH reconnects run on a background `ConnectionWorker` thread (UI never freezes)
  - Capped at `MAX_AUTO_RECONNECT_ATTEMPTS` (3) via a shared guard, then gives up
    until a manual reconnect (prevents endless reconnect/refresh loops)
  - The connect worker is interruptible (`should_cancel` / `isInterruptionRequested`);
    `shutdown()` interrupts, waits, and force-terminates a stuck thread as a last resort
  - ADB/iOS reconnect is synchronous (fast local USB) but equally bounded
- Connection failures show server selection dialog
- Qt accessibility warnings suppressed on macOS Tahoe (`QT_LOGGING_RULES`)

## Dependencies

| Package         | Version | Purpose                      |
| --------------- | ------- | ---------------------------- |
| PySide6         | ≥6.10.0 | Qt UI framework              |
| Paramiko        | ≥3.5.1  | SSH/SFTP                     |
| Pydantic        | ≥2.0.0  | Settings validation          |
| send2trash      | ≥1.8.3  | Safe file deletion           |
| pymobiledevice3 | ≥4.0.0  | iOS device access (optional) |

IMDb metadata lookup (OMDb + TMDB) uses the standard-library `urllib`: no extra HTTP dependency is added.
