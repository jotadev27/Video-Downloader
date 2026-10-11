import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import (
    DownloadProgress,
    DownloadResult,
    ProgressState,
    VideoInfo,
    VideoQuality,
)
from video_downloader.presentation.main_window import MainWindow


class Settings:
    download_directory = Path("/tmp")
    proxy_url = None


class Inspect:
    def __init__(self):
        self.calls = []

    def execute(self, url, proxy=None):
        self.calls.append(url)
        return VideoInfo("Real title", url, 60, None, (VideoQuality(720),))


class Download:
    def execute(self, *args):
        raise AssertionError("No download should start in this test")


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.inspect = Inspect()
        self.window = MainWindow(self.inspect, Download(), Settings(),
                                 Path("src/video_downloader/assets/VideoDownloader.png"))
        self.addCleanup(self.window.close)
        self.addCleanup(setattr, self.window, "_download_worker", None)

    def test_typing_and_pasting_never_start_inspection(self):
        for value in ("h", "ht", "http", "https", "https://example.com/video"):
            self.window.url_edit.setText(value)
            self.app.processEvents()
        QTest.qWait(800)
        self.assertEqual(self.inspect.calls, [])
        self.assertEqual(self.window.download_button.text(), "Inspect link")

    def test_default_dimensions_and_original_assets(self):
        self.assertEqual((self.window.width(), self.window.height()), (1080, 740))
        icon = QImage("src/video_downloader/assets/VideoDownloader.png")
        self.assertFalse(icon.isNull())
        self.assertEqual(icon.pixelColor(0, 0).alpha(), 0)
        self.assertTrue(Path("src/video_downloader/assets/brand-mark.svg").is_file())

    def test_click_is_explicit_async_inspection_and_invalid_url_is_local(self):
        self.window.url_edit.setText("bad link")
        with patch.object(self.window, "_show_error") as show_error:
            self.window.download_button.click()
        self.assertEqual(self.inspect.calls, [])
        show_error.assert_called_once()
        self.window.url_edit.setText("https://example.com/video")
        self.window.download_button.click()
        self.assertFalse(self.window.download_button.isEnabled())
        self.assertEqual(self.window.download_button.text(), "Inspecting…")
        deadline = time.monotonic() + 3
        while self.window._video is None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertEqual(self.inspect.calls, ["https://example.com/video"])
        self.assertEqual(self.window.download_button.text(), "Download")
        self.assertTrue(self.window.quality_combo.isEnabled())

    def test_thumbnail_is_cropped_without_stretch_and_play_is_centered(self):
        image = QImage(800, 600, QImage.Format_RGB32)
        image.fill("blue")
        self.window._thumbnail_loaded(image, self.window._thumbnail_generation)
        pixmap = self.window.preview_image.pixmap()
        self.assertEqual((pixmap.width(), pixmap.height()), (400, 225))
        self.assertEqual((self.window.play_mark.geometry().center().x(),
                          self.window.play_mark.geometry().center().y()), (199, 111))

    def test_metadata_starts_background_thumbnail_load(self):
        image = QImage(640, 360, QImage.Format_RGB32)
        image.fill("green")
        video = VideoInfo("Film", "https://example.com/watch", 60, None,
                          (VideoQuality(720),), "https://example.com/cover.png")
        with patch("video_downloader.presentation.main_window.load_thumbnail", return_value=image):
            self.window._inspection_succeeded(video)
            deadline = time.monotonic() + 3
            while self.window._thumbnail is None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertIsNotNone(self.window._thumbnail)
        self.assertFalse(self.window.preview_image.pixmap().isNull())

    def test_completion_waits_for_success_signal(self):
        self.window._update_progress(DownloadProgress(ProgressState.DOWNLOADING, 100, 100, 50))
        self.assertLess(self.window.progress_bar.value(), 1000)
        self.window._update_progress(DownloadProgress(ProgressState.PROCESSING))
        self.assertEqual(self.window.progress_heading.text(), "Processing")
        self.window._download_succeeded(DownloadResult(Path("/tmp/video.mp4"), 720, 720))
        self.assertEqual(self.window.progress_bar.value(), 1000)
        self.assertEqual(self.window.progress_heading.text(), "Completed")

    def test_failure_remains_visible_until_new_link(self):
        self.window.pages.setCurrentIndex(1)
        with patch.object(self.window, "_show_error"):
            self.window._download_failed(AppError(ErrorCode.NETWORK, "Connection failed."))
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.progress_heading.text(), "Failed")
        self.assertEqual(self.window.status_label.text(), "Connection failed.")
        self.window._download_finished()
        self.window._header_action()
        self.assertEqual(self.window.pages.currentIndex(), 0)

    def test_two_downloads_use_original_inspected_links_and_release_worker(self):
        calls = []

        class SuccessfulDownload:
            def execute(self, url, directory, height, proxy, progress, cancelled):
                calls.append(url)
                progress(DownloadProgress(ProgressState.DOWNLOADING, 50, 100, 50))
                return DownloadResult(directory / "film.mp4", height, height)

        self.window._download_video = SuccessfulDownload()
        for number in (1, 2):
            source = f"https://example.com/watch/{number}"
            self.window.url_edit.setText(source)
            self.window._inspected_url = source
            self.window._inspection_succeeded(VideoInfo(
                "Film", "https://example.com/canonical", 60, None, (VideoQuality(720),),
            ))
            self.window._download()
            deadline = time.monotonic() + 3
            while self.window._busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertFalse(self.window._busy)
            self.assertIsNone(self.window._download_worker)
            self.assertEqual(self.window.progress_heading.text(), "Completed")
            self.assertFalse(self.window.new_link_button.isHidden())
            self.window.new_link_button.click()
            self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertEqual(calls, ["https://example.com/watch/1", "https://example.com/watch/2"])

    def test_failed_download_can_retry_without_retyping_link(self):
        calls = []

        class FlakyDownload:
            def execute(self, url, directory, height, proxy, progress, cancelled):
                calls.append(url)
                if len(calls) == 1:
                    raise AppError(ErrorCode.ACCESS_REQUIRED, "Session rejected")
                return DownloadResult(directory / "film.mp4", height, height)

        source = "https://example.com/watch"
        self.window._download_video = FlakyDownload()
        self.window._start_download(source, "Film", 720)
        deadline = time.monotonic() + 3
        while self.window._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(self.window.retry_button.isEnabled())
        self.assertFalse(self.window.retry_button.isHidden())
        self.window.retry_button.click()
        deadline = time.monotonic() + 3
        while self.window._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(calls, [source, source])
        self.assertEqual(self.window.progress_heading.text(), "Completed")

    def test_cancellation_resets_form_after_worker_finishes(self):
        self.window._download_worker = object()
        self.window.pages.setCurrentIndex(1)
        self.window._download_failed(AppError(ErrorCode.CANCELLED, "Cancelled"))
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.window._download_finished()
        self.assertEqual(self.window.pages.currentIndex(), 0)

    def test_declining_cancellation_keeps_download_running(self):
        worker = Mock()
        self.window._download_worker = worker
        self.window.pages.setCurrentIndex(1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
            self.window._header_action()
        question.assert_called_once()
        worker.cancel.assert_not_called()
        self.assertTrue(self.window.back_button.isEnabled())
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.window._download_worker = None

    def test_confirming_cancellation_waits_for_cleanup_then_returns_home(self):
        worker = Mock()
        self.window._download_worker = worker
        self.window.pages.setCurrentIndex(1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.window._header_action()
        worker.cancel.assert_called_once()
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertFalse(self.window.back_button.isEnabled())
        self.window._download_finished()
        self.assertEqual(self.window.pages.currentIndex(), 0)

    def test_cancellation_accepts_worker_completion_while_confirmation_is_open(self):
        worker = Mock()
        self.window._download_worker = worker
        self.window.pages.setCurrentIndex(1)
        def finish_during_confirmation(*args):
            self.window._download_finished()
            return QMessageBox.Yes
        with patch.object(QMessageBox, "question", side_effect=finish_during_confirmation):
            self.window._header_action()
        self.assertEqual(self.window.pages.currentIndex(), 0)
        worker.cancel.assert_not_called()

    def test_processing_status_does_not_claim_antivirus_scan(self):
        self.window._update_progress(DownloadProgress(ProgressState.PROCESSING,
                                                     message="Finalizing file"))
        self.assertEqual(self.window.progress_heading.text(), "Processing")
        self.assertEqual(self.window.progress_details.text(), "Finalizing file")


if __name__ == "__main__":
    unittest.main()
