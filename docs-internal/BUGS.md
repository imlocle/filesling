# Bugs

> Known issues and potential bugs tracked from production audit.
> For fixed bugs, see [CHANGELOG.md](CHANGELOG.md).

---

## Critical (Data Loss / Crash Risk)

- [x] **BUG-1: SFTP session leak in `_retry_download`** — `_retry_download()` opened a new SFTP session but never stored it in `self._download_sftp` for cleanup. Fixed: now assigns to `self._download_sftp` so `_cleanup_download()` can close it.

- [x] **BUG-2: `_delete_multiple` doesn't record activity history** — Batch delete skipped `history.add()` and had no `ConnectionLostError` handling. Fixed: now records each successful deletion in history, stops on connection loss with a user dialog, and tracks failures.

- [x] **BUG-3: `compress_folders_before_transfer` silently ignored with rsync** — When rsync is used, folder compression is bypassed without informing the user. Fixed: now logs an informational message and emits `method_changed("sftp")` so the UI dot reflects the actual method used.

- [x] **BUG-4: `cancel_active_transfer` can deadlock** — `quit()` + `wait(2000)` could hang if TransferWorker is blocked on SFTP `put()`. Fixed: now uses `terminate()` as fallback after 3s timeout with a warning log.

- [x] **BUG-5: `IOSClient.get()` fallback loads entire file into memory** — The `except AttributeError` fallback for older pymobiledevice3 versions uses `get_file_contents()` which can exhaust RAM for large files. Fixed: now logs a warning for files >500MB so users are aware of the limitation.

- [x] **BUG-6: `ConnectionManagerService.connect()` blocks main thread with `sleep(3)`** — Retry loop froze the UI for up to 6 seconds. Fixed: replaced `sleep()` with a non-blocking `QEventLoop` wait that keeps the Qt event loop processing.

---

## Medium (Incorrect Behavior / Edge Cases)

- [x] **BUG-7: `create_folder` path validation is broken** — `is_remote = folder_path.startswith(self.settings.remote_base_dir)` treated all paths as remote when `remote_base_dir` is `/`. Fixed: now uses `self.view.remote_explorer.sftp is not None` like `_move_single` already does.

- [x] **BUG-8: `_on_load_finished` items jump around for ADB streaming** — Batch items arrived while sorting was enabled, causing visual jitter. Fixed: sorting is disabled during async load and re-enabled + applied once all items are loaded.

- [x] **BUG-9: `_handle_batch_rename` doesn't record history** — Batch renames never called `history.add()`. Fixed: now records each successful rename in `ActivityHistoryService` after the loop completes.

- [x] **BUG-10: Settings singleton reset causes stale references** — `Settings._instance = None` invalidated the singleton but other objects held the old reference. Fixed: added `reload_config()` method that updates config in-place; all callers now use that instead of resetting the singleton.

- [x] **BUG-11: Search cancellation race** — `_on_search_cleared` refreshed without cancelling the in-progress SearchWorker, whose results could overwrite the new directory listing. Fixed: now disconnects the search worker's signals before calling `refresh()`.

- [x] **BUG-12: `measure_latency()` is inaccurate** — `transport.send_ignore()` is non-blocking and only measured local buffer write time. Fixed: now uses `sftp_client.stat(".")` which forces a full round-trip.

- [x] **BUG-13: `ADBClient.stat()` shell injection** — Used `f'if [ -d "{path}" ]'` which breaks on paths containing special characters. Fixed: all shell commands in ADBClient now use `shlex.quote()` consistently (`stat`, `listdir`, `listdir_attr_stream`, `rename`, `mkdir`).

- [x] **BUG-14: `_reveal_in_finder` in `TransferItemWidget` instantiates Settings** — Created a full singleton lookup on every click. Fixed: now uses the `destination` field from the `TransferItem` (which is the download dir set at queue time), with Settings as a fallback.

- [x] **BUG-15: Download retry uses explorer's ADB session** — Marked as acceptable. ADB commands are independent subprocess calls (no session state), and the health check already skips while downloads are active. No interleaving risk in practice.

---

## Low (Cosmetic / Minor)

- [ ] **BUG-16: Binary/decimal unit mismatch in speed formatting** — Shows "KB/s" but divides by 1024. Fix: use KiB/s or divide by 1000.

- [ ] **BUG-17: Breadcrumb doesn't HTML-escape path segments** — Folder names with `<`, `>`, `&` break the rich text. Fix: use `html.escape()` on segments.

- [ ] **BUG-18: `handle_connection_failure` counts ADB/iOS failures** — Global retry counter triggers server selection dialog for USB connections. Fix: skip counter increment for non-SSH connection types.

---

## Accepted / Won't Fix

- **BUG-DA-22: Cancel during retry window can hit wrong queue item** — 1-second window after retry re-insert where pending positions may be out of sync. Extremely rare race condition; complexity of fix outweighs the risk.
- **BUG-DA-16: Download progress only updates every 500ms** — Timer-based refresh, by design for performance.
- **BUG-DA-24: Drag-to-Finder freezes UI for large files** — Synchronous download on main thread. Acceptable for small files (photos). Large files should use right-click → Download.
- **BUG-15: Download retry uses explorer's ADB session** — ADB commands are independent subprocesses with no session state. Health check already skips during downloads.

---

## Code Quality Improvements

### Architecture

- [ ] Extract download logic into a `DownloadController` (main_window_controller.py is 1500+ lines)
- [ ] Move SSH connection to a background thread (fully async connect)
- [ ] Add `QMutex` or command queue for ADB (prevents interleaved subprocess calls)

### Performance

- [ ] Cap `_get_local_dir_size` recursion depth or skip (blocks loader thread)
- [ ] Limit drag-to-Finder to 1 file or skip for files >10MB
- [ ] `_handle_batch_rename`: batch stat calls with a single `listdir_attr()`

### Robustness

- [ ] `keychain_service.py`: pass password via stdin pipe instead of CLI args
- [ ] `ffmpeg_service.convert_video`: add timeout / cancellation support
- [ ] Detect "No space left on device" in upload errors for clearer messaging

### Code Style

- [ ] Unify type annotations: pick `str | None` or `Optional[str]`
- [ ] Remove `hasattr` guard patterns (ensure widget init order is deterministic)
- [ ] Make `_install_adb_via_brew` async or replace with a terminal instruction

---

## Feature Ideas

### High Value

- [ ] Parallel downloads (multiple SFTP sessions, semaphore-gated)
- [ ] Transfer speed sparkline graph in queue widget
- [ ] Async drag-to-Finder via `NSFilePromiseProvider`
- [ ] Folder sync / mirror mode (rsync `--delete`)
- [ ] Watch folder auto-upload (`QFileSystemWatcher`)
- [ ] Multi-server split view

### Medium Value

- [ ] File preview panel (thumbnails, text preview)
- [ ] Transfer scheduling (timed queue)
- [ ] Bandwidth limiting (`rsync --bwlimit`, chunked SFTP)
- [ ] Quick Look integration (spacebar preview)
- [ ] SSH jump host / ProxyJump support

### Lower Priority

- [ ] Undo for moves/renames (Cmd+Z with history)
- [ ] Side-by-side diff for overwrite confirmation
- [ ] `UserNotifications` framework instead of osascript
- [ ] Touch Bar support
