# Project Status

> Reviewed: November 2026
> Package version in the repository: 3.8.0

This is a snapshot of the repository configuration and documentation. It records what is configured, not whether a CI run or release succeeded on the review date.

## Application capabilities

- Desktop application for macOS and Windows, built with Python and PySide6.
- Transfers to SSH/SFTP servers, Android devices through ADB, and iOS devices through AFC.
- Upload queues, retries, transfer history, folder bookmarks, remote file operations, and media tools.
- Remote NFO sidecars are prefetched into an in-memory folder cache for detail panel metadata.
- SSH uploads use staged replacement and SHA-256 verification. Folder uploads include hidden files.
- Optional per-server Jellyfin refresh requests run after queued uploads finish.
- SSH host keys are checked against the user's `known_hosts` file. Credentials use the platform credential store when available.

## Automation configured in this repository

| Workflow | Trigger | Configured work |
| --- | --- | --- |
| Quality checks | Push to `dev`, pull request to `main` or `dev` | Black, isort, flake8, pytest on a macOS runner with Python 3.13 |
| Build and release | A tag matching `v*` | Python source and wheel packages, a macOS DMG, a Windows ZIP, then a GitHub Release |

The workflows describe automation. Check the latest GitHub Actions run before treating a build or check as passing. Branch protection settings determine whether checks are required for merges.

## Support notes

- The Windows release workflow builds a Windows artifact. The workflow does not run the quality suite on Windows or establish full Windows runtime coverage.
- `rclone` and `rsync` are optional SSH transfer paths. FileSling verifies output and falls back to the next method if an optimized path is unavailable or fails.
- Jellyfin refresh requires a reachable Jellyfin server, a valid API key, and a library already configured to watch the uploaded destination.
- The project does not provide cloud object storage or a hosted database. FileSling connects to storage that the user operates or has access to.

## Related documentation

- [Architecture](../development/architecture.md)
- [Platform support](platform-support.md)
- [Release guide](releases.md)
- [Known issues and audit notes](../project/known-issues.md)
