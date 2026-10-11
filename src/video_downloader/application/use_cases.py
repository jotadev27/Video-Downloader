from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from video_downloader.application.ports import (
    CancellationCheck,
    ProgressCallback,
    VideoGateway,
    VideoValidator,
)
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    ProgressState,
    VideoInfo,
    validate_proxy_url,
    validate_public_url,
)


class InspectVideo:
    def __init__(self, gateway: VideoGateway) -> None:
        self._gateway = gateway

    def execute(self, url: str, proxy_url: str | None = None) -> VideoInfo:
        try:
            safe_url = validate_public_url(url)
            safe_proxy = validate_proxy_url(proxy_url)
        except ValueError as exc:
            raise AppError(ErrorCode.INVALID_LINK, str(exc)) from exc
        info = self._gateway.inspect(safe_url, safe_proxy)
        if not info.qualities:
            raise AppError(
                ErrorCode.FORMAT_UNAVAILABLE,
                "The source did not report any downloadable video formats.",
            )
        return info


class DownloadVideo:
    def __init__(self, gateway: VideoGateway, validator: VideoValidator) -> None:
        self._gateway = gateway
        self._validator = validator

    def execute(
        self,
        url: str,
        target_directory: Path,
        requested_height: int,
        proxy_url: str | None,
        on_progress: ProgressCallback,
        is_cancelled: CancellationCheck,
    ) -> DownloadResult:
        if requested_height < 0:
            raise AppError(ErrorCode.FORMAT_UNAVAILABLE, "Select a valid video quality.")
        try:
            safe_url = validate_public_url(url)
            safe_proxy = validate_proxy_url(proxy_url)
        except ValueError as exc:
            raise AppError(ErrorCode.INVALID_LINK, str(exc)) from exc
        target = target_directory.expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppError(
                ErrorCode.STORAGE,
                "The download folder could not be created or is not writable.",
            ) from exc
        if not self._validator.available():
            if os.environ.get("VIDEODOWNLOADER_BUNDLE_ROOT"):
                message = (
                    "FFprobe is missing. Copy the entire installer folder, "
                    "including tools and VideoDownloader/_internal, then open the app again."
                )
            else:
                message = "FFprobe is required to validate videos. Install FFmpeg and FFprobe."
            raise AppError(
                ErrorCode.ENGINE,
                message,
            )
        if is_cancelled():
            raise AppError(ErrorCode.CANCELLED, "The download was cancelled.")
        # Keep intermediate files disposable until their video format is verified.
        with tempfile.TemporaryDirectory(prefix=".videodownloader-download-", dir=target) as staging_name:
            staging = Path(staging_name)
            request = DownloadRequest(safe_url, staging, requested_height, safe_proxy)
            on_progress(DownloadProgress(ProgressState.PREPARING, message="Checking site protection"))
            result = self._gateway.download(request, on_progress, is_cancelled)
            candidate = result.file_path
            try:
                if candidate.parent.resolve() != staging.resolve():
                    raise ValueError("Download escaped the staging directory")
                metadata = candidate.lstat()
                if not stat.S_ISREG(metadata.st_mode) or candidate.is_symlink():
                    raise ValueError("Download is not a regular file")
                if candidate.suffix.lower() not in {
                    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts"
                }:
                    raise ValueError("Download is not a recognized video file")
            except (OSError, ValueError) as exc:
                raise AppError(
                    ErrorCode.STORAGE, "The download did not produce a safe video file."
                ) from exc
            on_progress(DownloadProgress(ProgressState.PROCESSING, message="Validating video format"))
            actual_height = self._validator.validate(candidate, is_cancelled)
            if is_cancelled():
                raise AppError(ErrorCode.CANCELLED, "The download was cancelled.")
            # Windows rename is atomic and refuses to overwrite existing files,
            # including on USB filesystems that cannot create hard links.
            for index in range(1000):
                suffix = f" ({index})" if index else ""
                destination = target / f"{candidate.stem}{suffix}{candidate.suffix}"
                try:
                    if os.name == "nt":
                        os.rename(candidate, destination)
                    else:
                        os.link(candidate, destination, follow_symlinks=False)
                    on_progress(DownloadProgress(ProgressState.FINISHED, message="Download complete"))
                    return DownloadResult(destination, actual_height, result.requested_height)
                except FileExistsError:
                    continue
                except OSError as exc:
                    raise AppError(ErrorCode.STORAGE, "The validated video could not be saved.") from exc
            raise AppError(ErrorCode.STORAGE, "Too many files with the same name exist.")
