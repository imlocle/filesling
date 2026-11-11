# FileSling: Roadmap

> **Last updated:** November 2026: Version 3.8.0
>
> Completed work is listed in the [changelog](changelog.md). Potential issues from older audits are in [known issues](known-issues.md) and need revalidation.

---

## Completed in 3.7.2

- [x] Stage SFTP uploads and verify SHA-256 before replacing a destination.
- [x] Compare remote content before skipping an existing upload; use checksum matching with rsync.
- [x] Include hidden files in folder uploads.
- [x] Request an optional Jellyfin library refresh after the upload queue finishes.
- [x] Verify SSH host keys and use the configured SSH port.
- [x] Store credentials through the platform credential store and write configuration atomically.
- [x] Count reconnection as recovered only after the first remote directory listing succeeds.

## 🔥 Priority 1: Performance & Stability

### Batch NFO Caching

- [x] After directory listing completes, read `.nfo` sidecars in a background worker
- [x] Cache parsed metadata in memory for the currently browsed folder
- [x] Detail panel reuses cached sidecar values instead of reading NFO files on selection
- [x] Rebuild the cache on folder refresh and after metadata saves

### rclone Backend for Bulk Transfers

- [x] Add rclone as an optional SFTP transfer method when available locally
- [x] Auto-detect the local rclone executable and use verified SSH key settings
- [x] Use `--transfers 4` for parallel files within each uploaded folder
- [x] Fall back to rsync, then SFTP, when rclone cannot complete a transfer

### Sleep/Wake Resilience

- [x] ~~Prevent sleep during active transfers (`caffeinate -i` subprocess)~~ ✅ Done in 3.4.0
- [x] ~~Bounded async auto-reconnect that won't loop or freeze the UI~~ ✅ Done (dev): health timer detects a dead socket and reconnects off the UI thread, capped at 3 attempts
- [ ] Detect explicit wake events (beyond the 15s health poll) and reconnect immediately
- [ ] Auto-restart failed-in-progress transfers after reconnect
- [x] ~~Release sleep lock when queue is empty~~ ✅ Done in 3.4.0

### Persistent Remote Conversions

- [ ] Launch ffmpeg with `nohup` so conversions survive app exit/crash
- [ ] Write progress to temp file on server, poll from FileSling
- [ ] On reconnect, detect running conversions and resume progress display
- [ ] Clean up temp files after completion

---

## Priority 2: Media Management

### NFO Improvements

- [x] Rename `.nfo` sidecars with matching video files, including batch renames
- [x] Infer TV show, season, episode, and title from common folder and filename patterns
- [ ] Import metadata from TMDB/TVDB by filename match

### Video Tools

- [x] Batch Quick Fix: apply timestamp fix / container change to multiple files
- [ ] Thumbnail extraction (show video first-frame in detail panel)
- [x] Select which audio tracks to keep, alongside subtitle selection

---

## Priority 3: New Backends

### NFS Mount Mode (optional, power users)

- [ ] Connect to Pi via NFS for instant directory browsing (no SFTP overhead)
- [ ] Directory listings are local filesystem operations (sub-millisecond)
- [ ] Falls back to SFTP for operations NFS can't do (remote commands)
- [ ] Requires NFS server setup on Pi (provide setup guide)

### SMB/CIFS

- [ ] Windows PCs and NAS devices (Synology, QNAP) via `smbprotocol`
- [ ] Username/password auth
- [ ] Auto-discover shares on local network

### S3

- [ ] AWS bucket transfers via `boto3`
- [ ] Auth from `~/.aws/credentials` or stored in Keychain
- [ ] Multipart upload/download for large files

### Google Drive

- [ ] OAuth2, resumable transfers
- [ ] Browse Drive folders in the same explorer

### WebDAV

- [ ] Nextcloud, Synology, Box
- [ ] Low priority: only useful if you run those services

---

## Priority 4: Code Quality

### Thread Safety

- [ ] Connection state machine (Disconnected → Connecting → Connected → Reconnecting): partially in place via the reconnect guard flags; not yet a formal state machine
- [x] ~~Interruptible connect worker~~ ✅ Done (dev): `ConnectionWorker`/`connect()` honor `QThread.isInterruptionRequested` via a `should_cancel` hook
- [ ] `QThread.isInterruptionRequested()` checks in TransferWorker/DownloadWorker loops (still unbounded blocking there)
- [ ] Lock (or single-thread confinement) around `ssh_client`/`sftp_*` mutation in `ConnectionManagerService` (health probe vs connect worker)

### File Organization

- [x] Move conversion, directory loading, and quick fix workers into `src/workers/`
- [x] Move loading spinner into `src/widgets/loading_spinner.py`
- [x] Move explorer tree classes into `src/widgets/tree_widgets.py`
- [x] Move media dialogs and workflow coordination into `MediaToolsController`
- [ ] Continue splitting `FileExplorerWidget` by view responsibility

### Code Deduplication

- [x] Route remote media probes and NFO access through `RemoteMediaService`
- [x] Centralize Paramiko command session open/close behavior in `open_ssh_session`
- [ ] Apply `is_connection_lost_error()` consistently across SFTP operations
- [x] Shared atomic JSON and file-size utilities
- [x] Transfer queue persistence and recovery service/repository
- [x] Share one activity-history service across the main window workflows

### Robustness

- [ ] ffmpeg timeout/cancellation (prevent infinite hang on corrupt files)
- [ ] `hasattr` guards removed (deterministic widget init order)
- [ ] `__all__` exports for each module

---

## Priority 5: macOS Native Polish

- [x] ~~Menu bar icon with drop zone (drag file to quick-send)~~ ✅ Done (menu bar icon with live activity status, Open/Quit dropdown)
- [ ] Finder extension (right-click → "Send with FileSling")
- [ ] `UserNotifications` framework (richer notifications, action buttons)
- [ ] Async drag-to-Finder via `NSFilePromiseProvider` (any file size)
- [ ] Quick Look preview (spacebar on remote file)

---

## Priority 6: Power Features

### Integrity & Control

- [x] ~~SFTP SHA-256 verification and rsync checksum matching~~ Completed in 3.7.2
- [ ] Manual folder compare (diff two folders, pick what to transfer)
- [ ] Bandwidth limiting (`rsync --bwlimit`, chunked SFTP)
- [ ] Dry run mode (preview before committing)

### Post-Transfer Hooks

- [x] ~~Jellyfin library refresh after upload batches~~ Completed in 3.7.2
- [ ] General per-server script hook after transfer
- [ ] Slack/Discord notification on big transfers

### Automation (opt-in, off by default)

- [ ] Watch Folders: auto-upload new files from a local folder
- [ ] Transfer Rules: pattern-based routing
- [ ] Device-Aware Actions: run rules when a device connects

### Other

- [ ] Multi-server split view (two servers side by side)
- [ ] Transfer speed sparkline graph in queue widget
- [ ] Transfer scheduling ("upload at 2am")
- [ ] Undo for moves/renames (Cmd+Z with history)
- [ ] MTP backend (Android without Developer Mode, experimental)

---

_Last updated: November 2026_
