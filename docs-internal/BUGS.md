# Bugs & Roadmap

> Known issues, improvements, and feature ideas — ordered by impact.
> For fixed bugs, see [CHANGELOG.md](CHANGELOG.md).

---

## ✅ Fixed — Critical

- [x] **BUG-1: SFTP session leak in `_retry_download`** — Fixed: assigns to `self._download_sftp` for cleanup.
- [x] **BUG-2: `_delete_multiple` doesn't record activity history** — Fixed: records deletions, handles `ConnectionLostError`.
- [x] **BUG-3: `compress_folders_before_transfer` silently ignored with rsync** — Fixed: logs and emits `method_changed`.
- [x] **BUG-4: `cancel_active_transfer` can deadlock** — Fixed: `terminate()` fallback after 3s.
- [x] **BUG-5: `IOSClient.get()` fallback loads entire file into memory** — Fixed: warns for files >500MB.
- [x] **BUG-6: `ConnectionManagerService.connect()` blocks main thread** — Fixed: non-blocking `QEventLoop` wait.

## ✅ Fixed — Medium

- [x] **BUG-7: `create_folder` path validation broken** — Fixed: uses `sftp is not None` check.
- [x] **BUG-8: ADB streaming items jump around** — Fixed: disable sorting during load.
- [x] **BUG-9: Batch rename doesn't record history** — Fixed: records each rename.
- [x] **BUG-10: Settings singleton reset causes stale refs** — Fixed: `reload_config()` in-place.
- [x] **BUG-11: Search cancellation race** — Fixed: disconnect signals before refresh.
- [x] **BUG-12: `measure_latency()` inaccurate** — Fixed: uses `sftp.stat(".")` round-trip.
- [x] **BUG-13: ADB shell injection** — Fixed: `shlex.quote()` everywhere.
- [x] **BUG-14: `_reveal_in_finder` instantiates Settings** — Fixed: uses `item.destination`.
- [x] **BUG-15: Download retry uses explorer session** — Accepted: ADB is stateless.

---

## 🔥 Next Up — Prioritized by Impact

> Do these in order. Each one delivers noticeable value to either the user or the developer experience.

### Tier 1: User-Facing Speed (do these first)

| #   | Item                                             | Why it matters                                                                                       | Effort | Status               |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ------ | -------------------- |
| 1   | **`ConnectionWorker` — fully async SSH connect** | Eliminates the biggest UX freeze (up to 30s on unreachable hosts). BUG-6 fix was a stopgap.          | Medium | ✅ Done              |
| 2   | **Parallel downloads**                           | 2-3x download throughput for batches. Requires `DownloadController` extraction first (Tier 3 #12).   | Medium | ⏳ Blocked on Tier 3 |
| 3   | **Batch SFTP stat calls**                        | Duplicate detection uses single `listdir_attr()` + local filter instead of N round-trips. 2s → 40ms. | Small  | ✅ Done              |
| 4   | **Async drag-to-Finder**                         | Eliminates UI freeze for any file size. Use `NSFilePromiseProvider` via pyobjc.                      | Large  | Pending              |
| 5   | **`DiskUsageWorker`**                            | Tree becomes interactive immediately instead of waiting 1-3s for `df` to finish.                     | Small  | ✅ Done              |

### Tier 2: Remaining Bugs (quick wins)

| #   | Item                                     | Why it matters                                                                       | Effort | Status  |
| --- | ---------------------------------------- | ------------------------------------------------------------------------------------ | ------ | ------- |
| 6   | **BUG-17: Breadcrumb HTML-escape**       | Folders with `<>&` in names break the path bar. One-line `html.escape()` fix.        | Tiny   | ✅ Done |
| 7   | **BUG-18: ADB/iOS retry counter**        | USB failures trigger irrelevant "switch server?" dialog. Skip increment for non-SSH. | Tiny   | ✅ Done |
| 8   | **BUG-16: Binary/decimal unit mismatch** | Shows "KB/s" but divides by 1024. Now uses decimal (÷1000) to match labels.          | Tiny   | ✅ Done |

### Tier 3: Architecture (makes everything after this easier)

| #   | Item                                   | Why it matters                                                                                                                       | Effort |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| 9   | **`DeviceClient` protocol**            | Formalizes the SSH/ADB/iOS duck-typing. Enables `isinstance()`, IDE autocomplete, and new backends. Foundation for everything below. | Small  |
| 10  | **`ServerConfig` dataclass**           | Replaces `dict.get("key", default)` scattered everywhere with typed model. Prevents typo bugs, enables validation.                   | Small  |
| 11  | **Extract `ConnectionController`**     | ~350 lines out of main controller. Owns connect/disconnect/health/reconnect lifecycle.                                               | Medium |
| 12  | **Extract `DownloadController`**       | ~200 lines. Mirrors `ManualTransferController` pattern. Enables parallel downloads cleanly.                                          | Medium |
| 13  | **Extract `FileOperationsController`** | ~300 lines. CRUD ops (delete/rename/move/mkdir) in one place.                                                                        | Medium |
| 14  | **`RemoteFileService`**                | Centralizes connection-lost detection. Every caller currently does its own `IOError("Socket is closed")` check.                      | Medium |

After items 11-13, `MainWindowController` drops from ~1500 → ~600 lines.

### Tier 4: Widget Decomposition (FileExplorerWidget is 2500 lines)

| #   | Item                              | Why it matters                                                                                     | Effort |
| --- | --------------------------------- | -------------------------------------------------------------------------------------------------- | ------ |
| 15  | **Extract `FolderPickerDialog`**  | Self-contained dialog used by move operations. ~150 lines, no shared state. Easy first extraction. | Small  |
| 16  | **Extract `BatchRenameDialog`**   | Self-contained dialog. ~100 lines.                                                                 | Small  |
| 17  | **Extract `VideoConvertManager`** | Conversion queue + progress. ~120 lines, clean boundary.                                           | Small  |
| 18  | **Extract `SearchWidget`**        | Search bar + SearchWorker + results display. ~200 lines.                                           | Medium |
| 19  | **Extract `BookmarksBar`**        | Bookmark buttons + toggle logic. ~80 lines.                                                        | Small  |
| 20  | **Extract `InlineRenameEditor`**  | Rename overlay widget. ~100 lines.                                                                 | Small  |

After all extractions, `FileExplorerWidget` becomes ~800 lines focused on tree display + navigation + drag-drop.

### Tier 5: Robustness & Code Quality

| #   | Item                                               | Why it matters                                                                                                            | Effort           |
| --- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------- | ---- |
| 21  | **Connection state machine**                       | Prevents race conditions (e.g., reconnect during transfer). States: Disconnected → Connecting → Connected → Reconnecting. | Medium           |
| 22  | **`QThread.isInterruptionRequested()` in workers** | Cleaner cancellation — workers check a flag between chunks instead of relying on thread termination.                      | Small            |
| 23  | **Keychain: stdin pipe instead of CLI args**       | Password briefly visible in `ps` output. Use `Popen` stdin instead.                                                       | Small            |
| 24  | **ffmpeg timeout/cancellation**                    | Infinite hang on corrupt files. Add session timeout or polling for cancel flag.                                           | Medium           |
| 25  | **"No space left on device" detection**            | Currently shows opaque IOError. Parse the error message for a clear user-facing dialog.                                   | Small            |
| 26  | **`TransferQueuePersistenceService`**              | Isolates queue serialization. Makes format changes (e.g., SQLite) trivial.                                                | Small            |
| 27  | **`DiskUsageService`**                             | Normalizes df across SSH/ADB/iOS. Currently inline in the widget.                                                         | Small            |
| 28  | **Move `SearchWorker` to `workers/`**              | Inline class definition inside a method is hard to test and find.                                                         | Tiny             |
| 29  | **Unify type annotations**                         | Mix of `Optional[str]` and `str                                                                                           | None`. Pick one. | Tiny |
| 30  | **Remove `hasattr` guards**                        | Ensure widget init order is deterministic so guards are unnecessary.                                                      | Small            |
| 31  | **Add `__all__` exports**                          | Clean public API for each module.                                                                                         | Tiny             |

---

## Accepted / Won't Fix

- **BUG-DA-22: Cancel during retry window** — Extremely rare race; complexity outweighs risk.
- **BUG-DA-16: Download progress 500ms refresh** — By design for performance.
- **BUG-DA-24: Drag-to-Finder freezes for large files** — Acceptable for small files. Superseded by Tier 1 item #4 (async drag).
- **BUG-15: Download retry uses explorer's ADB session** — ADB is stateless subprocess calls.

---

## Feature Ideas (after quality work is done)

### High Value

- [ ] Parallel downloads (covered in Tier 1 #2)
- [ ] Transfer speed sparkline graph in queue widget
- [ ] Async drag-to-Finder (covered in Tier 1 #4)
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
