# Release Guide

FileSling releases are created from Git tags matching `v*`. The release workflow builds the Python distributions and desktop artifacts, then attaches them to a GitHub Release.

## Artifacts

The workflow in `.github/workflows/publish.yml` builds:

- Python wheel and source distribution on Ubuntu.
- `FileSling.dmg` on macOS.
- `FileSling-Windows.zip` on Windows.

It does not publish packages to PyPI. The quality workflow is separate and runs on pushes to `dev` and pull requests targeting `main` or `dev`.

## Before a release

- Review the changes and confirm the working tree is in the state you expect.
- Review `docs/project/changelog.md` and update the version in `pyproject.toml` and `src/utils/constants.py` together.
- Run the quality commands you want to require for this release and review their results.
- Confirm `dev` is ready to merge into `main`.

## Automated release command

The Makefile provides:

```bash
make release V=X.Y.Z
```

This command edits both version fields, commits the version bump, pushes `dev`, checks out `main`, merges and pushes `dev`, creates and pushes the `vX.Y.Z` tag, then checks out `dev` again. It performs real Git operations and does not first verify that the working tree is clean. Review your branch and uncommitted changes before running it. The `sed -i ''` syntax in the Makefile is macOS-specific.

## Manual release steps

If you do not use the Makefile command:

```bash
git checkout dev
# Update pyproject.toml and src/utils/constants.py to the same X.Y.Z version.
git add pyproject.toml src/utils/constants.py
git commit -m "bump version to X.Y.Z"
git push origin dev

git checkout main
git merge dev
git push origin main

git tag vX.Y.Z
git push origin vX.Y.Z
git checkout dev
```

Pushing the tag starts the build and release workflow. Review the GitHub Actions run and the attached artifacts when it completes.

## Local builds

```bash
# Build the wheel and source distribution
python -m build

# Build the macOS app bundle with PyInstaller
./scripts/build_exe.sh
```

The standalone local script produces `dist/FileSling.app`. The tagged workflow is responsible for the published DMG and Windows ZIP.

## Recovery from a failed tagged build

Fix and commit the build issue, then follow the repository's tag recovery procedure. Before deleting or moving a published tag, check whether a GitHub Release already exists and review its attached artifacts. Prefer a new patch version when a release has already been announced or distributed.
