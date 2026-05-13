# PiSync — Feature Ideas & Improvements

> A living document of ideas for advancing the application.

---

## ✅ Completed

### Transfer Queue

- [x] Visual queue panel showing pending/in-progress/completed transfers
- [x] Show transfer speed (MB/s) and ETA
- [x] Retry failed transfers with one click
- [x] Cancel individual queued transfers

### Keyboard Shortcuts

- [x] `⌘+Delete` — Delete selected items
- [x] `⌘+R` — Refresh explorer
- [x] `Enter` — Navigate into folder / execute search
- [x] `⌘+↑` — Go back / up one directory
- [x] `⌘+N` — New folder
- [x] `⌘+F` — Focus search bar
- [x] `Escape` — Clear search / deselect all

### Disk Space Indicator

- [x] Visual bar below explorer showing used/total
- [x] Color-coded: blue → orange (75%) → red (90%)

### Search & Filter

- [x] Always-visible search bar above explorer
- [x] Recursive search across subdirectories (3 levels deep)
- [x] Background thread search with loading spinner
- [x] Enter to search, Escape to clear

### Code Cleanup (Done)

- [x] Removed all auto-sync/monitoring code
- [x] Removed watchdog, pillow, pydantic-settings dependencies
- [x] Removed 16 unused error classes
- [x] Removed legacy settings fields (pi_user → username, pi_ip → host)
- [x] Removed path_mapper, monitor_thread, file_monitor_repository
- [x] Cleaned up log format (concise, no duplicates)

---

## 🚀 Next Up

### Download from Server

- [ ] Right-click → "Download" to pull files back to Mac
- [ ] Choose local download destination
- [ ] Download progress in the same queue system

### Transfer History

- [ ] Persist transfer history between sessions (JSON log)
- [ ] Show history panel: file name, date, size, destination
- [ ] "Did I already upload this?" search

### Bookmarked Folders

- [ ] Quick-access buttons for frequently used remote directories
- [ ] Add/remove bookmarks from context menu
- [ ] Show as sidebar or dropdown above explorer

### Duplicate Detection

- [ ] Warn before uploading a file that already exists on remote
- [ ] Options: skip, overwrite, rename
- [ ] Compare by name + size for quick detection

---

## 💡 Nice to Have

### Connection Health

- [ ] Auto-reconnect when connection drops
- [ ] Visual indicator for connection quality
- [ ] Show latency in status bar

### File Previews

- [ ] Show file type icons (video, subtitle, image, etc.)
- [ ] File info tooltip on hover (full path, modified date, size)

### Theme Support

- [ ] Light mode option
- [ ] Follow system appearance (dark/light)

### Batch Rename

- [ ] Select multiple files → batch rename with pattern
- [ ] Find & replace in filenames

### Drag from Explorer to Finder

- [ ] Drag a remote file to Finder to download it

---

## 🔮 Future Directions

### Rename to Shuttle

- [ ] Rename app from PiSync to Shuttle
- [ ] Update SOFTWARE_NAME constant
- [ ] New app icon
- [ ] Update config directory (~/.PiSync → ~/.shuttle)

### Multi-Server Dashboard

- [ ] Show all servers at a glance with connection status
- [ ] Quick-switch between servers without dialog

### Android Device Support (USB)

Replace Android File Transfer with something that actually works on modern macOS.

**Option A: ADB (Developer Mode required)**

- [ ] ADB transport backend — `adb push/pull/shell`
- [ ] Auto-detect connected devices via `adb devices`
- [ ] Browse device filesystem via `adb shell ls`
- [ ] Transfer files via `adb push` (upload) / `adb pull` (download)
- [ ] Same explorer UI, just a different connection backend
- [ ] Works with phones, tablets, Quest VR headsets
- [ ] More reliable and faster than MTP
- [ ] Tradeoff: user must enable Developer Mode + USB Debugging once

**Option B: MTP (Plug-and-play, no setup)**

- [ ] MTP transport backend via libmtp / pymtp
- [ ] No Developer Mode needed — just plug in USB
- [ ] True Android File Transfer replacement
- [ ] Challenge: MTP protocol is flaky on macOS (disconnects, slow)
- [ ] Would need robust retry/error handling

**Architecture:**

- [ ] Abstract the connection layer (SSH, ADB, MTP) behind a common interface
- [ ] Explorer widget doesn't care what backend is used
- [ ] Server selection dialog shows device type (SSH server vs USB device)

### Plugin System

- [ ] Post-transfer hooks (run a script after upload)
- [ ] Notification integrations (Slack, Discord)

---

_Last updated: May 2026_
