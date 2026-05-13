# Shuttle — Feature Ideas & Improvements

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

### Android Device Support (USB via ADB)

- [x] ADB transport backend — `adb push/pull/shell`
- [x] Auto-detect connected devices via `adb devices`
- [x] Browse device filesystem via `adb shell ls`
- [x] Transfer files via `adb push` (upload)
- [x] Same explorer UI, just a different connection backend
- [x] Works with phones, tablets, Quest VR headsets
- [x] Add Server UI supports USB device type selection
- [x] Test Connection works for both SSH and ADB
- [x] Device picker with refresh button

### UI/UX Improvements

- [x] Inline rename (slow-click to edit)
- [x] Multi-select delete
- [x] Folder picker dialog for Move To
- [x] Auto-connect to default server on launch
- [x] "Don't ask again" on exit confirmation
- [x] Tightened button sizes, tooltips, toolbar layout
- [x] Modern dropdown styling with hover highlights
- [x] Input hover/focus border highlights
- [x] Loading spinner for remote directory browsing
- [x] Sortable columns (name, size)

### Code Cleanup

- [x] Removed all auto-sync/monitoring code
- [x] Removed watchdog, pillow, pydantic-settings dependencies
- [x] Removed 16 unused error classes
- [x] Renamed pi_user → username, pi_ip → host (no legacy fields)
- [x] Removed path_mapper, monitor_thread, file_monitor_repository
- [x] Cleaned up log format (concise, no duplicates)
- [x] Extracted ConnectionFormWidget from settings_window
- [x] Centralized hardcoded strings into constants.py
- [x] Removed local watch directory / Transfers folder creation

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

### Multi-Server Dashboard

- [ ] Show all servers at a glance with connection status
- [ ] Quick-switch between servers without dialog

### MTP Support (Android — No Setup)

- [ ] MTP transport backend via libmtp / pymtp
- [ ] No Developer Mode needed — just plug in USB
- [ ] True Android File Transfer replacement
- [ ] Challenge: MTP protocol is flaky on macOS

### Plugin System

- [ ] Post-transfer hooks (run a script after upload)
- [ ] Notification integrations (Slack, Discord)

---

_Last updated: May 2026_
