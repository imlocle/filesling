# FileSling

<p align="center">
  <img src="assets/icons/filesling_logo.png" alt="FileSling" width="128">
</p>

A file manager for Mac that sends files to connected devices — SSH servers, Raspberry Pis, Android phones, tablets, and VR headsets — through a clean drag-and-drop interface.

Built with Python, PySide6, and Paramiko.

## Features

- **Remote file explorer** — Browse, upload, download, and manage files on SSH servers and Android devices
- **Drag-and-drop** — Drop files from Finder into the current directory
- **Android USB + WiFi** — Connect phones, tablets, and VR headsets via ADB (wired or wireless)
- **iPhone/iPad USB** — Browse and back up camera roll photos/videos via AFC protocol
- **Transfer queue** — Queued uploads/downloads with speed, ETA, auto-retry, and resume
- **rsync fast path** — Delta transfers for SSH servers (only sends changed bytes)
- **Remote video convert** — Right-click → Convert to H.264/H.265/VP9 (runs ffmpeg on server)
- **Quick Fix** — Fix timestamps, change container, selectively remove subtitle tracks (no re-encoding)
- **Media metadata** — Edit .nfo sidecar files, batch edit across multiple files, view stream info
- **Batch metadata** — Multi-select → apply shared fields (Artist, Series, Season, Episode #) to all
- **Fetch from IMDb** — Enter an IMDb ID (or paste an IMDb URL) to auto-fill metadata fields via OMDb, with automatic TMDB fallback for titles OMDb doesn't have yet
- **Multi-server** — Quick-switch dropdown, per-server bookmarks and settings
- **Auto-reconnect** — Detects dropped connections and reconnects with latency indicator
- **Sleep prevention** — Mac stays awake during active transfers (configurable)
- **Menu bar icon** — App lives in the menu bar; close hides the window, click Dock/taskbar or menu bar to reopen, ⌘Q fully quits
- **Flexible auth** — SSH key (with passphrase), password, or macOS Keychain
- **Notifications** — macOS alerts on transfer complete/fail, Dock badge for pending count
- **Media info** — View detailed stream info and edit tags in a dedicated dialog
- **Batch operations** — Multi-select download, move, delete, and batch rename
- **Detail panel** — Side panel showing metadata + stream info on file select (⌘I)
- **Themes** — Modern dark mode with macOS-style toggle switches, light mode, or follow system
- **Keyboard shortcuts** — ⌘+R, ⌘+N, ⌘+F, ⌘+I, ⌘+Delete, etc.

## Quick Start

### macOS

Grab `FileSling.dmg` from the [latest release](https://github.com/imlocle/filesling/releases/latest), open it, and drag `FileSling.app` to Applications.

**First launch:** Apple blocks unsigned apps by default. Run this once in Terminal to allow it:

```bash
xattr -cr /Applications/FileSling.app
```

Then open FileSling normally.

### Windows

Grab `FileSling-Windows.zip` from the [latest release](https://github.com/imlocle/filesling/releases/latest), extract it, and run `FileSling.exe`.

No installer needed — it's a portable app. You can move the folder anywhere (e.g., `C:\Program Files\FileSling\`).

**Optional:** For credential storage (remember SSH passwords), install the `keyring` package if running from source.

### Run from source

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install keyring
python main.py
```

## Requirements

- Python 3.9+ (3.13 recommended)
- macOS or Windows (macOS is the primary platform)
- SSH access to your server (key-based or password)
- For Android: ADB installed (macOS: `brew install android-platform-tools`, Windows: [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)) + USB Debugging enabled
- For iOS: `pip install pymobiledevice3` + device unlocked and trusted
- For IMDb metadata lookup (optional): a free [OMDb API key](https://www.omdbapi.com/apikey.aspx) and/or [TMDB API key](https://www.themoviedb.org/settings/api), entered in Settings → Files → Metadata Lookup

## Configuration

Stored at `~/.FileSling/config.json` (macOS/Linux) or `%APPDATA%\FileSling\config.json` (Windows):

```json
{
  "servers": {
    "my-server": {
      "name": "My Server",
      "connection_type": "ssh",
      "username": "user",
      "host": "192.168.1.100",
      "ssh_key_path": "~/.ssh/id_rsa",
      "ssh_port": 22,
      "remote_base_dir": "/",
      "bookmarks": ["/mnt/external"],
      "default_bookmark": "/mnt/external"
    },
    "my-phone": {
      "name": "My Phone",
      "connection_type": "adb",
      "device_id": "DEVICE_SERIAL",
      "remote_base_dir": "/storage/emulated/0",
      "bookmarks": ["/storage/emulated/0/Download"],
      "default_bookmark": "/storage/emulated/0/Download"
    },
    "my-iphone": {
      "name": "My iPhone",
      "connection_type": "ios",
      "device_id": "UDID",
      "remote_base_dir": "/DCIM"
    }
  },
  "default_server_id": "my-server",
  "delete_after_transfer": true,
  "download_directory": "~/Downloads",
  "theme_mode": "system",
  "skip_patterns": [".DS_Store", "._*", "Thumbs.db", ".Trashes"],
  "omdb_api_key": "",
  "tmdb_api_key": ""
}
```

### Metadata Lookup (IMDb)

FileSling can auto-fill video metadata from an IMDb ID. In the Media Info dialog (right-click a video → **Edit Metadata**), enter an IMDb ID like `tt0983514` (or paste a full IMDb URL) and click **Fetch**. The fields populate for review before you save the `.nfo` file.

Two providers are used, in order:

1. **OMDb** (primary) — set `omdb_api_key`. Get a free key at [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx) (activate it via the confirmation email).
2. **TMDB** (fallback) — set `tmdb_api_key`. Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Used automatically when OMDb has no record for an ID (common for brand-new episodes).

Keys are stored locally in your config and entered via Settings → Files → Metadata Lookup. FileSling does not scrape IMDb; it uses these providers' public APIs.

## Keyboard Shortcuts

| Shortcut   | Action                            |
| ---------- | --------------------------------- |
| `⌘+F`      | Focus search bar                  |
| `Enter`    | Navigate into folder / run search |
| `⌘+↑`      | Go back one directory             |
| `⌘+N`      | New folder                        |
| `⌘+R`      | Refresh                           |
| `⌘+I`      | Toggle detail panel               |
| `⌘+Delete` | Delete selected                   |
| `⌘+Q`      | Fully exits the application       |
| `Escape`   | Clear search / deselect           |

## Development

```bash
# Create virtual environment and install dev dependencies
python3 -m venv .venv
source .venv/bin/activate
make dev-install

# Run the app
make run

# Format code (black + isort)
make format

# Lint (flake8)
make lint

# Run tests (477 unit tests)
make test

# Build distribution (wheel + sdist)
make build
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <short description>
```

| Type       | When to use                                             |
| ---------- | ------------------------------------------------------- |
| `feat`     | New feature or page                                     |
| `fix`      | Bug fix                                                 |
| `docs`     | Documentation only                                      |
| `style`    | Formatting, whitespace, no code logic change            |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf`     | Performance improvement                                 |
| `chore`    | Build config, dependencies, tooling                     |
| `content`  | Copy or content updates in `src/data/`                  |

Keep messages lowercase, imperative, and under 72 characters.

## Project Structure

```
src/
├── clients/        Device backends (DeviceClient protocol, ADB, iOS)
├── config/         Settings singleton (Pydantic model)
├── controllers/    UI event routing (5 controllers)
├── models/         ServerConfig dataclass, error hierarchy
├── platform/       OS abstraction (macOS, Windows, base stubs)
├── services/       Business logic (11 services, incl. IMDb/OMDb+TMDB lookup)
├── utils/          Constants, crash handler, icons, theme
├── views/          Windows and dialogs (2 windows + 7 dialogs)
├── widgets/        Reusable UI components (8 widgets)
└── workers/        Background QThread workers (6 workers)
```

## Releasing

```bash
# Release a new version (bumps version, merges to main, tags, pushes)
make release V=3.3.0
```

This single command:

1. Updates the version in `pyproject.toml` and `src/utils/constants.py`
2. Commits and pushes to `dev`
3. Merges `dev` → `main` and pushes
4. Creates a `v3.3.0` tag and pushes it
5. Switches back to `dev`

GitHub Actions then builds `FileSling.dmg` and creates the release automatically.

## Icon Generation

To regenerate app icons from the source logo (after updating `assets/icons/filesling_logo.png`):

```bash
.venv/bin/python scripts/generate_icons.py
.venv/bin/python scripts/generate_menu_bar_icon.py
```

These scripts are local dev tools (not committed to the repo). They produce all required sizes (16×16 through 1024×1024), the macOS `.icns` bundle, the Windows `.ico`, and the menu bar template icon in `assets/icons/generated/`.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [System Diagram](docs/SYSTEM_DIAGRAM.md)
- [Changelog](docs-internal/CHANGELOG.md)
- [Roadmap](docs-internal/ROADMAP.md)
- [Case Study](https://imlocle.com/#/work/case-study/filesling)

## License

MIT

## Support

If FileSling is useful to you, consider buying me a coffee ☕
[buymeacoffee.com/imlocle](https://buymeacoffee.com/imlocle)
