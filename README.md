# FileSling

<p align="center">
  <img src="assets/icons/filesling_logo.png" alt="FileSling" width="128">
</p>

A desktop file manager for macOS and Windows that sends files to SSH servers and connected Android and iOS devices through drag and drop.

Built with Python, PySide6, and Paramiko.

## Features

- **Remote file explorer:** Browse, upload, download, and manage files on SSH servers and Android devices
- **Drag and drop:** Drop files from Finder or Explorer into the current directory
- **Android USB and WiFi:** Connect phones, tablets, and VR headsets via ADB
- **iPhone and iPad USB:** Browse and back up camera roll photos and videos via AFC protocol
- **Transfer queue:** Queued uploads and downloads with speed, ETA, automatic retry, and resume
- **rsync fast path:** Delta transfers for SSH servers when rsync is available
- **Verified uploads:** SHA-256 checks and staged remote replacement before source files can be moved to Trash
- **Fast SSH transfers:** Use rclone parallel uploads or rsync when installed, with verified SFTP fallback
- **Jellyfin integration:** Optionally request a library scan after an upload batch completes
- **Remote video conversion:** Convert to H.264, H.265, or VP9 with ffmpeg on the server
- **Quick Fix:** Fix timestamps, change containers, or choose audio and subtitle tracks to keep without re-encoding. Apply container and timestamp fixes to multiple videos at once.
- **Media metadata:** Edit NFO sidecar files, batch edit multiple files, infer TV details from common folder names, and keep matching NFO files beside renamed videos
- **NFO cache:** Preload remote sidecar metadata in the background for faster detail
  panel updates
- **Batch metadata:** Apply shared fields such as Artist, Series, Season, and Episode to selected files
- **Fetch from IMDb:** Enter an IMDb ID or URL to fetch metadata through OMDb, with TMDB fallback
- **Multi-server:** Switch servers quickly with per-server bookmarks and settings
- **Destination profiles:** Save a connection, destination folder, and duplicate
  handling as a one-click upload target
- **Auto-reconnect:** Detect dropped connections and reconnect in the background with a bounded retry count
- **Sleep prevention:** Prevent sleep during active transfers where the platform supports it
- **Menu bar and tray icon:** Hide the window while the app stays available, then reopen it from the Dock, taskbar, or menu bar
- **Flexible authentication:** SSH key, password, or the platform credential store
- **Notifications:** Transfer status notifications and activity indicators where supported
- **Media info**: View detailed stream info and edit tags in a dedicated dialog
- **Batch operations**: Multi-select download, move, delete, and batch rename
- **Detail panel:** Show metadata and stream information for the selected file
- **Themes:** Dark mode, light mode, or follow system appearance
- **Keyboard shortcuts:** Common actions for refresh, new folder, search, details, and delete

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

No installer is needed. The app is portable and can be moved to another folder.

**Optional:** For credential storage when running from source, install the `keyring` package.

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
- macOS or Windows. Linux is not a packaged desktop target.
- SSH access to your server (key-based or password)
- For Android: ADB installed (macOS: `brew install android-platform-tools`, Windows: [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)) + USB Debugging enabled
- For iOS: `pip install pymobiledevice3` + device unlocked and trusted
- For IMDb metadata lookup (optional): a free [OMDb API key](https://www.omdbapi.com/apikey.aspx) and/or [TMDB API key](https://www.themoviedb.org/settings/api), entered in Settings → Files → Metadata Lookup
- For Jellyfin scans (optional): enter the URL and API key in server settings, then choose the server default or a profile override

SSH connections require a trusted host key. Verify the server fingerprint, then connect once with your system SSH client so it is recorded in `~/.ssh/known_hosts`.

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

1. **OMDb** (primary): set `omdb_api_key`. Get a free key at [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx) (activate it via the confirmation email).
2. **TMDB** (fallback): set `tmdb_api_key`. Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Used automatically when OMDb has no record for an ID (common for brand-new episodes).

Keys are stored in the operating system credential store and entered via Settings → Files → Metadata Lookup. FileSling does not scrape IMDb; it uses these providers' public APIs.

Passwords, SSH key passphrases, and API keys are stored in the operating system credential store when available. Existing saved credentials are migrated automatically. The config file is written with private permissions and replaced atomically.

### Jellyfin Library Scans

Enter the Jellyfin server URL and API key in the server's settings. Enable **Scan libraries after uploads** for the server default, or set a different scan action on an individual destination profile. FileSling batches queued uploads and sends a library refresh request when the batch finishes. This does not configure library paths or change Jellyfin's library settings.

### Destination Profiles

Use the **Destination** dropdown in the toolbar to save and switch between upload
targets such as a Jellyfin Movies folder, a VR headset, or an archive. Each profile
references a saved server or device connection, remembers its remote folder, and can
ask about duplicate files, skip them, or overwrite them. Credentials stay with the
saved connection. Uploads remain checksum verified. Profiles can inherit the
connection's Jellyfin scan setting, always scan after uploads, or disable the scan.
Wait for queued uploads to finish before changing destinations.

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

# Run tests
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
├── controllers/    UI event routing and application workflows
├── models/         ServerConfig dataclass, error hierarchy
├── platform/       OS abstraction (macOS, Windows, base stubs)
├── services/       Connection, transfer, metadata, and utility services
├── utils/          Constants, crash handler, icons, theme
├── views/          Main windows and dialogs
├── widgets/        Reusable UI components
└── workers/        Background tasks
```

## Releasing

```bash
# Release a new version (changes branches and pushes commits and a tag)
make release V=X.Y.Z
```

This single command:

1. Updates the version in `pyproject.toml` and `src/utils/constants.py`
2. Commits and pushes to `dev`
3. Merges `dev` → `main` and pushes
4. Creates a `vX.Y.Z` tag and pushes it
5. Switches back to `dev`

GitHub Actions builds the Python distributions, macOS DMG, and Windows ZIP, then creates the release. See the [release guide](docs/maintainers/releases.md) before running this command.

## Docs

- [Documentation index](docs/README.md)
- [Architecture](docs/development/architecture.md)
- [System diagrams](docs/development/system-diagram.md)
- [Raspberry Pi and Jellyfin setup](docs/user-guides/raspberry-pi-jellyfin.md)
- [Changelog](docs/project/changelog.md)
- [Roadmap](docs/project/roadmap.md)
- [Case Study](https://imlocle.com/#/work/case-study/filesling)

## License

MIT

## Support

If FileSling is useful to you, consider buying me a coffee ☕
[buymeacoffee.com/imlocle](https://buymeacoffee.com/imlocle)
