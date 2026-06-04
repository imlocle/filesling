# Bugs

> Known issues and potential bugs. For fixed bugs, see [CHANGELOG.md](CHANGELOG.md).

---

## Medium Priority

- [ ] **Batch rename doesn't handle name collisions** — if find/replace produces two files with the same name, the second rename will fail silently or overwrite the first.
- [ ] **`_handle_move_items` emits moves without checking self-move** — the controller's `_move_single` checks for self-move, but if the user selects a folder and tries to move it into itself via the multi-move dialog, each individual move will show an error dialog (one per item) rather than a single batch error.
- [ ] **`compress_folders_before_transfer` mutates `_total_bytes`** — `_upload_folder_compressed` sets `self._total_bytes = zip_size`, which breaks progress tracking if there are multiple items in the same transfer (the total gets overwritten to just the zip size).
- [ ] **Download worker emits `finished` after `error`** — in `DownloadWorker.run()`, both `self.error.emit(msg)` and `self.finished.emit()` are called on failure. Since both are connected to `self._download_thread.quit`, the thread gets quit twice (harmless but wasteful), and `_complete_download` fires with both an error stored AND a finished signal.

## Low Priority

- [ ] **`_is_remote_directory` called during `dragMoveEvent`** — this does a network `sftp.stat()` call on every mouse move during drag. On high-latency connections this could make dragging feel laggy.
- [ ] **Per-server download directory not used in `_retry_download`** — the retry method uses `self._download_local_dir` (already resolved), so this is fine. But if settings change between retries, the old dir is used. Acceptable behavior.
- [ ] **`set_dock_badge` uses `setBadgeNumber` which requires macOS 13+** — older macOS versions will silently fail (caught by the try/except). Not a crash, just no badge on older systems.
