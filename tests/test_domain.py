import unittest
from pathlib import Path

from video_downloader.domain.models import (
    DownloadProgress,
    DownloadResult,
    ProgressState,
    format_bytes,
    format_duration,
    validate_proxy_url,
    validate_public_url,
)


class DomainTests(unittest.TestCase):
    def test_formats_human_readable_transfer_values(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1536), "1.5 KB")
        self.assertEqual(format_bytes(1024**3), "1.0 GB")
        self.assertEqual(format_duration(83), "01:23")
        self.assertEqual(format_duration(3661), "1:01:01")

    def test_progress_percent_is_clamped(self) -> None:
        progress = DownloadProgress(ProgressState.DOWNLOADING, 150, 100)
        self.assertEqual(progress.percent, 100.0)

    def test_rejects_unsafe_source_urls(self) -> None:
        for url in (
            "file:///tmp/video.mp4",
            "javascript:alert(1)",
            "https://localhost/video",
            "http://127.0.0.1/video",
            "http://192.168.1.10/video",
            "https://example.com:99999/video",
            "https://example.com/vi\ndeo",
            "https://example.com/vi\tdeo",
            "https://example.com\\@127.0.0.1/video",
            "https://example.com/\x00video",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_public_url(url)

    def test_accepts_supported_proxy_schemes(self) -> None:
        self.assertEqual(
            validate_proxy_url("socks5://127.0.0.1:1080"), "socks5://127.0.0.1:1080"
        )
        self.assertIsNone(validate_proxy_url(""))

    def test_rejects_invalid_proxy_port_and_control_characters(self) -> None:
        for value in ("http://localhost:99999", "http://localhost:bad", "http://local\nhost:8080"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_proxy_url(value)

    def test_unknown_source_quality_does_not_claim_a_mismatch(self) -> None:
        result = DownloadResult(Path("video.mp4"), 720, 0)
        self.assertTrue(result.quality_matches)


if __name__ == "__main__":
    unittest.main()
