from pathlib import Path
from unittest.mock import patch

from video_downloader import main


def test_asset_lookup_survives_pyinstaller_moving_the_entry_script():
    # PyInstaller executes main.py at the bundle root while package assets live
    # under video_downloader/. Entry-script-relative lookup silently loses icons.
    with patch.object(main, "__file__", str(Path("build/_internal/main.py"))):
        assert main.asset_path("desktop-icon.svg").is_file()
