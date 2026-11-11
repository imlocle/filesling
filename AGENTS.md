# FileSling Coding Rules

## General Style

- Keep code clear, direct, and easy to maintain. Prefer small, focused functions and descriptive names.
- Preserve the existing separation between views and widgets, controllers, services, clients, and workers.
- Add type hints to new or changed public methods. Avoid `Any` unless an external API requires it.
- Use the existing error hierarchy and `logger` for user-facing operation failures. Do not silently swallow errors that affect data or connection state.
- Keep comments for non-obvious decisions. Do not narrate code that is already clear.
- Keep user-facing copy concise and specific. Never use em dashes in user-facing strings. Code comments are exempt.

## Architecture and Reuse

- Keep the application flow `view/widget → controller → service → repository` for persisted data.
- Views and widgets render state and emit user intent. They must not own persistence or application workflows.
- Controllers coordinate signals and application state. Put reusable business rules in services.
- Repositories own persistence details such as JSON files. Keep file formats, atomic writes, and migrations out of controllers.
- Keep remote device protocol behavior in clients. Services may coordinate clients, but widgets should not open remote sessions or build shell commands.
- Put shared, deterministic helpers in purpose-specific `src/utils/` modules. Avoid turning `helper.py` into a grab bag.
- Before adding logic, search for an existing implementation and reuse or extract one canonical implementation when multiple callers need it.
- Keep each class focused. Move background tasks into `src/workers/` and split large modules by responsibility.
- Avoid pass-through wrappers and extra abstraction layers that do not own behavior or clarify a boundary.

## PySide6 and Concurrency

- Keep widget updates on the Qt main thread. Put blocking network, disk, and subprocess work in a worker or service called from a worker.
- Prefer signals for worker-to-UI communication. Ensure worker threads and external processes are stopped or cleaned up during shutdown.
- Avoid blocking waits in UI callbacks unless the wait is bounded and required for safe teardown.

## Data Safety and Security

- Verify SSH host keys. Never silently accept an unknown or changed host key.
- Store passwords, passphrases, and API tokens in the platform credential store. Do not write secrets to `config.json` or logs.
- Make file replacement transactional where possible. Verify completed writes before replacing existing files or removing local sources.
- Quote paths passed to remote shells and use argument arrays for local subprocesses. Never interpolate untrusted text into shell commands.
- Preserve cross-platform behavior through `src/platform/` rather than scattering OS checks through UI code.

## Settings and Compatibility

- Keep `SettingsConfig`, the per-server settings model, settings UI, and README examples consistent when adding a setting.
- Preserve existing user settings during migrations. Do not silently change an explicit user preference.
- Avoid adding dependencies when the existing standard library or project stack is sufficient.

## Validation

- Add or update focused tests for behavior changes when test work is requested.
- Use the repository's existing formatting and lint conventions. Keep documentation and release metadata in sync with application behavior.
