import tempfile
import unittest
from pathlib import Path

import pytest

from video_downloader.domain.errors import ErrorCode
from video_downloader.domain.models import DownloadRequest
from video_downloader.infrastructure.firefox_media_resolver import ResolvedMedia
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


@pytest.mark.parametrize("protocol,is_live", [("m3u8", True), ("rtmp", False), ("rtsp", False)])
def test_engine_refuses_downloads_that_would_bypass_native_request_protection(protocol, is_live):
    from yt_dlp import YoutubeDL

    from video_downloader.domain.errors import AppError

    metadata = {
        "id": "synthetic-video", "title": "Synthetic video", "is_live": is_live,
        "url": "https://media.example/film", "protocol": protocol,
        "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "height": 720,
    }
    with YoutubeDL(YtDlpGateway._base_options(None)) as client, pytest.raises(AppError) as caught:
        client.process_ie_result(metadata, download=True)
    assert caught.value.code == ErrorCode.FORMAT_UNAVAILABLE


class GatewayTests(unittest.TestCase):
    def test_inspection_preserves_metadata_thumbnail(self) -> None:
        class Client:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def extract_info(self, url, download=False):
                return {"title": "Film", "thumbnail": "https://cdn.example.com/cover.jpg",
                        "formats": [{"vcodec": "vp9", "height": 720, "filesize_approx": 1000}]}

        class Module:
            YoutubeDL = Client

        class Guard:
            def ensure_public(self, url):
                pass

        gateway = YtDlpGateway(network_guard=Guard())
        gateway._module = lambda: Module
        info = gateway.inspect("https://example.com/film")
        self.assertEqual(info.thumbnail_url, "https://cdn.example.com/cover.jpg")
        self.assertIn("approx.", info.qualities[0].label)

    def test_changing_yt_dlp_estimate_never_becomes_total(self) -> None:
        events = []

        class Client:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def extract_info(self, url, download=True):
                self.options["progress_hooks"][0]({
                    "status": "downloading", "downloaded_bytes": 50,
                    "total_bytes_estimate": 100,
                })
                self.options["progress_hooks"][0]({
                    "status": "downloading", "downloaded_bytes": 60,
                    "total_bytes_estimate": 200,
                })
                output = Path(self.options["outtmpl"]["default"].replace("%(title).180B [%(id)s]", "video").replace("%(ext)s", "mp4"))
                output.write_bytes(b"video")
                return {"filepath": str(output), "height": 720}

        class Module:
            YoutubeDL = Client

        class Guard:
            def ensure_public(self, url):
                pass

        gateway = YtDlpGateway(network_guard=Guard())
        gateway._module = lambda: Module
        with tempfile.TemporaryDirectory() as directory:
            gateway.download(DownloadRequest("https://example.com/video", Path(directory), 720),
                             events.append, lambda: False)
        self.assertEqual([event.total_bytes for event in events if event.downloaded_bytes],
                         [None, None])
    def test_exact_height_selector_does_not_silently_fall_back(self) -> None:
        selector = YtDlpGateway._format_selector(1080)
        self.assertEqual(selector, "bestvideo[height=1080]+bestaudio/best[height=1080]")

    def test_source_quality_uses_best_video_source(self) -> None:
        self.assertEqual(YtDlpGateway._format_selector(0), "bestvideo*+bestaudio/best")

    def test_network_transport_uses_firefox_not_chrome(self) -> None:
        options = YtDlpGateway._base_options(None)
        self.assertEqual(options["impersonate"].client, "firefox")
        self.assertNotIn("chrome", str(options["impersonate"]).lower())

    def test_hls_vod_uses_native_downloader(self) -> None:
        from yt_dlp.downloader import HlsFD, get_suitable_downloader

        media = {"url": "https://example.com/video.m3u8", "protocol": "m3u8"}
        downloader = get_suitable_downloader(media, YtDlpGateway._base_options(None))
        self.assertIs(downloader, HlsFD)

    def test_unsupported_source_error_explains_safe_boundary(self) -> None:
        error = YtDlpGateway._app_error(Exception("ERROR: Unsupported URL: private"))
        self.assertEqual(error.code, ErrorCode.VERIFICATION_REQUIRED)
        self.assertIn("browser verification", error.user_message)
        self.assertNotIn("private", error.user_message)

    def test_network_error_is_classified_without_leaking_the_url(self) -> None:
        error = YtDlpGateway._app_error(
            Exception("Failed to resolve private.example.test for https://private.example.test")
        )
        self.assertEqual(error.code, ErrorCode.NETWORK)
        self.assertNotIn("private.example.test", error.user_message)

    def test_reported_qualities_are_unique_and_descending(self) -> None:
        qualities = YtDlpGateway._collect_qualities(
            [
                {"vcodec": "avc1", "height": 240, "filesize": 100},
                {"vcodec": "vp9", "height": 1080, "filesize": 900},
                {"vcodec": "avc1", "height": 1080, "filesize": 800},
                {"vcodec": "none", "height": None, "filesize": 20},
            ]
        )
        self.assertEqual([quality.height for quality in qualities], [1080, 240])
        self.assertEqual(qualities[0].estimated_bytes, 900)

    def test_unsupported_source_uses_isolated_firefox_fallback(self) -> None:
        class ExplodingClient:
            def __init__(self, options) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                pass

            def extract_info(self, url, download=False):
                raise RuntimeError("Unsupported URL")

        class FakeModule:
            YoutubeDL = ExplodingClient

        class FakeResolver:
            def resolve(self, url, proxy_url=None):
                return ResolvedMedia(
                    page_url=url,
                    media_url="https://media.example/video.m3u8",
                    title="Resolved video",
                    duration_seconds=120,
                    width=1920,
                    height=1080,
                    estimated_bytes=2_000_000_000,
                )

        class FakeGuard:
            def ensure_public(self, url):
                pass

        gateway = YtDlpGateway(FakeResolver(), FakeGuard())
        gateway._module = lambda: FakeModule
        video = gateway.inspect("https://example.com/watch/1")
        self.assertEqual(video.maximum_height, 1080)
        self.assertEqual(video.qualities[0].estimated_bytes, 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
