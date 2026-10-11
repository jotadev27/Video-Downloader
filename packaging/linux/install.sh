#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    echo "This installer requires Linux x64."
    exit 1
fi

ID=unknown
ID_LIKE=
if [ -r /etc/os-release ]; then . /etc/os-release; fi
case " $ID $ID_LIKE " in
    *ubuntu*|*debian*)
        command="sudo apt-get update && sudo apt-get install python3 python3-venv ffmpeg bubblewrap libgtk-3-0 libdbus-glib-1-2 libnss3 libxcb-cursor0 libegl1 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-image0 libxcb-render-util0"
        ;;
    *arch*|*manjaro*)
        command="sudo pacman -S --needed python python-pip ffmpeg bubblewrap gtk3 dbus-glib nss alsa-lib xcb-util-cursor libxkbcommon-x11 mesa libxcb xcb-util-image xcb-util-keysyms xcb-util-wm xcb-util-renderutil"
        ;;
    *fedora*)
        command="sudo dnf install python3 python3-pip ffmpeg-free bubblewrap gtk3 dbus-glib nss alsa-lib xcb-util-cursor libxkbcommon-x11 mesa-libEGL xcb-util-image xcb-util-keysyms xcb-util-wm xcb-util-renderutil"
        ;;
    *) echo "Supported families: Ubuntu/Debian, Manjaro/Arch, and Fedora."; exit 1 ;;
esac

if [ "${1-}" = --print-system-command ]; then printf '%s\n' "$command"; exit 0; fi
printf 'System dependency command for this distribution:\n%s\n' "$command"
printf 'Run that command now? [y/N] '
read -r answer
case "$answer" in
    y|Y|yes|YES) sh -c "$command" ;;
    *) echo "Continuing with the system dependencies already installed." ;;
esac

for tool in python3 ffmpeg ffprobe bwrap; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Missing $tool. Run the dependency command above, then retry."
        exit 1
    fi
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required; Ubuntu 24.04+ is recommended.")'

DATA_ROOT=${XDG_DATA_HOME:-"$HOME/.local/share"}
APP_ROOT=$DATA_ROOT/VideoDownloader/application
mkdir -p "$APP_ROOT" "$DATA_ROOT/applications" "$DATA_ROOT/icons/hicolor/scalable/apps"
cp -R "$ROOT/src" "$ROOT/tools" "$ROOT/licenses" "$APP_ROOT/"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY.md" "$ROOT/requirements.txt" "$APP_ROOT/"
python3 -m venv "$APP_ROOT/venv"
"$APP_ROOT/venv/bin/python" -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: -r "$APP_ROOT/requirements.txt"

# Resolve relative to this launcher, including installation paths with spaces.
cat > "$APP_ROOT/launch.sh" <<'LAUNCHER'
#!/bin/sh
set -eu
APP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$APP_ROOT/tools/firefox:$APP_ROOT/tools/bin:$PATH"
export PYTHONPATH="$APP_ROOT/src"
exec "$APP_ROOT/venv/bin/python" -m video_downloader.main "$@"
LAUNCHER
chmod +x "$APP_ROOT/launch.sh"
cp "$APP_ROOT/src/video_downloader/assets/desktop-icon.svg" "$DATA_ROOT/icons/hicolor/scalable/apps/videodownloader.svg"
# Escape desktop-entry metacharacters as specified by freedesktop.org.
"$APP_ROOT/venv/bin/python" - "$APP_ROOT" "$DATA_ROOT" <<'PYTHON'
from pathlib import Path
import sys
app, data = map(Path, sys.argv[1:])
executable = str(app / "launch.sh").replace("%", "%%")
for char in ('\\', '"', '`', '$'):
    executable = executable.replace(char, '\\' + char)
entry = '\n'.join((
    '[Desktop Entry]', 'Type=Application', 'Name=VideoDownloader',
    'Comment=Inspect and download videos', 'Exec="' + executable + '"',
    'Icon=videodownloader', 'Terminal=false', 'Categories=AudioVideo;Video;Network;', ''
))
(data / 'applications/videodownloader.desktop').write_text(entry, encoding='utf-8')
PYTHON
printf '\nInstalled VideoDownloader 1.0.0. Open it from your applications menu.\n'
printf 'Terminal launch: "%s/launch.sh"\n' "$APP_ROOT"
