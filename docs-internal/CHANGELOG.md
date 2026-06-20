# FileSling — Changelog

> **Last updated:** June 2026 — Version 3.2.1
>
> For planned/future work, see [ROADMAP.md](ROADMAP.md).
> For known issues, see [BUGS.md](BUGS.md).

---

## Unreleased (dev)

### Code Organization Refactor

- [x] Created `src/clients/` package — extracted `DeviceClient`, `ADBClient`, `IOSClient` from models/services
- [x] Moved `server_selection_dialog.py` to `src/views/dialogs/` (all dialogs now in one place)
- [x] Removed dead code: `src/widgets/ui_components.py` (was never imported)
- [x] Services reduced from 11 → 8 (client code extracted to own package)

### Testing Expansion

- [x] Test directory restructured to mirror src/ layout (flat → organized subdirectories)
- [x] 437 unit tests (up from 149) covering:
  - All 3 device clients (ADB, iOS, DeviceClient protocol)
  - All 5 controllers (connection, download, file_operations, transfer, main_window)
  - All 8 services
  - All 6 utility modules (constants, crash_handler, helper, icons, theme, logging)
  - Both models (errors, server_config)
  - Quick Fix dialog, transfer queue widget, download worker

### Architecture Refactor

- [x] Multi-channel SFTP: 3 dedicated channels (explorer UI, metadata, background workers) — eliminates thread contention and UI lag
- [x] Async SSH connect via `ConnectionWorker` (eliminates 30s UI freeze)
- [x] Parallel downloads (up to 3 concurrent, each with own SFTP session)
- [x] Batched SFTP stat calls (duplicate detection: 2s → 40ms)
- [x] Size-limited drag-to-Finder (files >10MB skipped, no freeze)
- [x] Async disk usage worker (tree interactive immediately)
- [x] `MainWindowController` decomposed: 1550 → 345 lines
- [x] Extracted: `ConnectionController`, `DownloadController`, `FileOperationsController`
- [x] Extracted: `FolderPickerDialog`, `BatchRenameDialog`, `VideoConvertManager`, `BookmarksBar`, `InlineRenameEditor`, `SearchWorker`, `DiskUsageWorker`
- [x] `DeviceClient` protocol + `ServerConfig` dataclass
- [x] `RemoteFileService` for centralized connection-lost detection
- [x] Unified type annotations (`Optional[X]` everywhere)
- [x] Keychain: password passed via stdin pipe (not visible in `ps`)
- [x] "No space left on device" detection in uploads
- [x] Connection health check skips ADB/iOS (stateless USB)

### Media Management

- [x] Video conversion: H.264, H.265, VP9 with full settings dialog (codec, preset, CRF, audio, container)
- [x] Convert settings: tooltips, "Restore Defaults" button, all fields documented
- [x] Media Info dialog with two tabs: Info (streams) and Tags (editable metadata)
- [x] Edit Metadata via .nfo sidecar files (instant, Jellyfin-compatible)
- [x] NFO auto-detect: movie vs episodedetails vs musicvideo based on filled fields
- [x] NFO People generation: Director/Artist/Performer auto-create `<actor>` entries
- [x] Quick Fix dialog: container change, timestamp fix, subtitle removal (all no-re-encode)
- [x] Detail panel: side panel showing metadata + stream info on file select
- [x] Detail panel hidden by default, toggle with ⌘I, setting to show at startup
- [x] Activity history shows server display name instead of ID
- [x] "Show All Tags" expandable section with every ffmpeg tag + examples
- [x] "+ Add Tag" for custom metadata fields
- [x] Sort Title tag for Jellyfin sort ordering
- [x] Hide .nfo files option in Settings

### UI

- [x] Pill-style buttons (grey default, blue hover) matching Aethra website design
- [x] Pill-shaped search bar, dropdown, bookmarks
- [x] Toolbar: transparent background, no visible container
- [x] Standard Edit menu (Undo, Cut, Copy, Paste, Select All) — enables Emojis & Symbols
- [x] "Toggle Detail Panel" in View menu (⌘I)
- [x] Back button disabled during directory load (prevents rapid-fire navigation)
- [x] Exit confirmation with "Quit After Jobs Finish" option during active transfers

### Bug Fixes (Production Audit — 18 bugs)

- [x] BUG-1: SFTP session leak in `_retry_download`
- [x] BUG-2: Batch delete doesn't record activity history
- [x] BUG-3: compress_folders silently ignored with rsync
- [x] BUG-4: cancel_active_transfer deadlock
- [x] BUG-5: iOS fallback loads entire file into memory
- [x] BUG-6: SSH connect blocks main thread
- [x] BUG-7: create_folder path validation broken
- [x] BUG-8: ADB streaming items jump around
- [x] BUG-9: Batch rename doesn't record history
- [x] BUG-10: Settings singleton reset stale refs
- [x] BUG-11: Search cancellation race
- [x] BUG-12: measure_latency inaccurate
- [x] BUG-13: ADB shell injection
- [x] BUG-14: \_reveal_in_finder instantiates Settings
- [x] BUG-16: Binary/decimal unit mismatch
- [x] BUG-17: Breadcrumb HTML-escape
- [x] BUG-18: ADB/iOS retry counter
- [x] Detail panel QThread crash: removed background thread, runs synchronously on dedicated channel
- [x] VideoConvertManager QThread crash: added wait() before deleteLater()
- [x] DiskUsageWorker overflow: Signal(int) → Signal(object)
- [x] ffmpeg busy-wait loop: added time.sleep(0.1)
- [x] QSS parse error (duplicate brace broke all styling)
- [x] Font family: removed unsupported -apple-system

### rsync Fast Transfers

- [x] rsync backend for SSH servers — delta sync, only transfers changed bytes
- [x] Auto-pick fastest method — rsync if available, falls back to SFTP
- [x] Per-file progress via `--progress` flag (compatible with openrsync + GNU rsync)
- [x] Transfer method indicator dot in queue (green=rsync, blue=SFTP, orange=ADB)
- [x] Dot updates in real-time on fallback (green → blue when rsync fails)
- [x] Help → Transfer Indicators legend
- [x] Fixed: remote paths with special characters (parentheses, spaces, brackets) properly quoted
- [x] Fixed: folder uploads preserve the folder (strip trailing slash from local paths)

### iPhone / iOS Support

- [x] iOS backend via `pymobiledevice3` (pure Python, AFC protocol over USB)
- [x] Browse iPhone camera roll (DCIM) in the same explorer UI
- [x] Download photos/videos to any attached server
- [x] Device picker with auto-detect in Add Server dialog
- [x] Handles trust prompt (guides user to unlock + tap "Trust This Computer")
- [x] Bundled in .dmg builds (PyInstaller + CI updated)

### ADB over WiFi — Wireless Android Transfers

- [x] "Connect via WiFi" option in the ADB device setup (enter phone's IP address)
- [x] Runs `adb connect <ip>:5555` to establish wireless session
- [x] WiFi-paired devices appear in the device picker automatically
- [x] `pair_wireless()` and `enable_tcpip()` functions for Android 11+ pairing
- [x] Shows "(WiFi)" in connection status when connected wirelessly
- [x] WiFi IP saved per-server so it auto-connects next time

### Multi-Server Quick-Switch

- [x] Server dropdown in the toolbar — switch with one click, no dialog
- [x] Instant disconnect → reconnect on selection change
- [x] "Manage Servers…" at bottom of dropdown

### Remote Video Convert (ffmpeg)

- [x] Right-click video file → "Convert to H.264" (runs ffmpeg on the server via SSH)
- [x] Queued conversions — queue multiple videos, processed one at a time
- [x] Progress shown in Activity panel with ETA
- [x] Replaces original file with H.264 version when done
- [x] Settings: `-preset fast -crf 18` (visually lossless, fast encode)
- [x] Detects if ffmpeg is installed; prompts to install if missing
- [x] Logged in activity history (action: "convert")
- [x] Runs independently from uploads (both can happen simultaneously)

### UI / Theme

- [x] Modern iOS-inspired dark theme (deeper blacks, softer borders, rounder corners)
- [x] Combo box dropdown with proper padding and rounded items
- [x] Slimmer progress bars (6px), thinner scroll bars (8px)
- [x] Tree items with breathing room (margin between rows)
- [x] Move To dialog auto-expands to current directory
- [x] External drag-and-drop always uploads to current directory (no accidental sub-folder targeting)
- [x] Internal drag (rearrange) still highlights folders as drop targets
- [x] Error logs moved from project-root to `~/.FileSling/logs/errors.json`
- [x] Removed status bar — connection shown by green power button instead
- [x] Server dropdown shows just names (no type icons), auto-sizes to fit
- [x] "Manage Servers…" option at bottom of server dropdown (separator + link to dialog)
- [x] Search bar left padding fixed (magnifying glass no longer clipped)
- [x] Transfer queue: each file gets its own row (no more combining into "file1, file2 (+3 more)")
- [x] Transfer queue ordering: active on top → queued → completed at bottom

### Bug Fixes

- [x] Drop target wrong folder — uses highlighted item only, not pixel position
- [x] Internal drag also used wrong target — same fix
- [x] rsync path quoting for parentheses/spaces/brackets in remote paths
- [x] rsync folder uploads extracted contents — fixed trailing slash stripping
- [x] `dragMoveEvent` network call on every pixel — now skips when hovering same item
- [x] Method dot didn't update on fallback — added `method_changed` signal
- [x] Ghost "Uploading" stuck in queue after transfer completes — fallback scan for in-progress items
- [x] rsync compression flag removed (`-z` slowed local network transfers)
- [x] `cancel_active_transfer` double-fires `_cleanup_and_next` — disconnects signal before explicit call

### Deep Audit Fixes (24 bugs found, all resolved)

- [x] DA-01: TransferWorker emits both `error` and `finished` — potential data loss (file deletion after failed transfer). Fixed: only success emits `finished`.
- [x] DA-02: SFTP sessions leaked after every transfer — eventual SSH channel exhaustion. Fixed: sessions stored and explicitly closed.
- [x] DA-03: iOS async device detection broken. Fixed: simplified to `asyncio.run()`.
- [x] DA-06: Fragile `startswith(remote_base_dir)` for remote/local detection. Fixed: uses `sftp is not None`.
- [x] DA-07: Health check reconnect TOCTOU race with download workers. Fixed: also checks `_download_thread`.
- [x] DA-08: Search results navigation confusion. Fixed: clears `_is_searching` on navigate.
- [x] DA-09: Batch rename silent failure on disconnection. Fixed: shows "Connection lost" warning.
- [x] DA-10/DA-14: `os.sep` used for remote POSIX paths. Fixed: hardcoded `"/"`.
- [x] DA-12: `clear_completed` invalidates progress index. Fixed: `indices_changed` signal re-syncs.
- [x] DA-13: `compress_folders_before_transfer` mutates `_total_bytes`. Fixed: local variable, restores original.
- [x] DA-15: `dragMoveEvent` redundant network calls. Fixed: `_dir_cache` dict, cleared on refresh.
- [x] DA-17: rsync transfers cannot be cancelled. Fixed: `cancel_active_transfer()` terminates process.
- [x] DA-18/DA-19: iOS client OOM on large files. Fixed: chunked 1MB streaming.
- [x] DA-20: Partial download files left as truncated data. Fixed: size verification + cleanup.
- [x] DA-21: Health check reconnect conflicts with DirectoryLoader. Fixed: returns early if loader running.
- [x] Batch rename name collisions — appends `_2`, `_3` suffix to resolve.
- [x] Multi-move self-move check — filters out self-moves with batch warning.

---

## v3.1.0 — May 2026

### Bug Fixes

- [x] Download retry doesn't reset `_download_attempts` — fixed: reset to 0
- [x] Drag-to-Finder leaks temp files — fixed: `atexit.register` cleanup
- [x] Health check runs during active transfer — fixed: skips when busy
- [x] `_upload_file` overwrites `remote_dir` variable — fixed: renamed to `target_dir`
- [x] Drop target lands in wrong folder — fixed: coordinate mapping with `mapFrom`
- [x] Rename timer conflicts with drag — fixed: moved to `mouseReleaseEvent`
- [x] "Opened file" log misleading — removed `file_opened` signal entirely

### Code Quality

- [x] Full type annotations across all functions (0 remaining)
- [x] 147 unit tests (services, models, controllers, icons, rsync)
- [x] CI/CD quality workflow (lint + test on every push to dev)
- [x] Removed dead code: `styles.qss`, `DIALOG_RENAME_FAILED`, `shuttle.egg-info/`
- [x] Makefile `format` fixed — removed `autoflake`, uses `black` + `isort` via venv

### UI

- [x] Transfer queue shows destination path (→ /mnt/external/Movies)
- [x] Cancel button styled as "x" (subtle_btn), visible during pending + in-progress
- [x] Extracted icon logic to `src/utils/icons.py`

---

## v3.0.0 — May 2026

### New Features

- [x] Auto-reconnect when connection drops (15s health check)
- [x] Latency indicator in status bar (color-coded green/orange/red)
- [x] File type icons (play for video, volume for audio, etc.)
- [x] File info tooltip on hover (full path, size)
- [x] Batch rename — select multiple files, find/replace in filenames
- [x] Drag remote files to Finder to download
- [x] Resume interrupted uploads (skip fully-uploaded files by size)
- [x] Download retry (up to 3 attempts)
- [x] Notification sound toggle in settings
- [x] Dock badge with pending transfer count
- [x] Drop onto a folder to upload directly into it
- [x] Visual drop target highlight on specific folders
- [x] Export/import settings (JSON)
- [x] Per-server download directory and file extension filters
- [x] Compress folders before transfer (zip → upload)
- [x] Skip unchanged files (size comparison)
- [x] SSH key passphrase support
- [x] Password-based SSH auth as fallback
- [x] macOS Keychain integration for credentials
- [x] Multi-select → Download All, Move All, Delete All
- [x] macOS notifications on transfer complete/fail

### Breaking

- [x] Renamed app from Shuttle to FileSling (config path: `~/.FileSling/`)

---

## v2.4.0 — May 2026

- [x] Transfer history — persistent log of uploads/downloads, searchable
- [x] Activity history service with "already uploaded?" lookup
- [x] Open in Finder after download (reveal option)
- [x] Confirm before deleting files (single and multi-select)
- [x] Clickable breadcrumb path bar
- [x] Transfer history panel (View → Transfer History)
- [x] Remember window size/position between sessions
- [x] Crash handler with one-click GitHub issue reporting
- [x] Bug fixes: right-click rename, ADB path, ADB disk usage

---

## v2.3.0 — May 2026

- [x] Download from server (right-click → Download)
- [x] Download progress in transfer queue
- [x] Duplicate detection for downloads (warns if file exists locally)
- [x] Created `src/workers/` directory (TransferWorker, DownloadWorker)
- [x] Renamed `components/` → `views/`
- [x] Fixed light mode issues (tab bar, icons, status labels)
- [x] Bug fixes: ADB download, ADB delete

---

## v2.2.1 — May 2026

- [x] Fixed auto-connect to device (removed — was unreliable)
- [x] ADB path resolved from Homebrew for .app bundles

---

## v2.2.0 — May 2026

- [x] Dark and light theme support (Follow System option)
- [x] Diagnostics log moved out of main UI → View menu
- [x] Transfer resilience — auto-retry uploads (3 attempts)
- [x] Queue persistence — don't lose uploads on crash
- [x] Per-server bookmarks with default start folder
- [x] Disk space bar updates per browsed directory

---

## v2.1.0 — May 2026

- [x] macOS menu bar (File, Edit, View, Help)
- [x] MainWindow converted to QMainWindow

---

## v2.0.0 — May 2026

- [x] Download files and folders from server
- [x] Transfer history logic
- [x] Server selection UI improvements
- [x] ADB: progress bar, refresh explorer, auto-detect device
- [x] Removed file extension restrictions (transfer any file type)
- [x] CI/CD: `.app` and `.dmg` builds via GitHub Actions
- [x] PyInstaller build script

---

## v1.2.0 — May 2026

- [x] Duplicate file detection (warn before overwriting on remote)

---

## v1.1.0 — May 2026

- [x] Android device support (USB via ADB)
- [x] ADB client that mimics SFTPClient interface
- [x] Device picker with auto-detect
- [x] Keyboard shortcuts (⌘+R, ⌘+N, ⌘+F, ⌘+Delete, etc.)
- [x] Search bar with recursive search
- [x] Connection form widget extracted from settings
- [x] Removed all auto-sync/monitoring code
- [x] Transfer queue with visual panel
- [x] Sortable columns (name, size)

---

## v1.0.0 — May 2026 (Initial)

- [x] SSH/SFTP connection to remote servers
- [x] Remote file explorer with drag-and-drop upload
- [x] Settings with multi-server support
- [x] Splash screen, logging, progress bar
- [x] Disk space indicator
