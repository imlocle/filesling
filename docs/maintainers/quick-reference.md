# Developer Quick Reference

## Set up the development environment

```bash
python3 -m venv .venv
source .venv/bin/activate
make dev-install
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Common commands

```bash
make run       # Run FileSling
make format    # Apply Black and isort
make lint      # Run flake8
make test      # Run pytest with the repository configuration
make build     # Build wheel and source distribution
```

## Project areas

```text
src/clients/       Remote device and protocol clients
src/config/        Settings model and persistence
src/controllers/   UI event routing and application workflows
src/models/        Shared data models and errors
src/platform/      Operating system integrations
src/services/      Connection, transfer, metadata, and utility services
src/views/         Windows and dialogs
src/widgets/       Reusable interface components
src/workers/       Background tasks
tests/             Automated tests organized around application modules
docs/              User, development, maintenance, and project documentation
```

## Release

See the [release guide](releases.md) before using `make release V=X.Y.Z`. That target changes branches and pushes commits and tags to `origin`.
