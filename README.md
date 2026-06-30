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
- **Multi-server** — Quick-switch dropdown, per-server bookmarks and settings
- **Auto-reconnect** — Detects dropped connections and reconnects with latency indicator
- **Sleep prevention** — Mac stays awake during active transfers (configurable)
- **Flexible auth** — SSH key (with passphrase), password, or macOS Keychain
- **Notifications** — macOS alerts on transfer complete/fail, Dock badge for pending count
- **Batch operations** — Multi-select download, move, delete, and batch rename
- **Detail panel** — Side panel showing metadata + stream info on file select (⌘I)
- **Themes** — Modern dark mode with macOS-style toggle switches, light mode, or follow system
- **Keyboard shortcuts** — ⌘+R, ⌘+N, ⌘+F, ⌘+I, ⌘+Delete, etc.

## Quick Start

### Download the app

Grab `FileSling.dmg` from the [latest release](https://github.com/imlocle/filesling/releases/latest), open it, and drag `FileSling.app` to Applications.

**First launch on macOS:** Apple blocks unsigned apps by default. Run this once in Terminal to allow it:

```bash
xattr -cr /Applications/FileSling.app
```

Then open FileSling normally.

### Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Requirements

- Python 3.9+ (3.13 recommended)
- macOS (primary platform)
- SSH access to your server (key-based or password)
- For Android: `brew install android-platform-tools` + USB Debugging enabled
- For iOS: `pip install pymobiledevice3` + device unlocked and trusted

## Configuration

Stored at `~/.FileSling/config.json`:

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
  "skip_patterns": [".DS_Store", "._*", "Thumbs.db", ".Trashes"]
}
```

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

# Run tests (437 unit tests)
make test

# Build distribution (wheel + sdist)
make build
```

## Project Structure

```
src/
├── clients/        Device backends (DeviceClient protocol, ADB, iOS)
├── config/         Settings singleton (Pydantic model)
├── controllers/    UI event routing (5 controllers)
├── models/         ServerConfig dataclass, error hierarchy
├── services/       Business logic (8 services)
├── utils/          Constants, crash handler, icons, theme
├── views/          Windows and dialogs (3 windows + 5 dialogs)
├── widgets/        Reusable UI components (7 widgets)
└── workers/        Background QThread workers (5 workers)
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
