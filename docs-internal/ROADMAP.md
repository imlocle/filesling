# FileSling — Roadmap

> Ideas for advancing the application. For completed work, see [CHANGELOG.md](CHANGELOG.md).

> FileSling's architecture (backend abstraction where ADBClient mimics SFTPClient) means
> new connection types can be added without changing the explorer UI. Each backend just
> needs: listdir, stat, put, get, rename, mkdir, remove.
>
> **Design philosophy:** FileSling is a manual, power-user tool. You stay in control of
> every transfer. No background syncing, no "magic" that moves your files without you
> asking. Automation ideas live at the very bottom and are opt-in only.

---

## 🔮 Future Directions

### 1. SCP / rsync — Faster Transfers

> Highest priority. Directly improves the core job: moving files fast.

- [x] **rsync backend for SSH servers** — only transfers the changed parts of files (delta sync)
  - Example: re-uploading a 4GB video after a small edit transfers only the diff, not the whole file
  - Much faster for large files and folders that partially exist on the remote
- [x] **Auto-pick the fastest method** — use rsync if available on the server, fall back to SFTP
- [x] Show "delta: only 12 MB of 4 GB transferred" savings in the diagnostics log
- [x] ~~SCP for raw speed~~ — subsumed by rsync (rsync handles single files too, with delta + resume that SCP lacks)

> Implementation: `src/services/rsync_service.py` runs `rsync -az --partial --stats` over
> SSH. Requires SSH key auth (BatchMode); password-auth servers fall back to SFTP. macOS
> ships with rsync; most Linux servers have it too. Falls back gracefully if unavailable.

---

### 2. iPhone / iOS — Back Up Photos & Videos

> The use case: an iPhone with a full camera roll and full iCloud. Plug it into the Mac,
> browse the photos/videos, and offload them to any server you've attached (NAS, SSH, S3).
> This pairs with the existing Android support to make FileSling the device backup tool
> for Mac — both major phone platforms covered.

- [ ] **iOS backend** via `libimobiledevice` (open source, USB over the AFC protocol)
  - Exposes the iPhone's camera roll (DCIM — all photos and videos) as a browsable filesystem
  - No jailbreak required; the media folder is accessible once the device is paired/trusted
- [ ] Browse the camera roll in the same explorer UI (like ADB for Android)
- [ ] Select photos/videos → transfer to any attached server
- [ ] Handle the trust prompt: detect "device locked / not trusted" and tell the user to
      unlock the phone and tap "Trust This Computer"
- [ ] Auto-detect a connected iPhone like we do for Android USB devices

> **Feasibility:** Solid for photos/videos. `libimobiledevice` + AFC reads the media
> partition without special access. **Limits:** it can only reach the camera roll and a few
> media folders — not app data, Messages, or hidden iCloud-only content (photos that were
> offloaded to iCloud and aren't physically on the device won't appear until downloaded).
> Full device backups (`idevicebackup2`) produce an encrypted blob, not browsable files —
> out of scope. Requires `libimobiledevice` installed (Homebrew); FileSling would prompt to
> install it, same pattern as the ADB install helper.

---

### 3. SMB/CIFS — Connect to Windows PCs and NAS Devices

> You asked what a NAS is: a **N**etwork **A**ttached **S**torage device — basically a
> small always-on box (Synology, QNAP, etc.) or even an old PC that holds files and shares
> them over your home network. SMB is the protocol Windows and NAS devices use for file
> sharing. This lets FileSling browse them like any other server.

- [ ] **SMB/CIFS backend** (via `pysmb` or `smbprotocol`)
  - Example: connect to `\\192.168.1.50\Media` on your Windows PC and drag files in
  - Example: browse a Synology/QNAP NAS share without their clunky web UI
- [ ] Username/password auth (SMB doesn't use SSH keys)
- [ ] Auto-discover SMB shares on the local network (optional, via mDNS/WS-Discovery)
- [ ] Remember mounted shares per server like SSH/ADB

---

### 4. S3 — AWS Bucket Transfers

> Useful since you already know AWS. The main question you raised — "how do I sign in?" —
> is handled below.

- [ ] **S3 backend** (via `boto3`)
- [ ] **Auth flow** — FileSling reads standard AWS credentials, in this order:
  1. A profile from `~/.aws/credentials` (what you get after running `aws configure`)
  2. Manually entered Access Key ID + Secret Access Key in the Add Server dialog
  3. Stored securely in the macOS Keychain (reuse the existing keychain service)
  - You'd pick a profile or paste keys once; FileSling never sends them anywhere but AWS
- [ ] Browse buckets and "folders" (S3 prefixes) in the same explorer
- [ ] Upload/download with multipart for large files (boto3 handles this)
- [ ] Show storage class (Standard, Glacier) and let you set it on upload
- [ ] Optional: region selector per bucket

---

### 5. Google Drive — Cloud Backup Target

> Another good backup destination, especially if the goal is getting photos/videos off a
> full iCloud and into a place with more room. Cleanly fits the backend model.

- [ ] **Google Drive backend** (via `google-api-python-client`)
- [ ] **Auth flow (OAuth2):**
  1. Click "Connect Google Drive" → opens your browser to Google's login/consent screen
  2. You approve access once; Google hands back a token
  3. Token stored in the macOS Keychain and refreshed automatically — you won't re-login each time
- [ ] Browse Drive folders in the same explorer (maps Drive's ID-based model to paths)
- [ ] Upload/download with resumable transfers (the Drive API supports this for big files)
- [ ] Handle Google's quirks: a file can technically live in multiple folders, and folders
      are a special MIME type — the adapter normalizes this to a normal tree
- [ ] Optional later: support Shared Drives (Team Drives)

> **Feasibility:** Well-supported API. The extra work vs. S3 is the OAuth browser flow and
> mapping Drive's non-hierarchical model to a folder tree. **Alternative considered:** shell
> out to `rclone` (which already speaks Drive, S3, Dropbox, etc.). That would add many
> backends at once but changes the architecture to "drive rclone" instead of native Python
> adapters — worth weighing if cloud backends pile up.

---

### 6. Multi-Server Quick-Switch

> The dialog-free switching you liked.

- [ ] **Server dropdown in the toolbar** — switch active server with one click, no dialog
- [ ] Show connection status dot next to each server name (green/red/connecting)
- [ ] Remember the last-browsed path per server so switching feels instant
- [ ] **Split-pane mode** (later) — two servers side by side, drag files directly between them
  - Example: NAS on the left, S3 bucket on the right, drag to copy between them
  - This is the power-user dream: server-to-server transfers without round-tripping through your Mac

---

### 7. macOS Native Polish

> Everything here except the Touch Bar (agreed — that was a bad idea Apple killed anyway).
> These are small, native touches that make it feel like a real Mac app.

- [ ] **Menu bar icon with a drop zone** — drag a file onto the menu bar icon to quick-send
      to your default server without opening the full window
- [ ] **Finder extension** — right-click any file in Finder → "Send with FileSling"
- [ ] **Quick Look preview** — press spacebar on a remote file to preview it (downloads a
      temp copy and hands it to macOS Quick Look, just like Finder)
- [ ] **Native share sheet** — "Share → FileSling" from other apps
- [ ] **Spotlight-style transfer history search** — fast in-app search of everything you've sent
- [ ] ~~Touch Bar support~~ — skipped on purpose

---

### 8. MTP — Android Without Developer Mode

> You asked: is it worth it, and can ADB and MTP coexist? Short answer: **yes they can
> coexist** (MTP would just be another backend type), but it's **lower priority** because
> `libmtp` is genuinely flaky on macOS — slow enumeration, random disconnects. ADB is more
> reliable whenever the user can enable USB Debugging.

- [ ] **MTP backend** (via `libmtp`) as a fallback when ADB isn't available
  - Use case: a friend's phone where you can't enable Developer Mode
- [ ] Keep ADB as the default/preferred Android path; offer MTP only if ADB fails
- [ ] Clearly label it "experimental" so expectations are set

---

### 9. WebDAV — Self-Hosted & Cloud Drives

> You said you don't know what this is for — that's fine, it's niche. WebDAV is a protocol
> used by self-hosted cloud apps (Nextcloud), some NAS devices (Synology), and services
> like Box. If you don't run any of those, you don't need it. Leaving it here for
> completeness since it's cheap to add once SMB/S3 exist.

- [ ] **WebDAV backend** (via `webdavclient3` or similar)
- [ ] Username/password or token auth
- [ ] Useful mainly for people already running Nextcloud/Synology

---

### 10. Integrity & Control (New Ideas)

> These fit your "full control, know exactly what happened" mindset.

- [ ] **Checksum verification** — optionally verify a transfer by comparing MD5/SHA of both
      sides, not just file size. Catches silent corruption on big media files
- [ ] **Manual folder compare** — point at a local folder and a remote folder, see a diff
      (what's only here, only there, or different) and pick what to transfer. This is the
      _opposite_ of auto-sync: it shows you everything and you decide, nothing moves on its own
- [ ] **Bandwidth limit** — cap transfer speed (e.g. 5 MB/s) so a big upload doesn't choke
      your network while you're working
- [ ] **Per-transfer "reveal source"** — jump from a queue item back to the file in Finder
- [ ] **Dry run** — preview exactly what a multi-file transfer will do before committing

---

### 11. Plugin System

> You wanted examples to judge if it's useful or overkill. Here's what a plugin could
> actually do — all **manual, triggered by you**, never background:

- [ ] **Post-transfer hooks** — run a script after a transfer _you_ started
  - Example: after uploading a video to your NAS, run a script that kicks off Plex to
    rescan its library
  - Example: after uploading a `.apk` to a test device, run `adb install` automatically
- [ ] **Notification integrations** — ping Slack/Discord when a big transfer finishes
  - Example: "✅ 12 GB backup uploaded to NAS" posted to your private Discord
- [ ] **Custom destination resolvers** — a plugin that decides where a file goes based on
      your own rules (you write the logic)

> Verdict: probably **overkill for v1**, but post-transfer hooks alone (run a script after
> upload) might be worth doing as a single small feature rather than a whole plugin system.
> Recommend starting with just "run this command after transfer completes" in Settings.

---

## 🧊 Deferred — Automation (Not a Priority)

> Intentionally at the bottom. FileSling is built for people who want manual control. The
> whole point is _you_ decide when files move — not the app guessing or syncing behind your
> back. (Same reason you hate auto-synced texts showing up on every Apple device.)
>
> If these ever get built, they'd be **strictly opt-in, off by default, and clearly
> visible** — never silent.

### Workflow Automation (Rules Engine)

- [ ] **Watch Folders** — monitor a local folder, auto-upload new files to a destination
  - Example: `~/Movies/OBS/` → auto-upload to NAS `/recordings/`
- [ ] **Transfer Rules** — pattern-based routing (`*.mp4` → always send to a set folder)
- [ ] **Device-Aware Actions** — when a specific device connects, run a rule
- [ ] **Auto-Rename Templates** — rename on transfer using patterns (EXIF date, counters)
- [ ] **Rules UI** — simple list of if/then rules in Settings

### AI-Assisted Suggestions

- [ ] Suggest rules based on repeated transfer patterns (built on transfer history)
- [ ] Suggest destinations based on file type + history
- [ ] Flag potential duplicates using filename similarity
- [ ] NOT a chatbot, NOT semantic search, NOT an assistant sidebar

---

## Positioning

FileSling isn't just "Android File Transfer replacement" — it's a native macOS transfer
hub for devices and servers, built for people who want to stay in control. The unified
backend abstraction means it can grow into:

- Dev/homelab tool (SSH servers, Docker, Raspberry Pi, NAS)
- Creator workflow (camera → phone → NAS → S3)
- Power-user file manager (multi-protocol, queue-based, manual by design)

---

_Last updated: May 2026_
