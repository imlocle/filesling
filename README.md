# Shuttle

<p align="center">
  <img src="assets/icons/shuttle_logo.png" alt="Shuttle" width="128">
</p>

A file manager for Mac that sends files to connected devices — SSH servers, Raspberry Pis, Android phones, tablets, and VR headsets — through a clean drag-and-drop interface.

Built with Python, PySide6, and Paramiko.

## Features

- 🖥 **Remote file explorer** — Browse any SSH server or Android device
- 📂 **Drag-and-drop upload** — Drop files from Finder into the explorer
- 📱 **Android USB support** — Connect phones/tablets via ADB (no MTP needed)
- 📊 **Transfer queue** — Queue uploads with speed, ETA, progress, auto-retry, and crash recovery
- 🔍 **Recursive search** — Search across subdirectories with Enter
- 🔄 **Multi-server** — Save multiple devices, set a default for auto-connect
- ⭐ **Per-server bookmarks** — Save quick-access folders and choose a default start folder per server
- ✏️ **Inline rename** — Slow-click to rename files directly
- 💾 **Disk space bar** — See usage for the current remote filesystem, including mounted drives
- 🗑 **Auto-cleanup** — Move local files to trash after upload
- 🧰 **Diagnostics log** — Hidden by default, available from the View menu when troubleshooting
- 🌓 **Appearance modes** — Follow system, light, or dark theme
- ⌨️ **Keyboard shortcuts** — ⌘+R, ⌘+N, ⌘+F, ⌘+Delete, etc.

## Quick Start

### Download the app

Grab `Shuttle.dmg` from the [latest release](https://github.com/imlocle/shuttle/releases/latest), open it, and drag `Shuttle.app` to Applications.

**First launch on macOS:** Apple blocks unsigned apps by default. Run this once in Terminal to allow it:

```bash
xattr -cr /Applications/Shuttle.app
```

Then open Shuttle normally.

### Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Requirements

- Python 3.11+
- SSH key-based access to your server
- For Android: `brew install android-platform-tools` + USB Debugging enabled

## Configuration

Stored at `~/.Shuttle/config.json`:

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

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs-internal/ROADMAP.md)
- [Case Study](https://imlocle.com/#/work/case-study/shuttle)

## Support

If Shuttle is useful to you, consider buying me a coffee ☕
[buymeacoffee.com/imlocle](https://buymeacoffee.com/imlocle)
