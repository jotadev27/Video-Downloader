from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from video_downloader.domain.models import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    VideoInfo,
)

ProgressCallback = Callable[[DownloadProgress], None]
CancellationCheck = Callable[[], bool]


class VideoValidator(Protocol):
    """Validate staged content without exposing platform tools to workflows."""

    def available(self) -> bool: ...

    def validate(self, path: Path, is_cancelled: CancellationCheck) -> int: ...


class VideoGateway(Protocol):
    def inspect(self, url: str, proxy_url: str | None = None) -> VideoInfo: ...

    def download(
        self,
        request: DownloadRequest,
        on_progress: ProgressCallback,
        is_cancelled: CancellationCheck,
    ) -> DownloadResult: ...


class SettingsStore(Protocol):
    @property
    def download_directory(self) -> Path: ...

    @download_directory.setter
    def download_directory(self, value: Path) -> None: ...

    @property
    def proxy_url(self) -> str | None: ...

    @proxy_url.setter
    def proxy_url(self, value: str | None) -> None: ...
