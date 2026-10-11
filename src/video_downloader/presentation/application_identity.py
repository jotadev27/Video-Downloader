"""Keep native window, taskbar, and desktop launcher identity consistent."""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

APPLICATION_ID = "jotadev27.VideoDownloader"


def configure_windows_identity() -> None:
    if sys.platform == "win32":
        # Set before Qt creates native windows. Shortcuts use the same ID so
        # Windows groups the launcher and its application under the right icon.
        shell32 = ctypes.WinDLL("shell32")
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        if shell32.SetCurrentProcessExplicitAppUserModelID(APPLICATION_ID) != 0:
            raise OSError("Could not configure the Windows application identity")


def configure_application_icon(application: QApplication, assets: Path) -> None:
    icon = QIcon(str(assets / "desktop-icon.svg"))
    if icon.isNull():
        raise RuntimeError("The application icon is missing")
    application.setWindowIcon(icon)
    application.setDesktopFileName("videodownloader")
