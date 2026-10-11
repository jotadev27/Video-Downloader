"""Assemble clean release payloads without copying local application state."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
WINDOWS = BUILD / "release/VideoDownloader-windows-x64"
LINUX = BUILD / "release/VideoDownloader-1.0.0-linux-x64"
OUTPUT = ROOT / "installer"
DOWNLOADS = BUILD / "windows/downloads"


def remove_generated(path: Path) -> None:
    if not path.resolve().is_relative_to(BUILD.resolve()) or path.resolve() == BUILD.resolve():
        raise ValueError("Refusing cleanup outside generated build staging")
    if path.exists():
        native_path = str(path.resolve())
        if sys.platform == "win32":
            native_path = "\\\\?\\" + native_path
        shutil.rmtree(native_path)


def extract_verified(archive: Path, destination: Path) -> None:
    """Extract a previously checksum-verified archive under project build staging."""
    if not destination.resolve().is_relative_to(BUILD.resolve()):
        raise ValueError("Archive extraction escaped build staging")
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")


def copy_notices(destination: Path, *, bundled_python: bool = True) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src/video_downloader/assets/HAGEZI-LICENSE.txt", destination)
    for source in (BUILD / "licenses").glob("*.txt"):
        shutil.copy2(source, destination)
    # Dependency notices are shipped with their official wheels. Keep all of
    # them here as well, including licenses omitted by frozen-module collection.
    if bundled_python:
        site = ROOT / ".venv-windows/Lib/site-packages"
        runtime_names = {"brotli", "certifi", "cffi", "charset_normalizer", "curl_cffi", "idna",
                         "mutagen", "pycparser", "pycryptodomex", "requests", "urllib3", "websockets",
                         "yt_dlp", "yt_dlp_ejs", "pyside6", "pyside6_essentials", "pyside6_addons", "shiboken6"}
        for metadata in site.glob("*.dist-info"):
            notices = metadata / "licenses"
            if metadata.name.split("-")[0].lower() in runtime_names and notices.is_dir():
                shutil.copytree(notices, destination / metadata.name, dirs_exist_ok=True)
        python_notice = Path(sys.base_prefix) / "LICENSE.txt"
        if python_notice.is_file():
            shutil.copy2(python_notice, destination / "Python-LICENSE.txt")


def verify_runtime_downloads() -> None:
    firefox_line = next(line for line in (DOWNLOADS / "firefox-sha512.txt").read_text().splitlines()
                        if line.endswith("  linux-x86_64/en-US/firefox-157.0.1.tar.xz"))
    node_line = next(line for line in (DOWNLOADS / "node-shasums.txt").read_text().splitlines()
                     if line.endswith("  node-v24.21.0-linux-x64.tar.xz"))
    for path, algorithm, expected in (
        (BUILD / "linux/downloads/firefox.tar.xz", "sha512", firefox_line.split()[0]),
        (BUILD / "linux/node.tar.xz", "sha256", node_line.split()[0]),
    ):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, algorithm).hexdigest()
        if digest != expected:
            raise ValueError("Official Linux runtime checksum mismatch")


def stage() -> None:
    if not (WINDOWS / "VideoDownloader/VideoDownloader.exe").is_file():
        raise ValueError("Build the Windows application first")
    # Start from the signed Mozilla installer, never from a browser directory
    # that a user may have opened and populated with personal state.
    clean_firefox = BUILD / "windows/clean-firefox"
    remove_generated(clean_firefox)
    subprocess.run([str(DOWNLOADS / "7zr.exe"), "x", str(DOWNLOADS / "firefox-setup.exe"),
                    "-o" + str(clean_firefox), "-y"], check=True, stdout=subprocess.DEVNULL)
    remove_generated(WINDOWS / "tools")
    shutil.copytree(clean_firefox / "core", WINDOWS / "tools/firefox")
    binary_dir = WINDOWS / "tools/bin"
    binary_dir.mkdir(parents=True)
    for filename in ("ffmpeg.exe", "ffprobe.exe", "node.exe"):
        shutil.copy2(BUILD / "runtime/bin" / filename, binary_dir / filename)
    remove_generated(WINDOWS / "licenses")
    copy_notices(WINDOWS / "licenses")
    shutil.copy2(DOWNLOADS / "ffmpeg-extracted/ffmpeg-9.0.2-essentials_build/LICENSE",
                 WINDOWS / "licenses/FFmpeg-GPL-3.0.txt")
    shutil.copy2(DOWNLOADS / "ffmpeg-extracted/ffmpeg-9.0.2-essentials_build/README.txt",
                 WINDOWS / "licenses/FFmpeg-BUILD.txt")
    shutil.copy2(DOWNLOADS / "node-extracted/node-v24.21.0-win-x64/LICENSE",
                 WINDOWS / "licenses/Node-LICENSE.txt")
    for name in ("LICENSE", "THIRD_PARTY.md", "SECURITY.md"):
        shutil.copy2(ROOT / name, WINDOWS / name)
    (WINDOWS / "README.txt").write_text(
        "VideoDownloader 1.0.0 - Windows x64\n\n"
        "Extract the entire ZIP, then open VideoDownloader/VideoDownloader.exe.\n"
        "Keep tools beside the application folder. No installation is required.\n"
        "Choose a download folder in Settings. Temporary data and settings are\n"
        "stored in data/ inside this extracted package. No source links are logged.\n"
        "If inspection fails, click Inspect link again.\n"
        "Cancel asks for confirmation: No continues; Yes returns home after cleanup.\n"
        "See SECURITY.md for protection limits and THIRD_PARTY.md for licenses.\n",
        encoding="utf-8")

    verify_runtime_downloads()
    remove_generated(LINUX)
    LINUX.mkdir(parents=True)
    shutil.copytree(ROOT / "src/video_downloader", LINUX / "src/video_downloader",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    extract_verified(BUILD / "linux/downloads/firefox.tar.xz", LINUX / "tools")
    node_staging = BUILD / "linux/node-extracted"
    remove_generated(node_staging)
    extract_verified(BUILD / "linux/node.tar.xz", node_staging)
    (LINUX / "tools/bin").mkdir(parents=True)
    shutil.copy2(node_staging / "node-v24.21.0-linux-x64/bin/node", LINUX / "tools/bin/node")
    copy_notices(LINUX / "licenses", bundled_python=False)
    shutil.copy2(node_staging / "node-v24.21.0-linux-x64/LICENSE", LINUX / "licenses/Node-LICENSE.txt")
    for name in ("LICENSE", "THIRD_PARTY.md", "SECURITY.md", "README.md"):
        shutil.copy2(ROOT / name, LINUX / name)
    for name in ("install.sh", "requirements.txt"):
        shutil.copy2(ROOT / "packaging/linux" / name, LINUX / name)
    print("Clean Windows and Linux payloads staged")


def archive() -> None:
    OUTPUT.mkdir(exist_ok=True)
    setup_name = "VideoDownloader-1.0.0-windows-x64-setup.exe"
    names = {setup_name, "VideoDownloader-1.0.0-windows-x64-portable.zip",
             "VideoDownloader-1.0.0-linux-x64-installer.tar.gz", "RELEASE-v1.0.txt", "SHA256SUMS.txt"}
    if any(path.name not in names for path in OUTPUT.iterdir()):
        raise ValueError("Unexpected installer contents; clean them before building")
    if not (OUTPUT / setup_name).is_file():
        raise ValueError("Compile the Windows installer first")
    # Tests may create runtime data; it must never enter a release archive.
    remove_generated(WINDOWS / "data")
    with zipfile.ZipFile(OUTPUT / "VideoDownloader-1.0.0-windows-x64-portable.zip", "w",
                         compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(WINDOWS.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(WINDOWS).as_posix())
    with tarfile.open(BUILD / "linux/downloads/firefox.tar.xz") as original_browser:
        executable_files = {"tools/" + member.name for member in original_browser.getmembers()
                            if member.isfile() and member.mode & 0o111}
    executable_files.update({"install.sh", "tools/bin/node"})
    with tarfile.open(OUTPUT / "VideoDownloader-1.0.0-linux-x64-installer.tar.gz", "w:gz") as package:
        def permissions(member: tarfile.TarInfo) -> tarfile.TarInfo:
            # Windows extraction loses Unix execute bits. Restore executable
            # programs only; directory traversal and links stay under this root.
            relative = member.name.removeprefix(LINUX.name + "/")
            if member.isdir() or relative in executable_files:
                member.mode = 0o755
            elif member.isfile():
                member.mode = 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            return member
        package.add(LINUX, arcname=LINUX.name, filter=permissions)
    shutil.copy2(ROOT / "packaging/release-v1.0.txt", OUTPUT / "RELEASE-v1.0.txt")
    entries = []
    for path in sorted(OUTPUT.iterdir()):
        if path.name != "SHA256SUMS.txt":
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            entries.append(f"{digest}  {path.name}")
    (OUTPUT / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
    print("Exactly five release artifacts assembled; SHA-256 manifest generated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage", action="store_true")
    mode.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    stage() if args.stage else archive()
