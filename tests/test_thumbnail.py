import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from email.message import Message
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from video_downloader.infrastructure.thumbnail import load_thumbnail


class ThumbnailTests(unittest.TestCase):
    def test_decodes_real_response_and_rejects_local_url_by_default(self):
        image = QImage(1920, 1080, QImage.Format_RGB32)
        image.fill("blue")
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        data = bytes(buffer.data())

        url = "http://127.0.0.1/cover.png"
        self.assertIsNone(load_thumbnail(url, None, url))

        class Response:
            headers = Message()
            headers["Content-Type"] = "image/png"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, limit):
                return data[:limit]

        class Opener:
            def open(self, request, timeout):
                return Response()

        with patch("video_downloader.infrastructure.thumbnail.validate_public_url", side_effect=lambda value: value), patch(
            "video_downloader.infrastructure.thumbnail.PublicNetworkGuard.ensure_public"
        ), patch("video_downloader.infrastructure.thumbnail.build_opener", return_value=Opener()):
            loaded = load_thumbnail(url, None, url)
        self.assertIsNotNone(loaded)
        self.assertEqual((loaded.width(), loaded.height()), (1024, 576))


if __name__ == "__main__":
    unittest.main()
