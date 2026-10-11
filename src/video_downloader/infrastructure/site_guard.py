from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import idna

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.runtime import portable_data_directory

FEED_URL = "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/tif.mini-onlydomains.txt"
MAX_FEED_BYTES = 8 * 1024 * 1024
UPDATE_INTERVAL = 8 * 3600


class SiteGuard:
    """Match known malicious domains locally; never submit browsing URLs to a service."""

    def __init__(self, cache_directory: Path | None = None, bundled_list: Path | None = None) -> None:
        data = portable_data_directory()
        if data is None:
            data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "VideoDownloader"
        self._cache = (cache_directory or data / "site-protection") / "threat-domains.txt"
        self._bundled = bundled_list or Path(__file__).resolve().parents[1] / "assets/threat-domains.txt"
        self._domains: frozenset[str] = frozenset()
        self._checked_at = 0.0
        self._attempted_at = 0.0
        self._lock = threading.RLock()
        self._status = "Site protection: known-threat check runs when you inspect a link"

    @property
    def status(self) -> str:
        return self._status

    @staticmethod
    def _hostname(value: str) -> str:
        value = value.strip().lower().rstrip(".")
        try:
            if not value.isascii():
                value = idna.encode(value, uts46=True).decode("ascii")
        except (UnicodeError, idna.IDNAError):
            return ""
        if len(value) > 253 or "." not in value:
            return ""
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
               for label in value.split(".")):
            return ""
        return value

    @classmethod
    @lru_cache(maxsize=2)
    def _parse(cls, payload: bytes) -> frozenset[str]:
        if len(payload) > MAX_FEED_BYTES:
            raise ValueError("Threat list is too large")
        text = payload.decode("utf-8")
        # Reject HTML error pages and unrelated responses instead of caching them.
        if "# Title: HaGeZi's Threat Intelligence Feeds" not in text:
            raise ValueError("Unexpected threat list")
        domains = frozenset(host for line in text.splitlines()
                            if line and not line.startswith("#")
                            and (host := cls._hostname(line)))
        if len(domains) < 50:
            raise ValueError("Incomplete threat list")
        return domains

    def _load(self) -> None:
        if self._domains:
            return
        for path in (self._cache, self._bundled):
            try:
                with path.open("rb") as file:
                    domains = self._parse(file.read(MAX_FEED_BYTES + 1))
                self._domains = domains
                self._checked_at = path.stat().st_mtime
                break
            except (OSError, ValueError):
                continue

    @staticmethod
    def _fetch(proxy_url: str | None) -> bytes:
        from curl_cffi import requests

        # Only the fixed public list is requested. Neither the video URL nor its
        # hostname is sent to the list provider. Respect the session proxy.
        with requests.Session(trust_env=False) as session:
            response = session.get(FEED_URL, proxy=proxy_url, impersonate="firefox", timeout=8,
                                   allow_redirects=False, stream=True)
            try:
                response.raise_for_status()
                content = bytearray()
                deadline = time.monotonic() + 12
                for chunk in response.iter_content(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > MAX_FEED_BYTES or time.monotonic() > deadline:
                        raise ValueError("Threat-list download exceeded its limit")
                return bytes(content)
            finally:
                response.close()

    def prepare(self, proxy_url: str | None = None, force: bool = False) -> None:
        with self._lock:
            self._load()
            now = time.time()
            if not force and self._domains and 0 <= now - self._checked_at < UPDATE_INTERVAL:
                self._status = "Site protection: known-threat list available"
                return
            if not force and self._domains and now - self._attempted_at < 600:
                return
            self._attempted_at = now
            try:
                payload = self._fetch(proxy_url)
                domains = self._parse(payload)
                self._cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=self._cache.parent, delete=False) as file:
                        temporary = Path(file.name)
                        file.write(payload)
                    os.replace(temporary, self._cache)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                self._domains = domains
                self._checked_at = now
                self._status = "Site protection: known-threat list updated"
            except Exception as exc:
                if not self._domains:
                    self._status = "Site protection unavailable: no threat list"
                    raise AppError(ErrorCode.PROTECTION_UNAVAILABLE,
                                   "The site threat list is unavailable. Restore the application "
                                   "or update site protection before downloading.") from exc
                self._status = "Site protection: cached list · update unavailable"
                if force:
                    raise AppError(ErrorCode.PROTECTION_UNAVAILABLE,
                                   "The threat-list update failed. The previous list is still in use.") from exc

    def ensure_allowed(self, url: str) -> None:
        with self._lock:
            self._load()
            if not self._domains:
                raise AppError(ErrorCode.PROTECTION_UNAVAILABLE,
                               "The site threat list is missing. Update site protection.")
            host = self._hostname(urlsplit(url).hostname or "")
            labels = host.split(".")
            if host and any(".".join(labels[index:]) in self._domains
                            for index in range(len(labels) - 1)):
                raise AppError(ErrorCode.SITE_BLOCKED,
                               "This site is listed as a known threat (malware, phishing or scam). "
                               "The request was blocked.")
