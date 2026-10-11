"""Locate portable tools and keep helper processes out of the user's way."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_tool(name: str) -> str | None:
    bundle = os.environ.get("VIDEODOWNLOADER_BUNDLE_ROOT")
    if not bundle:
        return shutil.which(name)
    filename = name + (".exe" if sys.platform == "win32" else "")
    directory = "tools/firefox" if name == "firefox" and sys.platform == "win32" else "tools/bin"
    executable = Path(bundle) / directory / filename
    return str(executable) if executable.is_file() and os.access(executable, os.X_OK) else None


def hidden_process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def portable_data_directory() -> Path | None:
    bundle = os.environ.get("VIDEODOWNLOADER_BUNDLE_ROOT")
    return Path(bundle) / "data" if bundle else None


def temporary_directory() -> str | None:
    data = portable_data_directory()
    if data is None:
        return None
    directory = data / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


def remove_temporary_directory(directory: Path) -> None:
    """Remove extension storage even when Windows paths exceed MAX_PATH."""
    path = str(directory.resolve())
    if sys.platform == "win32":
        path = "\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path
    for attempt in range(20):
        try:
            shutil.rmtree(path)
            return
        except OSError as exc:
            # Browser shutdown and Windows security scanners can briefly retain
            # a handle. Retry only sharing/lock violations, with a bounded wait.
            if sys.platform != "win32" or getattr(exc, "winerror", None) not in {32, 33} or attempt == 19:
                raise
            time.sleep(0.1)
