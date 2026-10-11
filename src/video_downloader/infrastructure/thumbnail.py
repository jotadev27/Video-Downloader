"""Load a small public image in a worker without retaining it on disk."""
from __future__ import annotations

from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from video_downloader.domain.models import validate_public_url
from video_downloader.infrastructure.network_guard import PublicNetworkGuard

MAX_IMAGE_BYTES = 4 * 1024 * 1024


class _PublicRedirects(HTTPRedirectHandler):
    def __init__(self, guard: PublicNetworkGuard) -> None:
        super().__init__()
        self._guard = guard
        self._redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._redirects += 1
        if self._redirects > 3:
            raise ValueError("Too many thumbnail redirects")
        self._guard.ensure_public(validate_public_url(newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_thumbnail(url: str, proxy_url: str | None, referrer: str) -> QImage | None:
    """Return a bounded decoded image, or None when the source cannot provide one."""
    try:
        guard = PublicNetworkGuard()
        guard.ensure_public(validate_public_url(url))
        headers = {"User-Agent": "VideoDownloader/0.2", "Accept": "image/avif,image/webp,image/png,image/jpeg"}
        try:
            headers["Referer"] = validate_public_url(referrer)
        except ValueError:
            pass
        proxy = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
        opener = build_opener(ProxyHandler(proxy), _PublicRedirects(guard))
        with opener.open(Request(url, headers=headers), timeout=8) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
                return None
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                return None
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.ReadOnly)
        reader = QImageReader(buffer)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and size.width() * size.height() > 16_000_000:
            return None
        if size.isValid() and (size.width() > 1024 or size.height() > 1024):
            reader.setScaledSize(size.scaled(QSize(1024, 1024), Qt.KeepAspectRatio))
        image = reader.read()
        return image if not image.isNull() else None
    except Exception:
        # Covers unavailable/bad images without exposing private image URLs.
        return None
