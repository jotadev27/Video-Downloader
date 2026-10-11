from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from video_downloader.application.ports import SettingsStore
from video_downloader.domain.models import validate_proxy_url
from video_downloader.presentation.icons import set_action_icon


class SettingsDialog(QDialog):
    def __init__(self, settings: SettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)

        title = QLabel("Download settings")
        title.setObjectName("videoTitle")

        self.directory_edit = QLineEdit(str(settings.download_directory))
        self.directory_edit.setReadOnly(True)
        browse = QPushButton("Browse")
        browse.setObjectName("secondary")
        set_action_icon(browse, "folder")
        browse.clicked.connect(self._choose_directory)
        directory_row = QHBoxLayout()
        directory_row.setContentsMargins(0, 0, 0, 0)
        directory_row.addWidget(self.directory_edit, 1)
        directory_row.addWidget(browse)
        directory_widget = QWidget()
        directory_widget.setLayout(directory_row)

        self.proxy_edit = QLineEdit(settings.proxy_url or "")
        self.proxy_edit.setPlaceholderText("Optional — socks5://127.0.0.1:1080")
        self.proxy_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        form.addRow("Save to", directory_widget)
        form.addRow("Proxy", self.proxy_edit)

        note = QLabel(
            "The proxy is kept in memory for this session only. Leave it blank to use "
            "the normal system connection."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        set_action_icon(buttons.button(QDialogButtonBox.Cancel), "cancel")
        set_action_icon(buttons.button(QDialogButtonBox.Save), "save")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(20)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.directory_edit.text()
        )
        if selected:
            self.directory_edit.setText(selected)

    def _save(self) -> None:
        try:
            proxy = validate_proxy_url(self.proxy_edit.text())
        except ValueError as exc:
            self.proxy_edit.setFocus()
            self.proxy_edit.setToolTip(str(exc))
            self.proxy_edit.setStyleSheet("border-color: #EF4444;")
            return
        self._settings.download_directory = Path(self.directory_edit.text())
        self._settings.proxy_url = proxy
        self.accept()
