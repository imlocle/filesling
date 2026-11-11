"""Small, shared helpers for reading and writing JSON files safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


def read_json_file(path: Path, default: Any = None) -> Any:
    """Read JSON, returning ``default`` only when the file does not exist."""
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def write_json_file_atomic(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    directory_mode: Optional[int] = None,
    file_mode: Optional[int] = None,
) -> None:
    """Write JSON to a sibling temporary file and atomically replace ``path``."""
    path.parent.mkdir(
        mode=directory_mode if directory_mode is not None else 0o777,
        parents=True,
        exist_ok=True,
    )
    if directory_mode is not None and os.name != "nt":
        os.chmod(path.parent, directory_mode)

    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}-",
            delete=False,
        ) as file:
            temporary_path = file.name
            if file_mode is not None and os.name != "nt":
                os.chmod(temporary_path, file_mode)
            json.dump(data, file, indent=indent)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
        if file_mode is not None and os.name != "nt":
            os.chmod(path, file_mode)
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except OSError:
                pass
