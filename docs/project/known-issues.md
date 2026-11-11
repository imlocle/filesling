# Known Issues and Audit Notes

> **Last updated:** November 2026: Version 3.8.0

This file contains findings from earlier audits. The unchecked items have not
all been reproduced against the current code, so treat them as candidates for
triage rather than a confirmed list of current defects. New reports should
include the affected platform, connection type, reproduction steps, and logs
with secrets removed.

For planned work, see the [roadmap](roadmap.md). Recent fixes are in the
[changelog](changelog.md).

## Confirmed current issues

No issues have been confirmed in this document against the 3.8.0 codebase.
The older audit findings below are retained as investigation leads.

---

## Needs revalidation: performance reports

- [x] **LAG-1: Detail panel NFO read blocks main thread on every file click**: NFO sidecars are prefetched by `NfoCacheWorker` on the metadata channel. The remaining synchronous ffprobe request is tracked in LAG-3.

- [x] **LAG-2: Detail panel ffprobe shared a channel across threads**: ffprobe now runs synchronously through `RemoteMediaService` on the dedicated metadata channel, so it no longer races with directory loading. The synchronous UI delay is tracked in LAG-3.

- [ ] **LAG-3: Media Info and subtitle probes run synchronously on main thread**: `MediaToolsController` calls `RemoteMediaService` before showing the dialog and before Quick Fix. Slow remote responses can pause the UI. Fix: run probes in a worker and show a loading state.

- [x] **LAG-4: Media Info used an SSH shell command to read NFO files**: NFO reads use the SFTP file API through `RemoteMediaService`; detail panel sidecars are prefetched on the metadata worker.

- [x] ~~**LAG-5: Quick Fix dialog `recv_exit_status()` blocks main thread**~~ ✅ Fixed in 3.4.0: Quick Fix now runs on a background thread with activity panel integration.

- [ ] **LAG-6: `check_ffmpeg_installed()` blocks main thread**: Called from the right-click context menu handler (before showing Convert Video submenu). Does an SSH round-trip. Fix: cache the result per-server after first check.

- [ ] **LAG-7: FolderPickerDialog `listdir_attr` on expand blocks main thread**: Every time you expand a folder in the Move dialog, it does a synchronous SFTP call. Fix: acceptable for now since it's user-initiated, but could be async.

- [ ] **LAG-8: `_is_remote_directory()` does individual `sftp.stat()` calls**: Called during drag operations and context menu building. Each one is a network round-trip. Fix: use the directory cache (`_dir_cache`).

---

## Needs revalidation: threading reports

- [ ] **THREAD-1: Background workers share the background SFTP channel**: `DirectoryLoader`, `DiskUsageWorker`, and `SearchWorker` can use the same `_sftp_background` client from separate threads. Paramiko's `SFTPClient` is not thread-safe. Give each concurrent worker its own channel or serialize SFTP access.

- [ ] **THREAD-2: `_stop_all_threads` on `destroyed` signal may be too late**: Qt's `destroyed` signal fires during destruction when child objects are already being torn down. Calling `quit()` + `wait()` at that point can deadlock if the thread is trying to emit a signal back to the destroyed widget.

- [ ] **THREAD-3: DownloadController lambda connections with `QueuedConnection`**: Lambdas with `QueuedConnection` capture the slot reference but Qt can't guarantee the lambda's captured variables are still alive when the queued call executes (e.g., if the slot was cleaned up between emit and delivery).

---

## Needs revalidation: behavior reports

- [x] **BUG-NEW-2: NFO save doesn't handle ADB/iOS**: SSH-only metadata actions are hidden for ADB/iOS connections, which do not expose the SFTP file API required by the editor.

- [x] **BUG-NEW-3: Video convert manager checked SSH state on ADB**: The manager now rejects ADB/iOS clients before checking SSH transport availability.

- [x] **BUG-NEW-4: `_on_item_selected` fires during `refresh()`**: An empty selection clears the pending detail path, stops the debounce timer, and clears the panel before any detail lookup can run.

- [x] **BUG-NEW-5: `back_btn` not re-enabled if `_load_local()` path is taken**: Local directory loading now explicitly re-enables navigation.

- [x] **BUG-NEW-6: Renaming a file doesn't rename its .nfo sidecar**: Single and batch media renames now move the matching NFO sidecar with the video and roll back the video rename if the sidecar move fails.

---

## ✅ Fixed (September 2026: pre-release audit + reconnect crash)

### Connection reconnect loop & shutdown crash

- [x] **RECONNECT-1: Endless "socket connection lost" loop after a transfer**: `handle_explorer_failure` / `_handle_connection_lost` had no attempt cap, backoff, or shared in-progress flag. A dropped socket → failed refresh → reconnect → refresh fails again → forever. Fixed with a shared guard: `_reconnecting` flag, `_reconnect_attempts` counter capped at `MAX_AUTO_RECONNECT_ATTEMPTS` (3), and `_give_up_reconnect()` that disables auto-reconnect until the user manually reconnects.
- [x] **RECONNECT-2: `QThread: Destroyed while thread is still running` crash (SIGABRT) on exit**: a reconnect worker thread was left blocked in `socket.connect()` at teardown. Two causes fixed: `_connect_ssh` no longer overwrites a running connect thread (was orphaning it), and `shutdown()` now requests interruption, waits 5s, and force-terminates a stuck thread.
- [x] **RECONNECT-3: Synchronous reconnect froze the UI**: `handle_explorer_failure` (SSH) and `_handle_connection_lost` called `connect()`/`reconnect()` on the UI thread, blocking for up to the full retry window. Now routed through a shared `_start_async_connect()` + `ConnectionWorker` on a `QThread`; ADB/iOS stay synchronous (fast local USB) but bounded via `_reconnect_local()`.
- [x] **RECONNECT-4: Reconnect worker not interruptible**: `connect()`/`reconnect()` now take a `should_cancel` hook checked between retries and during an interruptible sliced sleep; `ConnectionWorker` wires `QThread.isInterruptionRequested`.
- [x] **RECONNECT-5: Reconnect success requires a working directory listing**: after SSH reconnect, FileSling rebinds its channels and starts a directory refresh. It counts the reconnect as recovered and resets attempts only when the first remote listing succeeds. A failed listing remains part of the bounded reconnect flow.
- [x] **RECONNECT-6: `_reconnecting` could latch True on terminate**: cleared explicitly at the end of `shutdown()` since a terminated thread never emits its slots.
- [x] **RECONNECT-7: ADB/iOS auto-reconnect was unbounded / off-by-one**: moved to `_reconnect_local()` sharing the same cap and `_give_up_reconnect()` path.

### Pre-release code audit

- [x] **AUDIT-1: `is_connection_lost_error()` operator precedence**: parenthesized the `and`/`or` groups (`remote_file_service.py`); the "no such file"+socket and "eof"+transport checks were dead code.
- [x] **AUDIT-2: Host validator rejected hostnames**: `settings.py` `validate_host` now accepts hostnames (e.g. `nas.local`), not just IP addresses.
- [x] **AUDIT-3: `test_connection()` ignored password auth**: now mirrors `connect()`'s auth-method detection.
- [x] **AUDIT-4: Hardcoded SSH connect timeout**: `connect()` uses the `TIMEOUT_SSH_CONNECT` constant.
- [x] **AUDIT-5: iOS `get()` `NameError` risk**: `total_size` computed in its own try/except before the streaming block (`ios_client.py`).
- [x] **AUDIT-6: Download progress stale/out-of-range queue index**: `_on_progress` guards the index access (`download_controller.py`).
- [x] **AUDIT-7: `_save_global_settings` dropped `max_parallel_transfers`**: now persisted alongside the new API keys.

### Notes from the previous audit that need revalidation

- **THREAD-3 (partial):** The reconnect/connect thread lifecycle is now safe (see RECONNECT-2). The DownloadController `QueuedConnection` lambda concern (below) is separate and still open.
- **Service `reconnect(should_cancel=)` is currently unused**: the controller drives reconnect via `disconnect()` + the worker's `connect()`. Kept as public API; candidate for cleanup.
- **Shared client-state race (low):** `check_health` now also skips while any connect thread runs, reducing the window where the health probe reads client refs the worker is mutating. A full lock around `ssh_client`/`sftp_*` was deferred in the earlier audit. Recheck against the [thread safety roadmap](roadmap.md#priority-4-code-quality).

## ✅ Fixed (Previous Audit)

- [x] BUG-1 through BUG-18, BUG-23, BUG-25, BUG-29 (see git history)
- [x] BUG-NEW-1: `ui_components.py` dead code: deleted, file removed

---

## Previously accepted or deferred

- **BUG-DA-22:** Cancel during retry window: rare race.
- **BUG-DA-16:** Download progress 500ms refresh: by design.
- **BUG-15:** Download retry uses explorer's ADB session: ADB is stateless.
