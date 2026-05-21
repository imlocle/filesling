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
- [x] Updates for the current browsed filesystem, including mounted drives

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

### Duplicate Detection

- [x] Warn before uploading a file that already exists on remote
- [x] Options: skip, overwrite, cancel
- [x] Compare by name (stat check on remote)

### Download from Server

- [x] Right-click → "Download" to pull files back to Mac
- [x] Configurable download directory in Settings → Files tab
- [x] Download progress in the same queue system
- [x] Duplicate detection (warns if file already exists locally)
- [x] Downloads show as "⬇️ Downloading" in transfer queue

### Transfer History

- [x] Persist transfer history between sessions (JSON log)
- [x] Records uploads and downloads with filename, size, timestamp, server
- [x] Search history by filename
- [x] "Did I already upload this?" lookup

### Bookmarked Folders

- [x] Right-click folder → "⭐ Bookmark" to save
- [x] Bookmark bar above explorer with quick-access buttons
- [x] Click bookmark to navigate directly
- [x] Remove bookmark via right-click → "⭐ Remove Bookmark"
- [x] Persists per server between sessions
- [x] Set a bookmarked folder as the default start folder for that server

### Transfer Resilience

- [x] Retry failed uploads automatically (3 attempts)
- [x] Queue persistence — don't lose queued upload items if app crashes

### UI/Diagnostics

- [x] Removed duplicate explorer title
- [x] Made Transfers panel larger and expandable
- [x] Hid diagnostics logs from the main screen
- [x] Diagnostics log available from View menu
- [x] Added macOS-style light/dark themes with a Follow System option
- [x] Reduced custom dark widget styling so themes can apply consistently

### ADB (Android) Fixes

- [x] Explorer refreshes after upload completes
- [x] File sizes showing correctly (single-call listdir_attr)
- [x] Disk usage bar works for Android devices
- [x] All file operations (create, rename, delete, move, upload) work with ADB
- [x] No crash when navigating away while a large folder is loading
- [x] Auto-connect to USB device when plugged in (prioritizes over default server)
- [x] Progressive/chunked directory loading for large folders (streams items in batches of 50)

### Theme Support

- [x] Light mode option
- [x] Follow system appearance (dark/light)

---

## 🚀 Next Up

### Quality of Life

- [ ] Show transfer history panel (View menu → Transfer History)
- [ ] "Open in Finder" for downloaded files (click completed transfer → reveal in Finder)
- [ ] Breadcrumb path bar should be clickable (navigate to any parent folder)
- [ ] Remember window size/position between sessions
- [ ] Confirm before deleting multiple files (currently deletes immediately)

---

## 💡 Nice to Have

### Connection Health

- [ ] Auto-reconnect when connection drops
- [ ] Visual indicator for connection quality
- [ ] Show latency in status bar

### File Previews

- [ ] Show file type icons (video, subtitle, image, etc.)
- [ ] File info tooltip on hover (full path, modified date, size)

### Batch Rename

- [ ] Select multiple files → batch rename with pattern
- [ ] Find & replace in filenames

### Drag from Explorer to Finder

- [ ] Drag a remote file to Finder to download it

### Multi-Select Transfers

- [ ] Select multiple files → right-click → Download all
- [ ] Select multiple files → right-click → Move all to folder
- [ ] Shift+click range selection for bulk operations

### Transfer Resilience

- [ ] Resume interrupted transfers (track partial uploads)
- [ ] Extend retry/persistence behavior to downloads

### Notifications

- [ ] macOS notification when transfer completes (especially large files)
- [ ] Sound on completion (optional, toggle in settings)
- [ ] Badge app icon with pending transfer count

### Drag-and-Drop Improvements

- [ ] Drop onto a folder in the tree to upload directly into it
- [ ] Visual drop target highlight on specific folders
- [ ] Drop multiple folders — preserve structure

### Settings & Config

- [ ] Export/import settings (share config between machines)
- [ ] Per-server file extension filters
- [ ] Per-server download directory

### Performance

- [ ] Parallel uploads (configurable: 1-4 simultaneous transfers)
- [ ] Compress before transfer option (zip folder → upload → extract)
- [ ] Skip unchanged files (compare modified date + size)

### Security

- [ ] SSH key passphrase support (currently only unencrypted keys)
- [ ] Password-based SSH auth as fallback
- [ ] Remember last N connected servers securely in keychain

---

## 🔮 Future Directions

> Shuttle's architecture (backend abstraction where ADBClient mimics SFTPClient) means
> new connection types can be added without changing the explorer UI. Each backend just
> needs: listdir, stat, put, get, rename, mkdir, remove.

### Workflow Automation (Rules Engine)

> The next major feature direction. Deterministic, reliable, no AI needed.

- [ ] **Watch Folders** — monitor a local folder, auto-upload new files to a destination
  - Example: `~/Movies/OBS/` → auto-upload to NAS `/recordings/`
- [ ] **Transfer Rules** — pattern-based routing
  - Example: `*.mp4` → always send to Android tablet `"/storage/emulated/0/Movies/`
  - Example: `*.apk` → always send to test device
- [ ] **Device-Aware Actions** — when a specific device connects, run a rule
  - Example: when Pixel connects → sync latest screenshots
- [ ] **Smart Destinations** — remember last upload location per file type
  - "You sent .blend files to /projects/ last 12 times — use that?"
- [ ] **Auto-Rename Templates** — rename on transfer using patterns
  - Example: `IMG_*.jpg` → `{date}_{counter}.jpg` using EXIF data
- [ ] **Rules UI** — simple list of if/then rules in Settings

### AI-Assisted Suggestions (Phase 3 — Later)

> Built on top of TransferHistoryService data. Minimal, assistive, deterministic.

- [ ] Suggest rules based on repeated transfer patterns
  - "You've uploaded OBS recordings to Media NAS 12 times. Create a rule?"
- [ ] Suggest destinations based on file type + history
- [ ] Flag potential duplicates using filename similarity
- [ ] NOT a chatbot, NOT semantic search, NOT an assistant sidebar

### Additional Backends

- [ ] **SMB/CIFS** — Connect to Windows PCs and NAS devices (pysmb / smbprotocol)
- [ ] **WebDAV** — Connect to Nextcloud, Synology, Box, etc.
- [ ] **S3** — Browse and transfer to AWS S3 buckets (boto3)
- [ ] **MTP** — Android without Developer Mode (libmtp, flaky on macOS)
- [ ] **SCP/rsync** — Faster bulk transfers for SSH servers

### Multi-Server Dashboard

- [ ] Show all servers at a glance with connection status
- [ ] Quick-switch between servers without dialog
- [ ] Split-pane: two servers side by side for server-to-server transfers

### Plugin System

- [ ] Post-transfer hooks (run a script after upload)
- [ ] Notification integrations (Slack, Discord)
- [ ] Custom transfer rules (auto-sort by file type on remote)

### macOS Native Polish

- [ ] Menu bar icon with quick-transfer drop zone
- [ ] Finder extension (right-click → "Send with Shuttle")
- [ ] Spotlight integration for transfer history search
- [ ] Touch Bar support (if applicable)
- [ ] Native macOS share sheet integration

### Positioning

Shuttle isn't just "Android File Transfer replacement" — it's a native macOS transfer
hub for devices and servers. The unified backend abstraction means it can grow into:

- Dev/homelab tool (SSH servers, Docker, Raspberry Pi)
- Creator workflow (camera → phone → NAS → cloud)
- Power-user file manager (multi-protocol, queue-based)

---

_Last updated: May 2026_
