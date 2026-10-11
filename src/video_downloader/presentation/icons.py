"""Render local monochrome SVGs for each button surface and Qt state."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

ASSETS = Path(__file__).resolve().parents[1] / "assets/actions"

# Match the button foreground colors in styles.py. All variants retain contrast
# against their corresponding normal, hover, pressed, and disabled surfaces.
PALETTES = {
    "light": ("#344154", "#203656", "#182f4b", "#677384"),
    "primary": ("#ffffff", "#ffffff", "#ffffff", "#536170"),
    "link": ("#245ba4", "#174b91", "#123b73", "#677384"),
}


def _render(source: bytes, color: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(source.replace(b"#000000", color.encode("ascii"))))
    if not renderer.isValid():
        raise ValueError("Invalid action icon")
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


@lru_cache(maxsize=48)
def action_icon(name: str, role: str = "light", size: int = 18) -> QIcon:
    if name not in {
        "save", "cancel", "folder", "download", "inspect", "menu", "back",
        "open-folder", "settings",
    }:
        raise ValueError("Unknown action icon")
    source = (ASSETS / f"{name}.svg").read_bytes()
    normal, active, pressed, disabled = PALETTES[role]
    icon = QIcon()
    for mode, color in (
        (QIcon.Normal, normal), (QIcon.Active, active),
        (QIcon.Selected, pressed), (QIcon.Disabled, disabled),
    ):
        icon.addPixmap(_render(source, color, size), mode)
    return icon


def set_action_icon(button: QPushButton, name: str, role: str = "light") -> None:
    button.setIcon(action_icon(name, role))
    button.setIconSize(QSize(18, 18))
