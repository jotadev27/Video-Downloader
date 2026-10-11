from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from video_downloader.infrastructure.runtime import portable_data_directory


class QtSettingsStore:
    def __init__(self) -> None:
        data = portable_data_directory()
        if data is not None:
            data.mkdir(parents=True, exist_ok=True)
            self._settings = QSettings(str(data / "settings.ini"), QSettings.IniFormat)
        else:
            self._settings = QSettings("VideoDownloader", "VideoDownloader")
        self._settings.remove("proxy_url")
        self._session_proxy: str | None = None

    @property
    def download_directory(self) -> Path:
        data = portable_data_directory()
        default = str(data / "downloads") if data else QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        stored = self._settings.value("download_directory", default, str)
        return Path(stored)

    @download_directory.setter
    def download_directory(self, value: Path) -> None:
        self._settings.setValue("download_directory", str(value))

    @property
    def proxy_url(self) -> str | None:
        return self._session_proxy

    @proxy_url.setter
    def proxy_url(self, value: str | None) -> None:
        self._session_proxy = value
