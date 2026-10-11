from __future__ import annotations

import re
from urllib.parse import urlsplit

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import PACKED_CODES_RE, ExtractorError, decode_packed_codes


class NjavIE(InfoExtractor):
    """Read the public HLS source without executing the page's packed JavaScript."""

    IE_NAME = "njav"
    _VALID_URL = r"https?://(?:www\.)?njavtv\.com/(?:[a-z]{2}/)?(?P<id>[\w-]+)(?:[/?#]|$)"

    @staticmethod
    def supports(url: str) -> bool:
        return urlsplit(url).hostname in {"njavtv.com", "www.njavtv.com"} and NjavIE.suitable(url)

    @staticmethod
    def manifest_from_page(webpage: str) -> str:
        if len(webpage) > 2 * 1024 * 1024:
            raise ExtractorError("Player page exceeds the supported size", expected=True)
        for match in re.finditer(PACKED_CODES_RE, webpage):
            code, base, count, symbols = match.groups()
            # Bound the decoder and reject malformed tables. This is text
            # substitution, never eval/exec or execution of site JavaScript.
            if len(code) > 256 * 1024 or len(base) > 2 or len(count) > 4:
                continue
            if not 2 <= int(base) <= 62:
                continue
            if not 1 <= int(count) <= min(4096, len(symbols.split("|"))):
                continue
            try:
                decoded = decode_packed_codes(match.group())
            except (ValueError, IndexError):
                continue
            source = re.search(r"\bsource\s*=\s*\\?(['\"])(https?://[^'\"\\\s]+)\\?\1", decoded)
            if source and urlsplit(source[2]).path.lower().endswith(".m3u8"):
                return source[2]
        raise ExtractorError("Unable to extract this player's public HLS source", expected=True)

    def _real_extract(self, url: str) -> dict:
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        manifest = self.manifest_from_page(webpage)
        headers = {"Referer": url}
        formats = self._extract_m3u8_formats(manifest, video_id, "mp4", m3u8_id="hls", headers=headers)
        for item in formats:
            item["http_headers"] = headers | (item.get("http_headers") or {})
        return {
            "id": video_id,
            "title": self._og_search_title(webpage, default=video_id),
            "thumbnail": self._og_search_thumbnail(webpage, default=None),
            "webpage_url": url,
            "original_url": url,
            "extractor": self.IE_NAME,
            "extractor_key": self.ie_key(),
            "http_headers": headers,
            "formats": formats,
        }
