# FileSling — Roadmap

> **Last updated:** June 2026 — Version 3.4.0
>
> Forward-looking only. For completed work, see [CHANGELOG.md](CHANGELOG.md).
> For known issues, see [BUGS.md](BUGS.md).

---

## 🔥 Priority 1: Performance & Stability

### Batch NFO Caching

- [ ] After directory listing completes, read ALL `.nfo` files in that folder in one pass
- [ ] Cache in memory (dict of filename → parsed metadata)
- [ ] Detail panel reads from cache (zero network on file click)
- [ ] Invalidate cache on directory change or NFO save

### rclone Backend for Bulk Transfers

- [ ] Add rclone as a transfer method (parallel streams, 4x faster than rsync for multi-file)
- [ ] Auto-detect if rclone is installed on server
- [ ] Use `--transfers 4` for parallel file copies
- [ ] Fall back to rsync → SFTP if not available

### Sleep/Wake Resilience

- [x] ~~Prevent sleep during active transfers (`caffeinate -i` subprocess)~~ ✅ Done in 3.4.0
- [ ] Detect wake and auto-reconnect (health timer already handles this partially)
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

- [ ] Rename `.nfo` file when video is renamed (BUG-NEW-6)
- [ ] Auto-detect NFO type from folder structure (TV show folders → episodedetails)
- [ ] Import metadata from TMDB/TVDB by filename match

### Video Tools

- [ ] Batch Quick Fix — apply timestamp fix / container change to multiple files
- [ ] Thumbnail extraction (show video first-frame in detail panel)
- [ ] Strip specific audio tracks (choose which to keep, similar to subtitle picker)

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
- [ ] Low priority — only useful if you run those services

---

## Priority 4: Code Quality

### Thread Safety

- [ ] Connection state machine (Disconnected → Connecting → Connected → Reconnecting)
- [ ] `QThread.isInterruptionRequested()` checks in TransferWorker/DownloadWorker loops

### File Organization

- [ ] Move `_ConvertWorker` to `src/workers/convert_worker.py`
- [ ] Move `DirectoryLoader` to `src/workers/directory_loader.py`
- [ ] Move `LoadingSpinner` to `src/widgets/loading_spinner.py`
- [ ] Move `DragDropTreeWidget` + `SortableTreeWidgetItem` to `src/widgets/tree_widgets.py`

### Code Deduplication

- [ ] SSH exec helper in `RemoteFileService` (22 repetitions of open_session pattern)
- [ ] Use `is_connection_lost_error()` everywhere (4 duplicated checks)
- [ ] `TransferQueuePersistenceService` (isolate queue serialization)

### Robustness

- [ ] ffmpeg timeout/cancellation (prevent infinite hang on corrupt files)
- [ ] `hasattr` guards removed (deterministic widget init order)
- [ ] `__all__` exports for each module

---

## Priority 5: macOS Native Polish

- [x] ~~Menu bar icon with drop zone (drag file to quick-send)~~ ✅ Done (menu bar status item with transfer status + Show/Quit)
- [ ] Finder extension (right-click → "Send with FileSling")
- [ ] `UserNotifications` framework (richer notifications, action buttons)
- [ ] Async drag-to-Finder via `NSFilePromiseProvider` (any file size)
- [ ] Quick Look preview (spacebar on remote file)

---

## Priority 6: Power Features

### Integrity & Control

- [ ] Checksum verification (MD5/SHA after transfer)
- [ ] Manual folder compare (diff two folders, pick what to transfer)
- [ ] Bandwidth limiting (`rsync --bwlimit`, chunked SFTP)
- [ ] Dry run mode (preview before committing)

### Post-Transfer Hooks

- [ ] Run script after transfer (per-server, e.g., Plex rescan)
- [ ] Slack/Discord notification on big transfers

### Automation (opt-in, off by default)

- [ ] Watch Folders — auto-upload new files from a local folder
- [ ] Transfer Rules — pattern-based routing
- [ ] Device-Aware Actions — run rules when a device connects

### Other

- [ ] Multi-server split view (two servers side by side)
- [ ] Transfer speed sparkline graph in queue widget
- [ ] Transfer scheduling ("upload at 2am")
- [ ] Undo for moves/renames (Cmd+Z with history)
- [ ] MTP backend (Android without Developer Mode, experimental)

---

_Last updated: June 2026_
