# Release builds

All outputs are project-local. `build/`, `.venv-windows/`, and `installer/` are ignored by Git. v1.0 intentionally targets Windows x64; there is no x32 build.

1. Create the Windows build environment using Python 3.12 and `windows-requirements.lock` from official PyPI. Keep external downloads in `build/windows/downloads` and verify them before execution.
2. Stage verified Windows Firefox, FFmpeg/FFprobe, and Node under `build/runtime/firefox` and `build/runtime/bin`. The tested versions are Firefox 157.0.1, FFmpeg 9.0.2, and Node 24.21.0. Firefox's installer has a valid Mozilla signature; FFmpeg and Node match their official provider checksums.
3. Run `./packaging/build-windows.ps1`. It creates the frozen app in `build/release/VideoDownloader-windows-x64`, exports native ICO sizes, and generates both wizard images from the same SVG mark. The icon covers 87.5% of the canvas with transparent, balanced margins.
4. Download Linux Firefox 157.0.1 and Node 24.21.0 x64 archives from Mozilla/Node, verify their official SHA-512/SHA-256 checksums, and place them under `build/linux/downloads/firefox.tar.xz` and `build/linux/node.tar.xz`.
5. Run `python packaging/assemble-release.py --stage` to copy verified runtimes, license notices, and the Linux installer source into clean staging. Run the frozen app's `--diagnose` and `packaging/smoke-windows.py` before archiving.
6. Install the signed official Inno Setup 7.1 compiler in portable mode at `build/InnoSetup`. Compile `packaging/windows-installer.iss` with `build/InnoSetup/ISCC.exe`.
7. Run `python packaging/assemble-release.py --archive` to create the portable ZIP, Linux tarball, release text, and SHA-256 manifest. This refuses unexpected installer contents and excludes runtime data.

The resulting `installer/` contains exactly five files: the Windows setup EXE, Windows portable ZIP, Linux installer tarball, `SHA256SUMS.txt`, and `RELEASE-v1.0.txt`. Attach them to a GitHub release manually; do not add them to source control.

The Linux installer selects apt, pacman, or dnf, asks before invoking the system package manager, and installs a per-user Python environment from official PyPI. Firefox and Node are bundled; FFmpeg and Bubblewrap come from the distribution. It requires Python 3.11+ and glibc 2.34+. Linux execution must be verified on the target distribution before claiming that distribution has been tested.

Run `python packaging/audit-public-source.py` before staging source. It rejects generated payloads, downloaded media, sensitive file types, personal absolute paths, and common secret markers, and verifies the bundled uBlock XPI hash. This is a focused publication check, not a complete vulnerability scanner.
