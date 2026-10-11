import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from video_downloader.presentation.icons import PALETTES, action_icon
from video_downloader.presentation.main_window import MainWindow
from video_downloader.presentation.settings_dialog import SettingsDialog


class Settings:
    download_directory = Path("/tmp")
    proxy_url = None


class IconContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _opaque_colors(icon: QIcon, mode: QIcon.Mode) -> set[str]:
        image = icon.pixmap(QSize(18, 18), mode).toImage()
        return {image.pixelColor(x, y).name().lower()
                for y in range(image.height()) for x in range(image.width())
                if image.pixelColor(x, y).alpha() == 255}

    def test_every_action_has_visible_normal_hover_pressed_disabled_icon(self):
        for name in ("save", "cancel", "folder", "download", "inspect", "menu",
                     "back", "open-folder", "settings"):
            for role in ("light", "primary", "link"):
                icon = action_icon(name, role)
                for mode, color in zip((QIcon.Normal, QIcon.Active, QIcon.Selected,
                                        QIcon.Disabled), PALETTES[role]):
                    with self.subTest(name=name, role=role, mode=mode):
                        self.assertIn(color, self._opaque_colors(icon, mode))

    def test_dialog_and_main_controls_have_icons_on_matching_surfaces(self):
        from video_downloader.presentation.styles import APP_STYLE
        self.app.setStyle("Fusion")
        self.app.setStyleSheet(APP_STYLE)
        window = MainWindow(None, None, Settings(),
                            Path("src/video_downloader/assets/VideoDownloader.png"))
        dialog = SettingsDialog(Settings(), window)
        try:
            box = dialog.findChild(QDialogButtonBox)
            for standard in (QDialogButtonBox.Save, QDialogButtonBox.Cancel):
                button = box.button(standard)
                self.assertFalse(button.icon().isNull())
                self.assertIn(PALETTES["light"][0], self._opaque_colors(button.icon(), QIcon.Normal))
            for button in window.findChildren(QPushButton):
                self.assertFalse(button.icon().isNull(), button.text())
        finally:
            dialog.close()
            window.close()


if __name__ == "__main__":
    unittest.main()
