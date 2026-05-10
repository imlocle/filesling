# PiSync

A remote file manager for transferring files to any SSH server via drag-and-drop.

## Features

- **Remote file explorer** — Browse, navigate, rename, delete, create folders on any SSH server
- **Drag-and-drop upload** — Drop files from Finder directly into the remote explorer
- **Transfer queue** — Queue multiple transfers, see progress, speed, and ETA in real-time
- **Multi-server support** — Save multiple servers, set a default for auto-connect
- **Inline rename** — Slow-click a file to rename it directly (like Finder)
- **Disk space indicator** — Visual bar showing remote drive usage
- **Auto-cleanup** — Optionally move local files to trash after successful upload
- **Error logging** — Errors saved to `logs/errors.json` for debugging

## Setup

### Requirements

- Python 3.11+
- SSH access to your server (key-based auth)

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### First Launch

1. Add a server (IP, username, SSH key path, remote directory)
2. Set it as default (⭐) to skip the selection screen next time
3. Connect and start managing files

## Configuration

Config is stored at `~/.PiSync/config.json`.

Example server config:

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
  "delete_after_transfer": true,
  "file_extensions": [".mp4", ".mkv", ".avi", ".srt"],
  "skip_patterns": [".DS_Store", "._*"]
}
```

## Usage

- **Upload**: Drag files/folders from Finder into the remote explorer
- **Navigate**: Double-click folders to enter, click ← to go back
- **Rename**: Click a file, pause, click again to rename inline
- **Delete**: Right-click → Delete, or select + click 🗑 button
- **Create folder**: Right-click → New Folder
- **Change server**: Click 🔄 in the toolbar
- **Settings**: Click ⚙ to configure transfer behavior and file filters
