<p align="center"><img src="src/video_downloader/assets/desktop-icon.svg" width="120" height="120" alt="VideoDownloader logo"></p>

# VideoDownloader

![Version](https://img.shields.io/badge/version-1.0.0-2f79db?style=flat-square)
![Language](https://img.shields.io/github/languages/top/jotadev27/Video-Downloader?style=flat-square)
![Platforms](https://img.shields.io/badge/platforms-Windows_x64_%7C_Linux_x64-555?style=flat-square)
![License](https://img.shields.io/badge/source_license-MIT-80b918?style=flat-square)

A desktop app to inspect video links, choose an available resolution, and save verified video files. It includes uBlock Origin Lite for temporary browser inspection and local checks against known malicious domains.

## Install

Get v1.0 from [GitHub Releases](https://github.com/jotadev27/Video-Downloader/releases).

**Windows x64:** run `VideoDownloader-1.0.0-windows-x64-setup.exe` and follow **Next → Next → Install**. Enable the desktop shortcut if wanted. For portable use, extract `VideoDownloader-1.0.0-windows-x64-portable.zip` completely and open `VideoDownloader/VideoDownloader.exe`. Keep the `tools` folder beside the application folder.

**Linux x64:** Ubuntu 24.04+, Manjaro/Arch, Fedora, and compatible derivatives. Python 3.11+, glibc 2.34+, a graphical desktop, and an internet connection are required. The installer selects the distribution's package manager, asks before installing system dependencies, and installs the app for the current user.

```sh
tar -xzf VideoDownloader-1.0.0-linux-x64-installer.tar.gz
cd VideoDownloader-1.0.0-linux-x64
chmod +x install.sh
./install.sh
```

Then open **VideoDownloader** from the applications menu, or run:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/VideoDownloader/application/launch.sh"
```

Verify downloaded release files with `sha256sum -c SHA256SUMS.txt` on Linux. On Windows, compare `Get-FileHash .\VideoDownloader-1.0.0-windows-x64-setup.exe -Algorithm SHA256` with the supplied checksum file.

## Use

Paste a public video link and click **Inspect link**. Select a resolution and download. If inspection fails, click **Inspect link** again. Cancelling asks for confirmation; **No** keeps the download running and **Yes** returns home after cleanup.

No browsing history or source links are written to logs. Portable settings and temporary data stay inside the extracted package. These protections reduce risk; they cannot guarantee that every website or media file is safe. See [SECURITY.md](SECURITY.md) and [third-party notices](THIRD_PARTY.md).

## Development

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m video_downloader.main
python -m pytest
```

The code separates domain rules, application workflows, infrastructure adapters, and the Qt interface. Release outputs, downloaded media, profiles, settings, credentials, and build environments are excluded from Git. See [packaging/README.md](packaging/README.md) for release builds.
