from __future__ import annotations

import os
import time
from collections.abc import Mapping
from copy import deepcopy
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any

from video_downloader.application.ports import CancellationCheck, ProgressCallback
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    ProgressState,
    VideoInfo,
    VideoQuality,
)
from video_downloader.infrastructure.firefox_media_resolver import (
    FirefoxMediaResolver,
    ResolvedMedia,
)
from video_downloader.infrastructure.network_guard import PublicNetworkGuard
from video_downloader.infrastructure.runtime import find_tool

# Third-party yt-dlp plugins execute arbitrary Python at import time. VideoDownloader
# deliberately supports only the bundled built-in extractor set.
os.environ["YTDLP_NO_PLUGINS"] = "1"


class DownloadCancelled(AppError):
    """Raised from a progress hook when the user cancels a download."""

    def __init__(self) -> None:
        super().__init__(ErrorCode.CANCELLED, "The download was cancelled.")


class _SilentYtDlpLogger:
    """Keep source URLs and engine diagnostics out of the user's terminal."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class YtDlpGateway:
    def __init__(
        self,
        firefox_resolver: FirefoxMediaResolver | None = None,
        network_guard: PublicNetworkGuard | None = None,
    ) -> None:
        self._network_guard = network_guard or PublicNetworkGuard()
        self._firefox_resolver = firefox_resolver or FirefoxMediaResolver(
            network_guard=self._network_guard
        )
        self._resolved_media: dict[str, ResolvedMedia] = {}
        self._inspection: dict[str, Any] | None = None
        self._inspection_urls: set[str] = set()
        self._inspection_cookies: tuple[Cookie, ...] = ()
        self._inspection_proxy: str | None = None
        self._inspection_time = 0.0

    def _module(self):
        try:
            import yt_dlp
        except ImportError as exc:
            raise AppError(
                ErrorCode.ENGINE,
                "The yt-dlp engine is not installed. Run: python -m pip install -e ."
            ) from exc
        return yt_dlp

    @staticmethod
    def _base_options(proxy_url: str | None) -> dict[str, Any]:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        options: dict[str, Any] = {
            "quiet": True,
            "ignoreconfig": True,
            "cachedir": False,
            "no_warnings": True,
            "noprogress": True,
            "logger": _SilentYtDlpLogger(),
            # Use the maintained curl-cffi transport with a Firefox fingerprint.
            # This does not open a browser or access browser profiles/cookies.
            "impersonate": ImpersonateTarget.from_str("firefox"),
            "extractor_args": {"generic": {"impersonate": []}},
            "noplaylist": True,
            "extract_flat": False,
            "socket_timeout": 15,
            "retries": 2,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 8,
            "skip_unavailable_fragments": False,
            # Keep VOD HLS fetching in yt-dlp's native transport. The bundled
            # FFmpeg input protocols are restricted to local processing below.
            "hls_prefer_native": True,
            "match_filter": YtDlpGateway._safe_media_filter,
            # FFmpeg only processes downloaded files. Network requests must go
            # through the guarded native transport, including HLS fragments.
            "postprocessor_args": {"ffmpeg_i": ["-protocol_whitelist", "file,pipe,crypto,data"]},
            "windowsfilenames": True,
            "restrictfilenames": False,
            "nopart": False,
            "enable_file_urls": False,
            "js_runtimes": {},
        }
        node = find_tool("node")
        if node:
            options["js_runtimes"] = {"node": {"path": node}}
        ffmpeg = find_tool("ffmpeg")
        if ffmpeg:
            options["ffmpeg_location"] = str(Path(ffmpeg).parent)
        if proxy_url:
            options["proxy"] = proxy_url
        return options

    @staticmethod
    def _safe_media_filter(info, *, incomplete=False):
        if incomplete:
            return None
        if info.get("is_live") or info.get("live_status") == "is_live":
            raise AppError(ErrorCode.FORMAT_UNAVAILABLE,
                           "Live streams are unavailable in this portable. Use a recorded video link.")
        protocol = str(info.get("protocol") or "")
        native_protocols = {"http", "https", "m3u8", "m3u8_native", "http_dash_segments", "m3u8_frag_urls"}
        if protocol and any(part not in native_protocols for part in protocol.split("+")):
            raise AppError(ErrorCode.FORMAT_UNAVAILABLE,
                           "This video requires a network downloader that cannot apply the link protections.")
        return None

    def inspect(self, url: str, proxy_url: str | None = None) -> VideoInfo:
        self._clear_inspection()
        if hasattr(self._network_guard, "prepare"):
            self._network_guard.prepare(proxy_url)
        self._network_guard.ensure_public(url)
        yt_dlp = self._module()
        options = self._base_options(proxy_url) | {"skip_download": True}
        try:
            with yt_dlp.YoutubeDL(options) as client:
                self._guard_client(client)
                raw = self._extract_info(client, url, download=False)
                self._inspection_cookies = tuple(
                    deepcopy(cookie) for cookie in getattr(client, "cookiejar", ())
                )
        except AppError:
            raise
        except Exception as exc:
            error = self._app_error(exc)
            if error.code != ErrorCode.VERIFICATION_REQUIRED:
                raise error from exc
            resolved = self._firefox_resolver.resolve(url, proxy_url)
            self._resolved_media[url] = resolved
            self._resolved_media[resolved.page_url] = resolved
            self._remember_inspection(url, resolved.page_url, proxy_url)
            height = resolved.height or 0
            return VideoInfo(
                title=resolved.title,
                webpage_url=url,
                duration_seconds=resolved.duration_seconds,
                uploader=None,
                qualities=(VideoQuality(height, resolved.estimated_bytes),),
                thumbnail_url=resolved.thumbnail_url,
            )
        if raw is None:
            raise AppError(ErrorCode.NOT_FOUND, "The source returned no video information.")
        if raw.get("_type") in {"playlist", "multi_video"}:
            entries = [entry for entry in raw.get("entries", []) if entry]
            if not entries:
                raise AppError(
                    ErrorCode.FORMAT_UNAVAILABLE,
                    "The source did not expose a downloadable video.",
                )
            raw = entries[0]
        formats = raw.get("formats") or []
        qualities = self._collect_qualities(formats)
        if not qualities and self._has_video_source(formats):
            qualities = (VideoQuality(0, self._as_int(raw.get("filesize"))),)
        webpage_url = str(raw.get("webpage_url") or url)
        self._inspection = deepcopy(raw)
        self._remember_inspection(url, webpage_url, proxy_url)
        return VideoInfo(
            title=str(raw.get("title") or "Untitled video"),
            webpage_url=webpage_url,
            duration_seconds=self._as_int(raw.get("duration")),
            uploader=self._optional_text(raw.get("uploader") or raw.get("channel")),
            qualities=qualities,
            thumbnail_url=self._optional_text(raw.get("thumbnail")),
        )

    def _remember_inspection(self, url: str, webpage_url: str, proxy: str | None) -> None:
        self._inspection_urls = {url, webpage_url}
        self._inspection_proxy = proxy
        self._inspection_time = time.monotonic()

    @staticmethod
    def _extract_info(client, url: str, download: bool):
        from video_downloader.infrastructure.njav_extractor import NjavIE

        if NjavIE.supports(url):
            return client.process_ie_result(NjavIE(client).extract(url), download=download)
        return client.extract_info(url, download=download)

    def _guard_client(self, client) -> None:
        if not hasattr(client, "urlopen"):
            return
        protected_transport = hasattr(client, "build_request_director")
        if protected_transport:
            from video_downloader.infrastructure.guarded_http import configure_guarded_transport
            configure_guarded_transport(client, self._network_guard.ensure_public)
        original_open = client.urlopen

        def guarded_open(request):
            url = request if isinstance(request, str) else getattr(request, "url", None)
            if url is None and hasattr(request, "get_full_url"):
                url = request.get_full_url()
            if url and not protected_transport:
                self._network_guard.ensure_public(url)
            try:
                response = original_open(request)
            except Exception as exc:
                cause = getattr(exc, "cause", None)
                if isinstance(cause, AppError):
                    raise cause from exc
                raise
            try:
                # Check the final response too, including test/custom clients.
                if not protected_transport and getattr(response, "url", None):
                    self._network_guard.ensure_public(response.url)
            except AppError:
                response.close()
                raise
            return response

        client.urlopen = guarded_open

    def _clear_inspection(self) -> None:
        self._resolved_media.clear()
        self._inspection = None
        self._inspection_urls.clear()
        self._inspection_cookies = ()

    @staticmethod
    def _unselect_formats(raw: dict[str, Any]) -> dict[str, Any]:
        """Select the user's quality again without repeating page extraction."""
        info = deepcopy(raw)
        for key in ("requested_formats", "requested_downloads", "filepath", "_filename"):
            info.pop(key, None)
        if info.get("formats"):
            for key in (
                "url", "format", "format_id", "ext", "protocol", "height", "width",
                "vcodec", "acodec", "filesize", "filesize_approx", "fps", "tbr", "abr", "vbr",
                "resolution", "dynamic_range", "container", "fragments", "manifest_url",
                "fragment_base_url", "downloader_options",
            ):
                info.pop(key, None)
        return info

    def download(
        self,
        request: DownloadRequest,
        on_progress: ProgressCallback,
        is_cancelled: CancellationCheck,
    ) -> DownloadResult:
        if hasattr(self._network_guard, "prepare"):
            self._network_guard.prepare(request.proxy_url)
        self._network_guard.ensure_public(request.url)
        yt_dlp = self._module()
        final_path: Path | None = None
        matches = request.url in self._inspection_urls and request.proxy_url == self._inspection_proxy
        age = time.monotonic() - self._inspection_time
        resolved = self._resolved_media.get(request.url) if matches else None
        cached = self._inspection if matches and age < 120 else None
        cookies = self._inspection_cookies if matches else ()
        self._clear_inspection()
        if is_cancelled():
            raise DownloadCancelled()
        if resolved and age >= 30:
            on_progress(DownloadProgress(ProgressState.PREPARING, message="Refreshing video session"))
            resolved = self._firefox_resolver.resolve(request.url, request.proxy_url)

        def progress_hook(data: Mapping[str, Any]) -> None:
            nonlocal final_path
            if is_cancelled():
                raise DownloadCancelled()
            status = data.get("status")
            if status == "downloading":
                # yt-dlp continually revises total_bytes_estimate. Only the
                # reported exact total is suitable for a fixed denominator.
                info = data.get("info_dict") or {}
                selected = info.get("requested_formats") or []
                total = (self._as_int(data.get("total_bytes"))
                         if len(selected) <= 1 else None)
                on_progress(
                    DownloadProgress(
                        state=ProgressState.DOWNLOADING,
                        downloaded_bytes=self._as_int(data.get("downloaded_bytes")) or 0,
                        total_bytes=total,
                        bytes_per_second=self._as_float(data.get("speed")),
                        eta_seconds=self._as_int(data.get("eta")),
                        message="Downloading",
                    )
                )
            elif status == "finished":
                filename = data.get("filename")
                if filename:
                    final_path = Path(str(filename))
                on_progress(DownloadProgress(ProgressState.PROCESSING, message="Processing video"))

        def postprocessor_hook(data: Mapping[str, Any]) -> None:
            nonlocal final_path
            if is_cancelled():
                raise DownloadCancelled()
            info = data.get("info_dict") or {}
            filepath = info.get("filepath") or info.get("_filename")
            if filepath:
                final_path = Path(str(filepath))
            if data.get("status") == "started":
                on_progress(DownloadProgress(ProgressState.PROCESSING, message="Finalizing file"))

        on_progress(DownloadProgress(ProgressState.PREPARING, message="Preparing download"))
        for attempt in range(2):
            if is_cancelled():
                raise DownloadCancelled()
            final_path = None
            if resolved:
                from yt_dlp.utils import sanitize_filename

                self._network_guard.ensure_public(resolved.media_url)
                safe_title = sanitize_filename(resolved.title, restricted=False)[:180] or "Video"
                # Titles are literal: a percent sign must not become a yt-dlp field.
                output_template = str(request.target_directory / f"{safe_title.replace('%', '%%')}.%(ext)s")
                selector = self._format_selector(0)
                download_url = resolved.media_url
            else:
                output_template = str(request.target_directory / "%(title).180B [%(id)s].%(ext)s")
                selector = self._format_selector(request.requested_height)
                download_url = request.url
            options = self._base_options(request.proxy_url) | {
                "format": selector,
                "outtmpl": {"default": output_template},
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
                "writethumbnail": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
                "overwrites": False,
                # A refreshed source must not resume fragments from a rejected URL.
                "continuedl": attempt == 0,
            }
            if resolved:
                options["http_headers"] = resolved.headers
            try:
                with yt_dlp.YoutubeDL(options) as client:
                    self._guard_client(client)
                    for cookie in cookies:
                        client.cookiejar.set_cookie(deepcopy(cookie))
                    if resolved:
                        self._load_session_cookies(client, resolved.cookies)
                    if cached and not resolved:
                        raw = client.process_ie_result(self._unselect_formats(cached), download=True)
                    else:
                        raw = self._extract_info(client, download_url, download=True)
                    if raw is None:
                        raise AppError(ErrorCode.NOT_FOUND, "The source returned no download result.")
                    actual_height = self._selected_height(raw) or (
                        resolved.height if resolved else None
                    )
                    # Merged paths live in requested_downloads; the top-level
                    # _filename can still point at an intermediate video stream.
                    downloads = raw.get("requested_downloads") or []
                    candidate = next((item.get("filepath") for item in downloads
                                      if isinstance(item, Mapping) and item.get("filepath")), None)
                    candidate = candidate or raw.get("filepath")
                    if candidate:
                        final_path = Path(str(candidate))
                    if final_path is None:
                        final_path = Path(raw.get("_filename") or client.prepare_filename(raw))
                return DownloadResult(final_path, actual_height, request.requested_height)
            except AppError:
                raise
            except Exception as exc:
                recoverable = (self._expired_source(exc)
                               or self._app_error(exc).code == ErrorCode.VERIFICATION_REQUIRED)
                if attempt or not recoverable:
                    raise self._app_error(exc) from exc
                if is_cancelled():
                    raise DownloadCancelled() from exc
                on_progress(DownloadProgress(ProgressState.PREPARING, message="Refreshing video session"))
                if resolved:
                    resolved = self._firefox_resolver.resolve(request.url, request.proxy_url)
                else:
                    self.inspect(request.url, request.proxy_url)
                    resolved = self._resolved_media.get(request.url)
                    cached = self._inspection
                    cookies = self._inspection_cookies
                    self._clear_inspection()
        raise AppError(ErrorCode.ENGINE, "The download could not be completed.")

    @staticmethod
    def _expired_source(exc: Exception) -> bool:
        lower = str(exc).lower()
        return any(marker in lower for marker in (
            "http error 401", "http error 403", "http error 410", "401 unauthorized",
            "403 forbidden", "410 gone",
        ))

    @staticmethod
    def _load_session_cookies(client, cookies: tuple[dict, ...]) -> None:
        """Transfer only ephemeral browser cookies; never create a cookie file."""
        for item in cookies:
            value = item.get("value") or {}
            if value.get("type") != "string":
                continue
            domain = str(item.get("domain") or "")
            if not domain:
                continue
            client.cookiejar.set_cookie(Cookie(
                version=0, name=str(item.get("name") or ""), value=str(value.get("value") or ""),
                port=None, port_specified=False, domain=domain,
                domain_specified=domain.startswith("."), domain_initial_dot=domain.startswith("."),
                path=str(item.get("path") or "/"), path_specified=True,
                secure=bool(item.get("secure")), expires=None, discard=True,
                comment=None, comment_url=None, rest={},
            ))

    @staticmethod
    def _collect_qualities(formats: list[Mapping[str, Any]]) -> tuple[VideoQuality, ...]:
        by_height: dict[int, VideoQuality] = {}
        for item in formats:
            if item.get("vcodec") in {None, "none"}:
                continue
            height = YtDlpGateway._as_int(item.get("height"))
            if not height or height <= 0:
                continue
            estimated = YtDlpGateway._as_int(item.get("filesize")) or YtDlpGateway._as_int(
                item.get("filesize_approx")
            )
            fps = YtDlpGateway._as_float(item.get("fps"))
            candidate = VideoQuality(height, estimated, fps)
            current = by_height.get(height)
            if current is None or (candidate.estimated_bytes or 0) > (current.estimated_bytes or 0):
                by_height[height] = candidate
        return tuple(by_height[height] for height in sorted(by_height, reverse=True))

    @staticmethod
    def _has_video_source(formats: list[Mapping[str, Any]]) -> bool:
        return any(
            item.get("video_ext") not in {None, "none"}
            or item.get("vcodec") not in {None, "none"}
            for item in formats
        )

    @staticmethod
    def _format_selector(requested_height: int) -> str:
        if requested_height == 0:
            return "bestvideo*+bestaudio/best"
        return (
            f"bestvideo[height={requested_height}]+bestaudio/"
            f"best[height={requested_height}]"
        )

    @staticmethod
    def _selected_height(info: Mapping[str, Any]) -> int | None:
        requested = info.get("requested_downloads") or info.get("requested_formats") or []
        heights = [
            YtDlpGateway._as_int(item.get("height"))
            for item in requested
            if isinstance(item, Mapping) and item.get("vcodec") not in {None, "none"}
        ]
        heights = [height for height in heights if height]
        return max(heights) if heights else YtDlpGateway._as_int(info.get("height"))

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        return YtDlpGateway._app_error(exc).user_message

    @staticmethod
    def _app_error(exc: Exception) -> AppError:
        message = str(exc).strip()
        lower = message.lower()
        if "site is listed as a known threat" in lower:
            return AppError(ErrorCode.SITE_BLOCKED,
                            "This site is listed as a known threat. The request was blocked.")
        if any(marker in lower for marker in (
            "http error 401", "401 unauthorized", "private video", "login", "sign in",
        )):
            return AppError(
                ErrorCode.ACCESS_REQUIRED,
                "The server rejected this video session or requires sign-in. "
                "Inspect the link again. An account may be required for private videos.",
            )
        if any(marker in lower for marker in (
            "unsupported url", "no video formats found", "unable to extract", "http error 403",
        )):
            return AppError(
                ErrorCode.VERIFICATION_REQUIRED,
                "This source is unsupported or requires browser verification. "
                "VideoDownloader does not bypass site protection.",
            )
        if "404" in lower or "not found" in lower or "video is unavailable" in lower:
            return AppError(ErrorCode.NOT_FOUND, "The video could not be found or is unavailable.")
        if "drm" in lower:
            return AppError(
                ErrorCode.DRM_PROTECTED,
                "This video is DRM-protected and cannot be downloaded.",
            )
        if "requested format is not available" in lower:
            return AppError(
                ErrorCode.FORMAT_UNAVAILABLE,
                "The selected quality is no longer available. Inspect the link again.",
            )
        if any(
            marker in lower
            for marker in (
                "timed out",
                "failed to resolve",
                "name resolution",
                "connection refused",
                "failed to connect",
                "could not connect",
                "could not resolve host",
                "ssl certificate problem",
                "network is unreachable",
                "certificate verify failed",
            )
        ):
            return AppError(
                ErrorCode.NETWORK,
                "The source could not be reached. Check the connection or proxy and try again.",
            )
        if any(marker in lower for marker in ("no space", "permission denied", "read-only")):
            return AppError(
                ErrorCode.STORAGE,
                "The file could not be saved. Check free space and folder permissions.",
            )
        if message.startswith("ERROR:"):
            message = message.removeprefix("ERROR:").strip()
        return AppError(
            ErrorCode.ENGINE,
            "The source could not be processed by the download engine.",
        )

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None
