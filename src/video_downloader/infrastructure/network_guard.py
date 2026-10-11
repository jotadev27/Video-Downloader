from __future__ import annotations

import socket
from ipaddress import ip_address
from urllib.parse import urlparse

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import validate_public_url
from video_downloader.infrastructure.site_guard import SiteGuard


class PublicNetworkGuard:
    """Reject hosts that resolve to loopback, private, link-local, or reserved IPs."""

    def __init__(self, site_guard: SiteGuard | None = None) -> None:
        self._site_guard = site_guard or SiteGuard()

    @property
    def protection_status(self) -> str:
        return self._site_guard.status

    def prepare(self, proxy_url: str | None = None) -> None:
        self._site_guard.prepare(proxy_url)

    def ensure_safe(self, url: str) -> None:
        self._site_guard.ensure_allowed(url)

    def ensure_public(self, url: str) -> None:
        try:
            url = validate_public_url(url)
        except ValueError as exc:
            raise AppError(ErrorCode.INVALID_LINK, str(exc)) from exc
        self.ensure_safe(url)
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise AppError(ErrorCode.INVALID_LINK, "The URL does not contain a valid host.")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise AppError(ErrorCode.INVALID_LINK, "The URL contains an invalid port.") from exc
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise AppError(
                ErrorCode.NETWORK,
                "The source host could not be resolved. Check the address and connection.",
            ) from exc
        addresses = {record[4][0].split("%", 1)[0] for record in records}
        if not addresses:
            raise AppError(ErrorCode.NETWORK, "The source host returned no network address.")
        if any(not ip_address(address).is_global for address in addresses):
            raise AppError(
                ErrorCode.INVALID_LINK,
                "Links that resolve to private or local networks are not accepted.",
            )
