# Bugs

> A living document of potential bugs.

---

## ✅ Fixed

- [x] Bookmarks should be saved within each individual server because servers might have different directories
- [x] Move the back button to be next to the bookmarks on the left hand side
- [x] Move the breadcrumbs to the bottom of the explorer
- [x] Main Window: Clear button needs to be bigger
- [x] Settings Screen: Margin on Cancel/Save button area
- [x] ADB directory /sdcard is showing as a file and not a directory
- [x] When connected to a device, I can't switch to another server
- [x] ADB delete doesn't work — fixed by using `rm -rf` directly instead of recursive stat+remove
- [x] ADB can't download file — fixed path normalization in `pull()` method
- [x] PyInstaller bundle crashes on launch — `importlib.metadata` not available in frozen app
- [x] Folder names not showing in transfer queue/logs when path has trailing slash
- [x] Duplicate detection triggers on folders (should only check files)
- [x] Upload verification fails for ADB (stat returns 0 bytes before filesystem syncs)
- [x] ADB not found in `.app` bundle — PATH doesn't include Homebrew; fixed with `get_adb_path()` fallback
- [x] Disk space bar not updating when switching to Android device — removed ADB skip in `_get_disk_usage()`
- [x] Light mode: tab bar has dark background strip — fixed with explicit `QTabBar` background color
- [x] Light mode: folder/file icons missing — replaced `QIcon.fromTheme` with `QStyle.standardIcon`
- [x] Light mode: transfer status labels unreadable — replaced hardcoded colors with stylesheet object names
- [x] `ADBStat.filename` property has no setter — changed to regular dataclass field
- [x] Crash when closing window during initial server selection — `closeEvent` accessed `self.controller` before it was assigned
- [x] File icons invisible in dark mode — replaced `QStyle.standardIcon` with custom colored pixmaps

---

---

## 🐛 Potential Bugs (Audit — May 2026)

### High Priority

- [x] **Download retry doesn't reset `_download_attempts` on new download** — fixed: reset to 0 at the start of `_download_paths()`
- [x] **Drag-to-Finder leaks temp files** — fixed: `atexit.register` cleans up temp dirs on app exit
- [x] **Health check runs during active transfer** — fixed: skips health check when `manual_transfer.is_busy()`
- [x] **`_upload_file` overwrites `remote_dir` variable** — fixed: renamed to `target_dir` to avoid shadowing

### Medium Priority

- [ ] **Batch rename doesn't handle name collisions** — if find/replace produces two files with the same name, the second rename will fail silently or overwrite the first.
- [ ] **`_handle_move_items` emits moves without checking self-move** — the controller's `_move_single` checks for self-move, but if the user selects a folder and tries to move it into itself via the multi-move dialog, each individual move will show an error dialog (one per item) rather than a single batch error.
- [ ] **`compress_folders_before_transfer` mutates `_total_bytes`** — `_upload_folder_compressed` sets `self._total_bytes = zip_size`, which breaks progress tracking if there are multiple items in the same transfer (the total gets overwritten to just the zip size).
- [ ] **Download worker emits `finished` after `error`** — in `DownloadWorker.run()`, both `self.error.emit(msg)` and `self.finished.emit()` are called on failure. Since both are connected to `self._download_thread.quit`, the thread gets quit twice (harmless but wasteful), and `_complete_download` fires with both an error stored AND a finished signal.

### Low Priority

- [ ] **`_is_remote_directory` called during `dragMoveEvent`** — this does a network `sftp.stat()` call on every mouse move during drag. On high-latency connections this could make dragging feel laggy.
- [ ] **Per-server download directory not used in `_retry_download`** — the retry method uses `self._download_local_dir` (already resolved), so this is fine. But if settings change between retries, the old dir is used. Acceptable behavior.
- [ ] **`set_dock_badge` uses `setBadgeNumber` which requires macOS 13+** — older macOS versions will silently fail (caught by the try/except). Not a crash, just no badge on older systems.
