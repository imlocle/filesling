# FileSling — Roadmap

> What's next. For completed work, see [CHANGELOG.md](CHANGELOG.md).

> **Design philosophy:** Manual, power-user tool. You control every transfer.
> No background syncing. No "magic" that moves files without you asking.

---

## Up Next

### 1. SMB/CIFS — Windows PCs and NAS Devices

- [ ] SMB backend (via `smbprotocol`)
- [ ] Connect to `\\192.168.1.50\Media` on a Windows PC or NAS (Synology, QNAP)
- [ ] Username/password auth
- [ ] Auto-discover shares on local network (optional)
- [ ] Remember mounted shares per server

---

### 2. S3 — AWS Bucket Transfers

- [ ] S3 backend (via `boto3`)
- [ ] Auth: reads `~/.aws/credentials` profile, or paste keys into Add Server dialog, stored in Keychain
- [ ] Browse buckets and "folders" (S3 prefixes) in the same explorer
- [ ] Multipart upload/download for large files
- [ ] Show storage class (Standard, Glacier)
- [ ] Region selector per bucket

---

### 3. Google Drive

- [ ] Google Drive backend (via `google-api-python-client`)
- [ ] OAuth2 auth: opens browser once, token stored in Keychain
- [ ] Browse Drive folders in the same explorer
- [ ] Resumable uploads/downloads
- [ ] Optional: Shared Drives support

---

### 4. macOS Native Polish

- [ ] Menu bar icon with drop zone — drag a file to quick-send without opening the window
- [ ] Finder extension — right-click any file → "Send with FileSling"
- [ ] Quick Look preview — spacebar on a remote file to preview it
- [ ] Native share sheet — "Share → FileSling" from other apps
- [ ] In-app transfer history search (Spotlight-style)

---

### 5. Integrity & Control

- [ ] Checksum verification — compare MD5/SHA after transfer (catches silent corruption)
- [ ] Manual folder compare — diff two folders, you pick what to transfer (anti-sync)
- [ ] Bandwidth limit — cap transfer speed so uploads don't choke your network
- [ ] Dry run — preview what a multi-file transfer will do before committing

---

### ~~6. Remote Video Convert (ffmpeg)~~ ✅ Done

> See [CHANGELOG.md](CHANGELOG.md). Implemented June 2026.

---

### 7. Post-Transfer Hooks

- [ ] Run a script/command after a transfer completes (in Settings per-server)
  - Example: trigger Plex library rescan after uploading to NAS
  - Example: `adb install` after pushing an `.apk`
- [ ] Optional Slack/Discord notification on big transfers

---

### 8. MTP — Android Without Developer Mode

- [ ] MTP backend (via `libmtp`) as fallback when ADB unavailable
- [ ] Use case: a friend's phone where you can't enable Developer Mode
- [ ] Label as "experimental" (libmtp is flaky on macOS)

---

### 9. WebDAV

- [ ] WebDAV backend for Nextcloud, Synology, Box
- [ ] Username/password or token auth
- [ ] Low priority — only useful if you run those services

---

## Done (v3.2.0)

- ~~rsync fast transfers~~ — delta sync, auto-fallback to SFTP
- ~~iPhone/iOS support~~ — camera roll via AFC/pymobiledevice3
- ~~ADB over WiFi~~ — wireless Android transfers
- ~~Multi-server quick-switch~~ — toolbar dropdown
- ~~Remote video convert~~ — right-click → Convert to H.264 (ffmpeg on server)
- ~~24-bug deep audit~~ — all resolved
- ~~Modern dark theme~~ — iOS-inspired redesign
- ~~Transfer queue rework~~ — per-file rows, proper ordering, renamed to "Activity"

---

## Deferred — Automation

> Strictly opt-in, off by default, never silent. At the bottom on purpose.

- [ ] Watch Folders — auto-upload new files from a local folder
- [ ] Transfer Rules — pattern-based routing
- [ ] Device-Aware Actions — run rules when a device connects
- [ ] AI suggestions — recommend rules based on transfer history (not a chatbot)

---

_Last updated: June 2026_
