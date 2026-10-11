import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_downloader.infrastructure.video_validator import VideoValidator
from video_downloader.main import configure_bundled_runtime


class BundledRuntimeTests(unittest.TestCase):
    def test_direct_binary_finds_its_bundled_video_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "portable"
            binary = root / "VideoDownloader" / "VideoDownloader"
            binary.parent.mkdir(parents=True)
            binary.touch()
            scanner = root / "tools" / "bin" / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
            scanner.parent.mkdir(parents=True)
            scanner.write_text("#!/bin/sh\nexit 0\n")
            scanner.chmod(0o700)
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(binary)
            ), patch.dict(os.environ, {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "",
                                      "XDG_DATA_HOME": str(Path(directory) / "data")}):
                configure_bundled_runtime()
                self.assertEqual(os.environ["VIDEODOWNLOADER_BUNDLE_ROOT"], str(root))
                self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], str(root / "tools" / "bin"))
                self.assertTrue(VideoValidator().available())

    def test_incomplete_bundle_does_not_fall_back_to_host_video_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"VIDEODOWNLOADER_BUNDLE_ROOT": directory}
        ), patch("video_downloader.infrastructure.runtime.shutil.which", return_value="/usr/bin/ffprobe"):
            self.assertFalse(VideoValidator().available())

    def test_source_launcher_can_use_explicit_portable_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VIDEODOWNLOADER_BUNDLE_ROOT": directory, "PATH": "/usr/bin", "LD_LIBRARY_PATH": "",
            "XDG_DATA_HOME": str(Path(directory) / "data"),
        }):
            configure_bundled_runtime()
            self.assertEqual(os.environ["PATH"].split(os.pathsep)[0],
                             str(Path(directory) / "tools/bin"))


if __name__ == "__main__":
    unittest.main()
