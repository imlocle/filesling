# Platform Support

> Reviewed: November 2026

FileSling has a platform abstraction layer for operating system integrations. The repository currently includes macOS and Windows implementations, plus base fallbacks for unsupported platforms.

## Implemented platform integrations

| Capability | macOS | Windows |
| --- | --- | --- |
| Credential storage | Keychain | Windows credential manager through `keyring` |
| Notifications | macOS notification integration | Qt system tray notification |
| Prevent sleep during transfers | `caffeinate` | `SetThreadExecutionState` |
| Reveal a file in the file manager | Finder | Explorer |
| App packaging in release workflow | DMG | ZIP containing the PyInstaller build |

Shared application code remains in `src/`. Platform-specific behavior belongs in `src/platform/` and its platform modules.

## Build and runtime coverage

- `.github/workflows/publish.yml` builds macOS and Windows artifacts when a `v*` tag is pushed.
- `.github/workflows/quality.yml` runs formatting, lint, and tests on a macOS runner.
- The configured workflows do not run the full test suite on Windows.
- Confirm Windows UI appearance, SSH authentication, transfers, ADB discovery, and credential persistence on a Windows machine before describing those behaviors as manually validated.
- Linux has base fallbacks but is not a packaged desktop target in the release workflow.

## Platform changes

When adding an operating system integration:

1. Add the operating system behavior in `src/platform/`.
2. Keep UI, controller, and service code independent of platform-specific shell commands where practical.
3. Update packaging and dependency inputs in `pyproject.toml`, requirements files, and `.github/workflows/publish.yml` as needed.
4. Update the relevant tests and documentation when implementation work is requested.
