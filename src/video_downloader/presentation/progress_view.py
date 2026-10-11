"""Turn measured download samples into honest, readable progress."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from video_downloader.domain.models import DownloadProgress, format_bytes, format_duration


@dataclass(frozen=True)
class ProgressView:
    details: str
    fraction: float | None


class ProgressPresenter:
    def __init__(self) -> None:
        self._total: int | None = None
        self._total_invalid = False
        self._smoothed_speed: float | None = None
        self._smoothed_source_eta: float | None = None
        self._last_time: float | None = None
        self._last_eta_time: float | None = None
        self._last_bytes = 0

    def update(self, progress: DownloadProgress, now: float | None = None) -> ProgressView:
        now = time.monotonic() if now is None else now
        downloaded = max(0, progress.downloaded_bytes)
        reported = progress.total_bytes
        if downloaded < self._last_bytes and self._last_bytes:
            # yt-dlp can start a second stream with its own byte counter.
            self._total_invalid = True
            self._total = None
            self._smoothed_speed = None
        self._last_bytes = downloaded
        if not self._total_invalid and reported and reported > 0 and self._total is None:
            self._total = reported
        elif self._total is not None and reported and reported > 0 and reported != self._total:
            # Contradictory totals mean the source did not provide a reliable
            # whole-download size. Do not keep presenting the first as exact.
            self._total_invalid = True
            self._total = None
        if self._total and downloaded > self._total:
            self._total_invalid = True
            self._total = None

        raw_speed = progress.bytes_per_second
        if raw_speed is not None and raw_speed > 0:
            if self._smoothed_speed is None or self._last_time is None:
                self._smoothed_speed = raw_speed
            else:
                delta = max(0.0, now - self._last_time)
                weight = 1 - math.exp(-math.log(2) * delta / 6.0)
                self._smoothed_speed += weight * (raw_speed - self._smoothed_speed)
            self._last_time = now

        source_eta = progress.eta_seconds
        if source_eta is not None and source_eta >= 0:
            if self._smoothed_source_eta is None or self._last_eta_time is None:
                self._smoothed_source_eta = float(source_eta)
            else:
                delta = max(0.0, now - self._last_eta_time)
                predicted = max(0.0, self._smoothed_source_eta - delta)
                weight = 1 - math.exp(-math.log(2) * delta / 6.0)
                self._smoothed_source_eta = predicted + weight * (source_eta - predicted)
            self._last_eta_time = now

        speed_text = f"{format_bytes(raw_speed)}/s" if raw_speed is not None and raw_speed > 0 else "—"
        if self._total is None:
            eta_text = (f"≈{format_duration(math.ceil(self._smoothed_source_eta))} remaining · "
                        if source_eta is not None and self._smoothed_source_eta is not None else "")
            return ProgressView(
                f"{eta_text}{format_bytes(downloaded)} downloaded · total unknown · {speed_text}", None
            )
        remaining = max(0, self._total - downloaded)
        eta = (format_duration(math.ceil(remaining / self._smoothed_speed))
               if self._smoothed_speed and remaining else "—")
        return ProgressView(
            f"{eta} remaining · {format_bytes(downloaded)} of {format_bytes(self._total)} "
            f"({speed_text})",
            min(0.99, downloaded / self._total),
        )
