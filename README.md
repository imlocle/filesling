# PiSync

A remote file manager for transferring files to any SSH server via drag-and-drop.

Built with Python, PySide6, and Paramiko.

## Features

- 🖥 **Remote file explorer** — Browse any SSH server's filesystem
- 📂 **Drag-and-drop upload** — Drop files from Finder into the explorer
- 📊 **Transfer queue** — Queue multiple uploads with speed, ETA, and progress
- 🔄 **Multi-server** — Save multiple servers, set a default for auto-connect
- ✏️ **Inline rename** — Slow-click to rename files directly
- 💾 **Disk space bar** — See how full the remote drive is
- 🗑 **Auto-cleanup** — Move local files to trash after upload
- 🔌 **Auto-connect** — Set a default server and skip the selection screen

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## Configuration

Stored at `~/.PiSync/config.json`. Example:

```json
{
  "servers": {
    "my-server": {
      "name": "My Server",
      "pi_user": "pi",
      "pi_ip": "192.168.1.100",
      "ssh_key_path": "~/.ssh/id_rsa",
      "ssh_port": 22,
      "remote_base_dir": "/mnt/external"
    }
  },
  "default_server_id": "my-server",
  "delete_after_transfer": true
}
```

## Requirements

- Python 3.11+
- SSH key-based access to your server

## Docs

- [Architecture](docs/architecture.md)
- [Feature Ideas](docs/ideas.md)
