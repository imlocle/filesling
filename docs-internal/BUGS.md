# Bugs

> **Last updated:** July 2026 — Version 3.7.1
>
> Bug tracking for FileSling. For roadmap, see [ROADMAP.md](ROADMAP.md).

---

## Open — Performance (UI Lag)

- [ ] **LAG-1: Detail panel NFO read blocks main thread on every file click** — `_load_nfo_metadata()` calls `self._sftp.open()` synchronously. If the NFO doesn't exist, Paramiko does a full SFTP round-trip (~40-100ms) before throwing IOError. Every single file click pays this cost. Fix: move NFO read to the same background probe thread.

- [ ] **LAG-2: Detail panel ffprobe shares SFTP channel with directory loader** — `_ProbeWorker` uses `self._sftp.get_channel().get_transport().open_session()` from a background thread while the main thread or DirectoryLoader may also be using the same SFTP connection. Paramiko SFTP is NOT thread-safe. Fix: probe worker should open its own SSH session.

- [ ] **LAG-3: `_show_media_info` runs ffprobe synchronously on main thread** — When you open the Media Info dialog, it calls `transport.open_session()` + `session.exec_command(ffprobe)` + reads all output in a while loop — all on the main thread. For a file on a slow connection, this freezes the UI for 1-3 seconds. Fix: run in background thread, show dialog with "Loading..." then populate.

- [ ] **LAG-4: `_load_nfo_metadata` in Media Info dialog blocks main thread** — Same pattern: `transport.open_session()` + `exec_command("cat .nfo")` blocks while reading. Fix: already have the SFTP open — use `sftp.open()` (faster) or run async.

- [x] ~~**LAG-5: Quick Fix dialog `recv_exit_status()` blocks main thread**~~ ✅ Fixed in 3.4.0 — Quick Fix now runs on a background thread with activity panel integration.

- [ ] **LAG-6: `check_ffmpeg_installed()` blocks main thread** — Called from the right-click context menu handler (before showing Convert Video submenu). Does an SSH round-trip. Fix: cache the result per-server after first check.

- [ ] **LAG-7: FolderPickerDialog `listdir_attr` on expand blocks main thread** — Every time you expand a folder in the Move dialog, it does a synchronous SFTP call. Fix: acceptable for now since it's user-initiated, but could be async.

- [ ] **LAG-8: `_is_remote_directory()` does individual `sftp.stat()` calls** — Called during drag operations and context menu building. Each one is a network round-trip. Fix: use the directory cache (`_dir_cache`).

---

## Open — Threading (Crash Risk)

- [ ] **THREAD-1: Four threads share the same SFTP connection without synchronization** — `DirectoryLoader`, `DiskUsageWorker`, `_ProbeWorker`, and the main thread all use the same `self.sftp` / `self._sftp` reference. Paramiko's `SFTPClient` is NOT thread-safe. When two threads issue commands simultaneously, the packet sequences get interleaved → corrupted responses → IOError → crash or garbled data. This is the root cause of intermittent lag and the rainbow cursor.

- [ ] **THREAD-2: `_stop_all_threads` on `destroyed` signal may be too late** — Qt's `destroyed` signal fires during destruction when child objects are already being torn down. Calling `quit()` + `wait()` at that point can deadlock if the thread is trying to emit a signal back to the destroyed widget.

- [ ] **THREAD-3: DownloadController lambda connections with `QueuedConnection`** — Lambdas with `QueuedConnection` capture the slot reference but Qt can't guarantee the lambda's captured variables are still alive when the queued call executes (e.g., if the slot was cleaned up between emit and delivery).

---

## Open — Logic Bugs

- [ ] **BUG-NEW-2: NFO save doesn't handle ADB/iOS** — `self.sftp.open(nfo_path, "w")` assumes Paramiko SFTP. `ADBClient` and `IOSClient` don't have an `open()` method that accepts mode "w" and returns a file-like object. This will crash on Android/iOS.

- [ ] **BUG-NEW-3: Video convert manager checks `self.sftp.get_channel()` on ADB** — ADB client's `get_channel()` returns `self` (a stub), which then fails on `get_transport()`. The guard catches it but the error message is misleading.

- [ ] **BUG-NEW-4: `_on_item_selected` fires during `refresh()`** — When `tree_widget.clear()` is called during refresh, it triggers `itemSelectionChanged` → `_on_item_selected` → tries to show detail panel for empty selection → potential stale path access.

- [ ] **BUG-NEW-5: `back_btn` not re-enabled if `_load_local()` path is taken** — When `is_remote` is False, `refresh()` calls `_load_local()` synchronously (no spinner, no async callback). The back button stays disabled forever for local browsing.

- [ ] **BUG-NEW-6: Renaming a file doesn't rename its .nfo sidecar** — If `The Challenge.mp4` has `The Challenge.nfo` and you rename the video, the NFO keeps the old name. Jellyfin won't match it. Fix: on rename, also rename `oldname.nfo` → `newname.nfo` if it exists.

---

## ✅ Fixed (Previous Audit)

- [x] BUG-1 through BUG-18, BUG-23, BUG-25, BUG-29 (see git history)
- [x] BUG-NEW-1: `ui_components.py` dead code — deleted, file removed

---

## Accepted / Won't Fix

- **BUG-DA-22:** Cancel during retry window — rare race.
- **BUG-DA-16:** Download progress 500ms refresh — by design.
- **BUG-15:** Download retry uses explorer's ADB session — ADB is stateless.
