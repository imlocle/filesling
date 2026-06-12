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
- **iPhone/iPad USB** — Browse and back up camera roll photos/videos
- **Transfer queue** — Queued uploads/downloads with speed, ETA, auto-retry, and resume
- **rsync fast path** — Delta transfers for SSH servers (only sends changed bytes)
- **Remote video convert** — Right-click → Convert to H.264 (runs ffmpeg on server)
- **Multi-server** — Quick-switch dropdown, per-server bookmarks and settings
- **Auto-reconnect** — Detects dropped connections and reconnects with latency indicator
- **Flexible auth** — SSH key (with passphrase), password, or macOS Keychain
- **Notifications** — macOS alerts on transfer complete/fail, Dock badge for pending count
- **Batch operations** — Multi-select download, move, delete, and batch rename
- **Themes** — Modern iOS-inspired dark mode, or light
- **Keyboard shortcuts** — ⌘+R, ⌘+N, ⌘+F, ⌘+Delete, etc.

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
pip install -r requirements.txt
python main.py
```

## Requirements

- Python 3.11+
- SSH access to your server (key-based or password)
- For Android: `brew install android-platform-tools` + USB Debugging enabled

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
    }
  },
  "default_server_id": "my-server",
  "delete_after_transfer": true,
  "download_directory": "~/Downloads",
  "theme_mode": "system",
  "skip_patterns": [".DS_Store", "._*"]
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
| `⌘+Delete` | Delete selected                   |
| `Escape`   | Clear search / deselect           |

## Development

```bash
# Install dev dependencies
make dev-install

# Run the app
make run

# Format code
make format

# Lint
make lint

# Run tests
make test

# Build distribution
make build
```

## Releasing

```bash
# Release a new version (bumps version, merges to main, tags, pushes)
make release V=3.0.0
```

This single command:

1. Updates the version in `pyproject.toml` and `src/utils/constants.py`
2. Commits and pushes to `dev`
3. Merges `dev` → `main` and pushes
4. Creates a `v3.0.0` tag and pushes it
5. Switches back to `dev`

GitHub Actions then builds `FileSling.dmg` and creates the release automatically.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [System Diagram](docs/SYSTEM_DIAGRAM.md)
- [Roadmap](docs-internal/ROADMAP.md)
- [Case Study](https://imlocle.com/#/work/case-study/filesling)

## Support

If FileSling is useful to you, consider buying me a coffee ☕
[buymeacoffee.com/imlocle](https://buymeacoffee.com/imlocle)
