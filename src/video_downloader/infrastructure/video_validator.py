from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from video_downloader.application.ports import CancellationCheck
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.runtime import (
    find_tool,
    hidden_process_options,
    temporary_directory,
)


class VideoValidator:
    """Confirm a local video container and video stream without scanning its whole size."""

    def __init__(self, executable: str | None = None, timeout_seconds: float = 30) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def _find_executable(self) -> str | None:
        if self._executable:
            return self._executable
        return find_tool("ffprobe")

    def available(self) -> bool:
        return self._find_executable() is not None

    def validate(self, path: Path, is_cancelled: CancellationCheck) -> int:
        executable = self._find_executable()
        if not executable:
            raise AppError(ErrorCode.ENGINE,
                           "FFprobe is missing. Restore the complete application package.")
        if is_cancelled():
            raise AppError(ErrorCode.CANCELLED, "The download was cancelled.")
        command = [
            executable, "-v", "error", "-max_alloc", "67108864",
            "-protocol_whitelist", "file",
            "-format_whitelist", "mov,matroska,webm,avi,mpegts",
            "-probesize", "5242880", "-analyzeduration", "5000000",
            # Uppercase V excludes attached pictures and album artwork.
            "-select_streams", "V",
            "-show_entries", "format=format_name:stream=codec_type,codec_name,width,height",
            "-of", "json", str(path.resolve()),
        ]
        # A temporary output file avoids pipe deadlocks and allows cancellation.
        # Never expose diagnostics that could contain a source's filename or tags.
        with tempfile.TemporaryFile(dir=temporary_directory()) as output:
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=output, stderr=subprocess.DEVNULL, shell=False,
                                           **hidden_process_options())
            except OSError as exc:
                raise AppError(ErrorCode.ENGINE, "FFprobe could not start.") from exc
            try:
                deadline = time.monotonic() + self._timeout_seconds
                while process.poll() is None:
                    if is_cancelled():
                        raise AppError(ErrorCode.CANCELLED, "The download was cancelled.")
                    if time.monotonic() >= deadline:
                        raise AppError(ErrorCode.FORMAT_UNAVAILABLE,
                                       "Video validation timed out. The file was not saved.")
                    time.sleep(0.05)
                if is_cancelled():
                    raise AppError(ErrorCode.CANCELLED, "The download was cancelled.")
                output.seek(0)
                payload = output.read(512 * 1024 + 1)
                if process.returncode or len(payload) > 512 * 1024:
                    raise self._invalid_video()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        try:
            metadata = json.loads(payload)
            formats = set(metadata["format"]["format_name"].split(","))
            if not formats.intersection({"mov", "mp4", "matroska", "webm", "avi", "mpegts"}):
                raise ValueError("Unsupported container")
            heights = [int(stream["height"]) for stream in metadata["streams"]
                       if stream.get("codec_type") == "video"
                       and stream.get("codec_name") not in {None, "unknown", "none"}
                       and int(stream.get("width") or 0) > 0
                       and int(stream.get("height") or 0) > 0]
            if not heights:
                raise ValueError("No usable video stream")
            return max(heights)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise self._invalid_video() from exc

    @staticmethod
    def _invalid_video() -> AppError:
        return AppError(ErrorCode.FORMAT_UNAVAILABLE,
                        "The downloaded file is not a recognized video with a usable video stream. "
                        "The file was not saved.")
