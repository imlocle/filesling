#!/bin/bash
# Build standalone executable using PyInstaller

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

echo "==================================="
echo "FileSling — PyInstaller Build"
echo "==================================="
echo ""

# Check if PyInstaller is installed
if ! pip show pyinstaller > /dev/null 2>&1; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

# Build executable
echo "Building standalone executable..."
cd "$PROJECT_ROOT"

pyinstaller \
    --name=FileSling \
    --windowed \
    --icon=assets/icons/filesling_logo.png \
    --add-data="assets:assets" \
    --hidden-import=paramiko \
    --hidden-import=pydantic \
    --hidden-import=PySide6 \
    main.py

echo ""
echo "Build complete!"
echo "Executable: $PROJECT_ROOT/dist/FileSling.app"
