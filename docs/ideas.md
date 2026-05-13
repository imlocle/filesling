# PiSync — Feature Ideas & Improvements

> A living document of ideas for advancing the application.

---

## 🚀 High Priority (Daily Workflow)

### Transfer Queue Improvements

- [x] Visual queue panel showing pending/in-progress/completed transfers
- [x] Show transfer speed (MB/s) in progress bar
- [x] Show ETA for current transfer
- [x] Retry failed transfers with one click
- [x] Cancel individual queued transfers
- [ ] Drag to reorder queue priority (skipped — rarely needed with short queues)

### Keyboard Shortcuts

- [ ] `⌘+Delete` — Delete selected item
- [ ] `⌘+R` — Refresh explorer
- [ ] `Enter` — Navigate into folder
- [ ] `⌘+↑` — Go back / up one directory
- [ ] `⌘+N` — New folder
- [ ] `⌘+F` — Focus search/filter
- [ ] `Escape` — Deselect all

### Disk Space Indicator

- [x] Visual bar showing used/total space on remote drive
- [x] Show in status bar or below explorer
- [x] Warn when disk is nearly full before starting a transfer

---

## 🎯 Medium Priority (Quality of Life)

### Search & Filter

- [ ] Filter bar above explorer to search current directory
- [ ] Real-time filtering as you type
- [ ] Option to search recursively across all subdirectories

### Download from Server

- [ ] Right-click → "Download" to pull files back to Mac
- [ ] Choose local download destination
- [ ] Download progress in the same queue system

### Transfer History

- [ ] Persist transfer history between sessions (JSON log)
- [ ] Show history panel: file name, date, size, destination
- [ ] "Did I already upload this?" search
- [ ] Clear history option

### Bookmarked Folders

- [ ] Quick-access buttons for frequently used remote directories
- [ ] Add/remove bookmarks from context menu
- [ ] Show as sidebar or dropdown above explorer

### Multi-Select Drag

- [ ] Select multiple files/folders and drag them all at once
- [ ] Show count badge on drag ("3 items")
- [ ] Queue each as a separate transfer or batch them

---

## 💡 Lower Priority (Nice to Have)

### Connection Health

- [ ] Background ping/heartbeat to detect disconnection early
- [ ] Auto-reconnect when connection drops
- [ ] Visual indicator (green/yellow/red) for connection quality
- [ ] Show latency in status bar

### File Previews

- [ ] Show file type icons (video, subtitle, image, etc.)
- [ ] Thumbnail previews for images
- [ ] File info tooltip on hover (full path, modified date, size)

### Theme Support

- [ ] Light mode option
- [ ] Follow system appearance (dark/light)
- [ ] Custom accent color

### Duplicate Detection

- [ ] Warn before uploading a file that already exists on remote
- [ ] Options: skip, overwrite, rename
- [ ] Compare by name + size for quick detection

### Batch Rename

- [ ] Select multiple files → batch rename with pattern
- [ ] Find & replace in filenames
- [ ] Add prefix/suffix to selected items

### Drag from Explorer to Finder

- [ ] Drag a remote file to Finder to download it
- [ ] Reverse of the current upload flow

---

## 🏗 Architecture & Code Quality

### Testing

- [ ] Unit tests for ManualTransferController queue logic
- [ ] Unit tests for PathMapper
- [ ] Integration test with mock SFTP server
- [ ] UI tests for drag-and-drop behavior

### Performance

- [ ] Lazy-load directory sizes (don't block listing)
- [ ] Cache directory listings for back-navigation
- [ ] Parallel SFTP stat calls for faster directory loading

### Error Handling

- [ ] Structured error recovery (auto-reconnect on socket close)
- [ ] User-friendly error messages (not raw exceptions)
- [ ] Error notification badge on status bar

### Code Cleanup

- [ ] Remove unused settings fields (auto_start_monitor, stability_duration, local_watch_dir)
- [ ] Remove dead error classes from errors.py
- [ ] Consolidate path_mapper (only used as fallback now)
- [ ] Remove watchdog from requirements.txt

---

## 🔮 Future Directions

### Rename to Shuttle

- [ ] Rename app from PiSync to Shuttle
- [ ] Update SOFTWARE_NAME constant
- [ ] New app icon
- [ ] Update config directory (~/.PiSync → ~/.shuttle)
- [ ] Migration path for existing configs

### Multi-Server Dashboard

- [ ] Show all servers at a glance with connection status
- [ ] Quick-switch between servers without dialog
- [ ] Transfer to multiple servers simultaneously

### Scheduled Transfers

- [ ] Set up recurring transfers (e.g., every night at 2am)
- [ ] Watch a local folder and auto-upload new files on schedule
- [ ] Notification when scheduled transfer completes

### Plugin System

- [ ] Post-transfer hooks (run a script after upload)
- [ ] Custom file processors (compress before upload, etc.)
- [ ] Notification integrations (Slack, Discord, email)

---

_Last updated: May 2026_
