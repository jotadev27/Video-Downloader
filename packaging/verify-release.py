"""Check release integrity, native architectures, permissions, and private-state exclusions."""
from __future__ import annotations

import hashlib
import struct
import tarfile
import zipfile
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "installer"
EXPECTED = {
    "VideoDownloader-1.0.0-windows-x64-setup.exe",
    "VideoDownloader-1.0.0-windows-x64-portable.zip",
    "VideoDownloader-1.0.0-linux-x64-installer.tar.gz",
    "SHA256SUMS.txt", "RELEASE-v1.0.txt",
}
PRIVATE_FILES = {"cookies.sqlite", "places.sqlite", "settings.ini", "parent.lock", "user.js"}


def check_private_state(name: str) -> None:
    path = Path(name)
    if path.name in PRIVATE_FILES or path.name.startswith(".env") or path.suffix in {
        ".mp4", ".mkv", ".webm", ".mp3", ".part", ".log", ".pyc"
    } or any(part in {"data", "__pycache__", "private", "downloads"} for part in path.parts):
        raise ValueError("Runtime/private state entered a release archive")


def verify() -> None:
    assert {path.name for path in OUTPUT.iterdir()} == EXPECTED
    checksums = (OUTPUT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 4
    for entry in checksums:
        expected, name = entry.split("  ", 1)
        assert name in EXPECTED and name != "SHA256SUMS.txt"
        with (OUTPUT / name).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected
    setup = OUTPUT / "VideoDownloader-1.0.0-windows-x64-setup.exe"
    with setup.open("rb") as stream:
        dos_header = stream.read(64)
        assert dos_header[:2] == b"MZ"
        stream.seek(struct.unpack_from("<I", dos_header, 60)[0])
        header = stream.read(6)
        assert header[:4] == b"PE\0\0" and struct.unpack_from("<H", header, 4)[0] == 0x8664
    with zipfile.ZipFile(OUTPUT / "VideoDownloader-1.0.0-windows-x64-portable.zip") as package:
        assert package.testzip() is None
        for name in package.namelist():
            check_private_state(name)
        program = pefile.PE(data=package.read("VideoDownloader/VideoDownloader.exe"))
        assert program.FILE_HEADER.Machine == 0x8664
        resources = {entry.id for entry in program.DIRECTORY_ENTRY_RESOURCE.entries}
        assert {3, 14}.issubset(resources), "Executable lacks native icon resources"
        assert package.read("tools/bin/ffmpeg.exe")[:2] == b"MZ"
        assert package.read("tools/firefox/firefox.exe")[:2] == b"MZ"
    base = "VideoDownloader-1.0.0-linux-x64"
    with tarfile.open(OUTPUT / "VideoDownloader-1.0.0-linux-x64-installer.tar.gz") as package:
        for member in package.getmembers():
            assert member.name == base or member.name.startswith(base + "/")
            assert ".." not in Path(member.name).parts
            check_private_state(member.name)
        with tarfile.open(ROOT / "build/linux/downloads/firefox.tar.xz") as original_browser:
            browser_executables = {"tools/" + member.name.removeprefix("./")
                                   for member in original_browser.getmembers()
                                   if member.isfile() and member.mode & 0o111}
        for name in browser_executables | {"tools/bin/node", "install.sh"}:
            assert package.getmember(base + "/" + name).mode & 0o111
        for name in ("tools/firefox/firefox", "tools/bin/node"):
            with package.extractfile(base + "/" + name) as stream:
                header = stream.read(20)
                assert header[:5] == b"\x7fELF\x02" and struct.unpack_from("<H", header, 18)[0] == 62
        with package.extractfile(base + "/install.sh") as stream:
            assert b"\r\n" not in stream.read()
    print("Release verified: exactly five files, all SHA-256 values, ZIP CRCs, x64 architectures, native icons, Unix execute bits, and no private runtime state.")


if __name__ == "__main__":
    verify()
