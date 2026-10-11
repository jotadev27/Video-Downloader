from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse


class ProgressState(str, Enum):
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class VideoQuality:
    height: int
    estimated_bytes: int | None = None
    fps: float | None = None

    @property
    def label(self) -> str:
        if self.height == 0:
            return "Source quality"
        size = f" · approx. {format_bytes(self.estimated_bytes)}" if self.estimated_bytes else ""
        fps = f" · {round(self.fps)} fps" if self.fps else ""
        return f"{self.height}p{fps}{size}"


@dataclass(frozen=True, slots=True)
class VideoInfo:
    title: str
    webpage_url: str
    duration_seconds: int | None
    uploader: str | None
    qualities: tuple[VideoQuality, ...]
    thumbnail_url: str | None = None

    @property
    def maximum_height(self) -> int:
        return max(quality.height for quality in self.qualities)

    @property
    def minimum_height(self) -> int:
        return min(quality.height for quality in self.qualities)


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    url: str
    target_directory: Path
    requested_height: int
    proxy_url: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    state: ProgressState
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    bytes_per_second: float | None = None
    eta_seconds: int | None = None
    message: str = ""

    @property
    def percent(self) -> float | None:
        if not self.total_bytes or self.total_bytes <= 0:
            return None
        return min(100.0, max(0.0, self.downloaded_bytes / self.total_bytes * 100))


@dataclass(frozen=True, slots=True)
class DownloadResult:
    file_path: Path
    actual_height: int | None
    requested_height: int

    @property
    def quality_matches(self) -> bool:
        return (
            self.requested_height == 0
            or self.actual_height is None
            or self.actual_height == self.requested_height
        )


def validate_public_url(value: str) -> str:
    url = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in url) or "\\" in url:
        raise ValueError("URLs containing control characters or backslashes are not accepted.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS video URL.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Enter a URL with a valid port number.") from exc
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not accepted.")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Local network addresses are not accepted.")
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("Private and local network addresses are not accepted.")
    return url


def validate_proxy_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    proxy = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in proxy):
        raise ValueError("Proxy URLs containing control characters are not accepted.")
    parsed = urlparse(proxy)
    if parsed.scheme not in {"http", "https", "socks4", "socks5", "socks5h"}:
        raise ValueError("Use an HTTP, HTTPS, SOCKS4, or SOCKS5 proxy URL.")
    if not parsed.hostname:
        raise ValueError("Enter a valid proxy URL.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Enter a proxy URL with a valid port number.") from exc
    return proxy


def format_bytes(value: int | float | None) -> str:
    if value is None or value < 0:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            precision = 0 if unit == "B" else 1
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024
    return "—"


def format_duration(seconds: int | float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
