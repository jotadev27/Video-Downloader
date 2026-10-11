import json
import subprocess
import sys
from pathlib import Path

import pytest

from video_downloader.application.use_cases import DownloadVideo
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import DownloadResult
from video_downloader.infrastructure.runtime import find_tool
from video_downloader.infrastructure.video_validator import VideoValidator


@pytest.fixture(scope="module")
def real_video(tmp_path_factory):
    executable = find_tool("ffmpeg")
    if not executable:
        pytest.skip("The bundled FFmpeg fixture generator is unavailable")
    path = tmp_path_factory.mktemp("video-fixture") / "film.mp4"
    subprocess.run([str(executable), "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=160x90:r=10", "-t", "1", "-c:v", "mpeg4",
                    "-movflags", "+faststart", str(path)], check=True, timeout=15)
    return path


@pytest.fixture
def validator():
    executable = find_tool("ffprobe")
    if not executable:
        pytest.skip("The bundled FFprobe is unavailable")
    return VideoValidator(str(executable))


def test_real_video_height_is_verified(validator, real_video):
    assert validator.validate(real_video, lambda: False) == 90


def test_html_script_and_playlist_renamed_mp4_are_rejected(validator, tmp_path):
    for content in (b"<html>Access denied</html>", b"#!/bin/sh\necho malware\n",
                    b"#EXTM3U\nhttps://example.com/video.ts\n"):
        file = tmp_path / "fake.mp4"
        file.write_bytes(content)
        with pytest.raises(AppError) as caught:
            validator.validate(file, lambda: False)
        assert caught.value.code == ErrorCode.FORMAT_UNAVAILABLE


def test_actual_video_over_two_gb_is_validated_and_published(validator, real_video, tmp_path):
    class Gateway:
        def download(self, request, progress, cancelled):
            output = request.target_directory / "large.mp4"
            output.write_bytes(real_video.read_bytes())
            # Sparse padding exercises the size check without allocating 2 GB.
            with output.open("ab") as file:
                file.truncate(2_147_483_649)
            return DownloadResult(output, None, 90)

    result = DownloadVideo(Gateway(), validator).execute(
        "https://example.com/film", tmp_path, 90, None, lambda _: None, lambda: False,
    )
    assert result.file_path.stat().st_size == 2_147_483_649
    assert result.actual_height == 90
    assert result.quality_matches
    assert not list(tmp_path.glob(".videodownloader-download-*"))


def test_audio_only_container_cannot_pass_as_video(validator, tmp_path):
    executable = Path(validator._executable).with_name("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    file = tmp_path / "audio.mp4"
    subprocess.run([str(executable), "-v", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=8000:cl=mono", "-t", "0.2", "-c:a", "aac", str(file)],
                   check=True, timeout=15)
    with pytest.raises(AppError) as caught:
        validator.validate(file, lambda: False)
    assert caught.value.code == ErrorCode.FORMAT_UNAVAILABLE


@pytest.mark.skipif(sys.platform == "win32", reason="This test uses a POSIX shebang executable")
def test_validation_can_be_cancelled_and_timeout_stops_process(tmp_path):
    executable = tmp_path / "slow-probe"
    executable.write_text(f"#!{Path(sys.executable).resolve()}\nimport time\ntime.sleep(10)\n")
    executable.chmod(0o700)
    validator = VideoValidator(str(executable), timeout_seconds=0.05)
    with pytest.raises(AppError) as caught:
        validator.validate(tmp_path / "file.mp4", lambda: True)
    assert caught.value.code == ErrorCode.CANCELLED
    with pytest.raises(AppError) as caught:
        validator.validate(tmp_path / "file.mp4", lambda: False)
    assert caught.value.code == ErrorCode.FORMAT_UNAVAILABLE


@pytest.mark.skipif(sys.platform == "win32", reason="This test uses a POSIX shebang executable")
def test_invalid_probe_output_is_rejected(tmp_path):
    executable = tmp_path / "fake-probe"
    for metadata in ({"streams": []}, {"format": {"format_name": "mov"}, "streams": []},
                     {"format": {"format_name": "jpeg_pipe"}, "streams": [
                         {"codec_type": "video", "codec_name": "mjpeg", "width": 160, "height": 90}]}):
        executable.write_text(f"#!{Path(sys.executable).resolve()}\nprint({json.dumps(metadata)!r})\n")
        executable.chmod(0o700)
        with pytest.raises(AppError):
            VideoValidator(str(executable)).validate(tmp_path / "file.mp4", lambda: False)
