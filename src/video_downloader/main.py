from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import video_downloader
from video_downloader.application.use_cases import DownloadVideo, InspectVideo
from video_downloader.infrastructure.network_guard import PublicNetworkGuard
from video_downloader.infrastructure.settings import QtSettingsStore
from video_downloader.infrastructure.site_guard import SiteGuard
from video_downloader.infrastructure.video_validator import VideoValidator
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway
from video_downloader.presentation.application_identity import (
    configure_application_icon,
    configure_windows_identity,
)
from video_downloader.presentation.main_window import MainWindow
from video_downloader.presentation.styles import APP_STYLE


def asset_path(filename: str) -> Path:
    # Frozen entry scripts live outside their package; package-relative assets
    # keep both the native icons and protection files in the same stable location.
    return Path(video_downloader.__file__).resolve().parent / "assets" / filename


def configure_bundled_runtime() -> None:
    """Find the bundled tools even when the user opens the binary directly."""
    if getattr(sys, "frozen", False):
        bundle_root = Path(sys.executable).resolve().parent.parent
    elif os.environ.get("VIDEODOWNLOADER_BUNDLE_ROOT"):
        bundle_root = Path(os.environ["VIDEODOWNLOADER_BUNDLE_ROOT"]).resolve()
    else:
        return
    tools = bundle_root / "tools"
    os.environ["VIDEODOWNLOADER_BUNDLE_ROOT"] = str(bundle_root)
    directories = [("PATH", tools / "bin")]
    if sys.platform == "win32":
        directories.append(("PATH", tools / "firefox"))
    else:
        directories.append(("LD_LIBRARY_PATH", tools / "lib"))
    for variable, directory in reversed(directories):
        value = os.environ.get(variable, "")
        if str(directory) not in value.split(os.pathsep):
            os.environ[variable] = str(directory) + (os.pathsep + value if value else "")



def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    configure_bundled_runtime()
    configure_windows_identity()
    QCoreApplication.setOrganizationName("VideoDownloader")
    QCoreApplication.setApplicationName("VideoDownloader")
    application = QApplication(argv if argv is not None else sys.argv)
    configure_application_icon(application, asset_path("desktop-icon.svg").parent)
    application.setStyle("Fusion")
    application.setFont(QFont("Noto Sans", 10))
    application.setStyleSheet(APP_STYLE)

    site_guard = SiteGuard()
    gateway = YtDlpGateway(network_guard=PublicNetworkGuard(site_guard))
    settings = QtSettingsStore()
    window = MainWindow(
        InspectVideo(gateway),
        DownloadVideo(gateway, VideoValidator()),
        settings,
        asset_path("desktop-icon.svg"),
        protection_status=lambda: site_guard.status,
    )
    return application, window


def main() -> int:
    configure_bundled_runtime()
    parser = argparse.ArgumentParser(description="Private video downloader")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--diagnose", action="store_true", help="Run a local end-to-end self-test")
    actions.add_argument("--update-site-protection",
                        dest="update_site_protection", action="store_true",
                        help="Update the known-malicious-site list")
    parser.add_argument("--version", action="version", version=f"VideoDownloader {video_downloader.__version__}")
    args = parser.parse_args()
    if args.diagnose:
        from video_downloader.diagnostics import run
        return run()
    if args.update_site_protection:
        from video_downloader.domain.errors import AppError
        try:
            SiteGuard().prepare(force=True)
        except AppError as exc:
            print(exc.user_message)
            return 1
        print("Site threat list updated.")
        return 0
    application, window = create_application()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
