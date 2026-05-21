# Bugs

> A living document of potential bugs.

---

## ✅ Fixed

- [x] Bookmarks should be saved within each individual server because servers might have different directories.
- [x] Move the back button to be next to the bookmarks on the left hand side.
- [x] Move the breadcrumbs to the bottom of the explorer.
- [x] Main Window: Clear button needs to be bigger
- [x] Settings Screen: Margin on Cancel/Save button area
- [x] ADB directory /sdcard is showing as a file and not a directory
- [x] When connected to a device, I can't switch to another server. It stays at the device when I try.
- [x] ADB delete doesn't work — fixed by using `rm -rf` directly instead of recursive stat+remove
- [x] ADB can't download file — fixed path normalization in `pull()` method
- [x] PyInstaller bundle crashes on launch — `importlib.metadata` not available in frozen app
- [x] Folder names not showing in transfer queue/logs when path has trailing slash
- [x] Duplicate detection triggers on folders (should only check files)
- [x] Upload verification fails for ADB (stat returns 0 bytes before filesystem syncs)

---

## 🐛 Open

- [ ] `QObject::killTimer` / `QBasicTimer::start` warnings on download completion (cosmetic, non-blocking)
- [ ] macOS menu bar may not show when running via `python main.py` from Terminal (works in .app bundle)
- [ ] `brew install` for ADB blocks the UI thread during installation (~30-60 seconds with no progress)
- [ ] Transfer queue index tracking could conflict if upload and download run simultaneously
- [ ] ADB `stat` can return stale/incorrect sizes immediately after file operations
- [ ] Large ADB folder listing (1000+ files) may still feel slow despite progressive loading if device USB is slow

---

## 🔍 To Investigate

- [ ] Does `adb push` handle filenames with special characters (spaces, quotes, unicode)?
- [ ] What happens if USB cable is disconnected mid-transfer?
- [ ] Does the app handle SSH connection timeout gracefully during a long idle period?
- [ ] Memory usage with very large transfer history (200 records should be fine, but untested at scale)
