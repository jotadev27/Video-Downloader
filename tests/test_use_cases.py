import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_downloader.application.use_cases import DownloadVideo, InspectVideo
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import DownloadResult, VideoInfo, VideoQuality


class FakeGateway:
    def __init__(self) -> None:
        self.request = None

    def inspect(self, url, proxy_url=None):
        return VideoInfo("Example", url, 30, None, (VideoQuality(1080), VideoQuality(240)))

    def download(self, request, on_progress, is_cancelled):
        self.request = request
        (request.target_directory / "video.mp4").write_bytes(b"sample video")
        return DownloadResult(request.target_directory / "video.mp4", request.requested_height, 1080)


class FakeValidator:
    def available(self):
        return True

    def validate(self, path, is_cancelled):
        with path.open("rb") as file:
            assert file.read(12) == b"sample video"
        return 1080


class RejectingValidator(FakeValidator):
    def validate(self, path, is_cancelled):
        raise AppError(ErrorCode.FORMAT_UNAVAILABLE, "Not a video")


class MissingValidator(FakeValidator):
    def available(self):
        return False


class UseCaseTests(unittest.TestCase):
    def test_inspection_preserves_real_quality_bounds(self) -> None:
        video = InspectVideo(FakeGateway()).execute("https://example.com/watch/1")
        self.assertEqual(video.maximum_height, 1080)
        self.assertEqual(video.minimum_height, 240)

    def test_download_passes_exact_height(self) -> None:
        gateway = FakeGateway()
        with tempfile.TemporaryDirectory() as directory:
            result = DownloadVideo(gateway, FakeValidator()).execute(
                "https://example.com/watch/1",
                Path(directory),
                1080,
                None,
                lambda _: None,
                lambda: False,
            )
            self.assertEqual(result.file_path.read_bytes(), b"sample video")
            self.assertFalse(any(path.name.startswith(".videodownloader-download-") for path in Path(directory).iterdir()))
        self.assertEqual(gateway.request.requested_height, 1080)

    def test_non_video_download_never_reaches_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            with self.assertRaises(AppError) as caught:
                DownloadVideo(FakeGateway(), RejectingValidator()).execute(
                    "https://example.com/watch/1", target, 1080, None,
                    lambda _: None, lambda: False,
                )
            self.assertEqual(caught.exception.code, ErrorCode.FORMAT_UNAVAILABLE)
            self.assertEqual(list(target.iterdir()), [])

    def test_incomplete_bundle_explains_what_to_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"VIDEODOWNLOADER_BUNDLE_ROOT": directory}
        ):
            with self.assertRaises(AppError) as caught:
                DownloadVideo(FakeGateway(), MissingValidator()).execute(
                    "https://example.com/watch/1", Path(directory), 1080, None,
                    lambda _: None, lambda: False,
                )
            self.assertEqual(caught.exception.code, ErrorCode.ENGINE)
            self.assertIn("entire installer folder", caught.exception.user_message)

    def test_video_over_two_gb_is_published_without_antivirus_dependency(self) -> None:
        class LargeGateway(FakeGateway):
            def download(self, request, progress, cancelled):
                result = super().download(request, progress, cancelled)
                with result.file_path.open("ab") as file:
                    file.truncate(2_000_000_001)
                return result

        with tempfile.TemporaryDirectory() as directory:
            result = DownloadVideo(LargeGateway(), FakeValidator()).execute(
                "https://example.com/video", Path(directory), 1080, None,
                lambda _: None, lambda: False,
            )
            self.assertEqual(result.file_path.stat().st_size, 2_000_000_001)
            self.assertEqual(result.actual_height, 1080)


if __name__ == "__main__":
    unittest.main()
