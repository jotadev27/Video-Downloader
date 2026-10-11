import io
import shutil
import sys
from pathlib import Path
from threading import Timer
from unittest.mock import Mock, patch

import pytest

from video_downloader.infrastructure.firefox_media_resolver import FirefoxMediaResolver


def test_windows_browser_cleanup_stops_the_owned_process_tree():
    process = Mock(pid=12345)
    process.poll.return_value = None
    with patch("video_downloader.infrastructure.firefox_media_resolver.os.name", "nt"), patch(
        "video_downloader.infrastructure.firefox_media_resolver.subprocess.run"
    ) as stop_tree:
        FirefoxMediaResolver._stop_process(process)
    stop_tree.assert_called_once()
    assert stop_tree.call_args.args[0] == ["taskkill", "/PID", "12345", "/T", "/F"]
    process.wait.assert_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows long-path regression")
def test_disposable_profile_cleanup_handles_long_extension_storage_paths(tmp_path):
    from video_downloader.infrastructure import firefox_media_resolver as browser
    process = Mock(stderr=io.StringIO(""))
    try:
        with patch.object(browser, "find_tool", return_value=sys.executable), patch.object(
            browser, "temporary_directory", return_value=str(tmp_path)
        ), patch.object(browser.subprocess, "Popen", return_value=process), patch.object(
            browser.FirefoxMediaResolver, "_wait_for_port"
        ), patch.object(browser.FirefoxMediaResolver, "_stop_process"):
            with browser.FirefoxMediaResolver().browser_session():
                profile = next(tmp_path.glob("videodownloader-firefox-*"))
                storage = profile / "profile" / ("extension-storage-" + "a" * 100) / ("b" * 100)
                extended = Path("\\\\?\\" + str(storage.resolve()))
                extended.mkdir(parents=True)
                (extended / "synthetic.sqlite").write_bytes(b"generated fixture")
            assert not profile.exists()
    finally:
        shutil.rmtree("\\\\?\\" + str(tmp_path.resolve()), ignore_errors=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file-sharing regression")
def test_profile_cleanup_waits_for_a_brief_windows_file_lock(tmp_path):
    from video_downloader.infrastructure.runtime import remove_temporary_directory
    directory = tmp_path / "profile"
    directory.mkdir()
    handle = (directory / "synthetic-lock").open("wb")
    release = Timer(0.25, handle.close)
    release.start()
    try:
        remove_temporary_directory(directory)
        assert not directory.exists()
    finally:
        handle.close()
        release.join()
