from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import validate_public_url
from video_downloader.infrastructure.bidi import BidiError, BidiSession
from video_downloader.infrastructure.network_guard import PublicNetworkGuard
from video_downloader.infrastructure.runtime import (
    find_tool,
    hidden_process_options,
    remove_temporary_directory,
    temporary_directory,
)

FIREFOX_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"
)
UBLOCK_SHA256 = "e963ebbefd12ae36d891393ff61940b8d94b605c2a8510d3749afff176d7ad7a"


@dataclass(frozen=True, slots=True)
class ResolvedMedia:
    page_url: str
    media_url: str
    title: str
    duration_seconds: int | None
    width: int | None
    height: int | None
    estimated_bytes: int | None
    user_agent: str = FIREFOX_USER_AGENT
    cookies: tuple[dict, ...] = ()
    thumbnail_url: str | None = None
    request_headers: tuple[tuple[str, str], ...] = ()

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Referer": self.page_url, "User-Agent": self.user_agent}
        names = {"referer": "Referer", "origin": "Origin", "user-agent": "User-Agent"}
        for name, value in self.request_headers:
            if name.lower() in names:
                headers[names[name.lower()]] = value
        return headers


class FirefoxMediaResolver:
    """Resolve media requests in an isolated, disposable Firefox session."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        network_guard: PublicNetworkGuard | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._network_guard = network_guard or PublicNetworkGuard()

    def resolve(self, url: str, proxy_url: str | None = None) -> ResolvedMedia:
        if proxy_url:
            raise AppError(ErrorCode.VERIFICATION_REQUIRED,
                           "Browser verification is unavailable with a custom proxy.")
        self._network_guard.ensure_public(url)
        with self.browser_session() as (port, extension):
            page = self._inspect_page(port, url, extension)
        final_url = validate_public_url(str(page.get("page") or url))
        self._network_guard.ensure_public(final_url)
        candidates = [str(item) for item in page.get("media", [])
                      if str(item).startswith(("http://", "https://"))]
        current = str(page.get("currentSrc") or "")
        if current.startswith(("http://", "https://")):
            candidates.insert(0, current)
        if not candidates:
            raise AppError(
                ErrorCode.VERIFICATION_REQUIRED,
                "The page did not expose a downloadable video. It may require sign-in, "
                "an interactive check, or use a protected player. [NO_MEDIA]",
            )
        media_url = validate_public_url(candidates[0])
        self._network_guard.ensure_public(media_url)
        hosts = {urlsplit(final_url).hostname, urlsplit(media_url).hostname}
        cookies = tuple(cookie for cookie in page.get("cookies", [])
                        if any(host and (host == str(cookie.get("domain", "")).lstrip(".")
                               or host.endswith("." + str(cookie.get("domain", "")).lstrip(".")))
                               for host in hosts))
        return ResolvedMedia(
            page_url=final_url, media_url=media_url,
            title=str(page.get("title") or "Video").strip() or "Video",
            duration_seconds=self._positive_int(page.get("duration")),
            width=self._positive_int(page.get("videoWidth")),
            height=self._positive_int(page.get("videoHeight")), estimated_bytes=None,
            user_agent=str(page.get("userAgent") or FIREFOX_USER_AGENT), cookies=cookies,
            thumbnail_url=str(page.get("poster") or "") or None,
            request_headers=tuple((page.get("request_headers") or {}).get(media_url, {}).items()),
        )

    @contextmanager
    def browser_session(self):
        firefox = find_tool("firefox")
        if not firefox or not Path(firefox).is_file():
            raise AppError(ErrorCode.VERIFICATION_REQUIRED,
                           "Firefox is missing. Restore the complete application package. [BROWSER_MISSING]")
        profile_root = Path(tempfile.mkdtemp(prefix="videodownloader-firefox-", dir=temporary_directory()))
        profile = profile_root / "profile"
        process = None
        reader = None
        startup = {"reason": "BROWSER_STARTUP"}
        try:
            profile.mkdir()
            self._write_private_preferences(profile)
            bundled_extension = Path(__file__).resolve().parents[1] / "assets/ublock-origin-lite.xpi"
            if not bundled_extension.is_file() or hashlib.sha256(
                    bundled_extension.read_bytes()).hexdigest() != UBLOCK_SHA256:
                raise AppError(ErrorCode.VERIFICATION_REQUIRED,
                               "The ad blocker is missing or damaged. Restore the application. [BLOCKER_MISSING]")
            extension = profile_root / "ublock-origin-lite.xpi"
            shutil.copyfile(bundled_extension, extension)
            port = self._reserve_loopback_port()
            process = subprocess.Popen(
                self._firefox_command(firefox, profile, port),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=self._isolated_environment(profile), text=True, errors="replace",
                shell=False, start_new_session=True,
                **hidden_process_options(),
            )

            def drain_errors():
                # Classify startup failures without storing paths, URLs, or page data.
                for line in process.stderr:
                    lower = line.lower()
                    if any(word in lower for word in ("operation not permitted", "permission denied",
                                                       "creating new namespace", "user namespaces")):
                        startup["reason"] = "BROWSER_SANDBOX"
                    elif any(word in lower for word in ("error while loading shared", "symbol lookup",
                                                        "version `glibc", "couldn't load xpcom")):
                        startup["reason"] = "BROWSER_DEPENDENCY"

            reader = Thread(target=drain_errors, daemon=True)
            reader.start()
            try:
                self._wait_for_port(port, process)
            except (RuntimeError, OSError) as exc:
                reader.join(timeout=0.5)
                reason = startup["reason"]
                explanation = {
                    "BROWSER_SANDBOX": "The system blocked the browser sandbox. Run --diagnose from a terminal. "
                                       "The app will not disable browser isolation.",
                    "BROWSER_DEPENDENCY": "A browser component could not load. Restore the complete application package.",
                    "BROWSER_STARTUP": "Firefox could not start. Run --diagnose from a terminal.",
                }[reason]
                raise AppError(ErrorCode.VERIFICATION_REQUIRED, f"{explanation} [{reason}]") from exc
            sandboxed_extension = Path("/tmp/videodownloader-addon.xpi") if sys.platform.startswith("linux") else extension
            yield port, sandboxed_extension
        except AppError:
            raise
        except (TimeoutError, BidiError) as exc:
            raise AppError(ErrorCode.VERIFICATION_REQUIRED,
                           "Firefox stopped responding during page inspection. Retry the link. [BROWSER_CONTROL]") from exc
        except Exception as exc:
            raise AppError(ErrorCode.VERIFICATION_REQUIRED,
                           "The browser connection failed. Run --diagnose from a terminal. [BROWSER_CONNECTION]") from exc
        finally:
            try:
                if process is not None:
                    self._stop_process(process)
                    if reader is not None:
                        reader.join(timeout=2)
                    if process.stderr:
                        process.stderr.close()
            finally:
                try:
                    remove_temporary_directory(profile_root)
                except OSError as exc:
                    raise AppError(ErrorCode.STORAGE,
                                   "The temporary browser profile could not be removed. [PROFILE_CLEANUP]") from exc

    def _inspect_page(self, port: int, url: str, extension: Path) -> dict:
        from websockets.sync.client import connect

        endpoint = f"ws://127.0.0.1:{port}/session"
        # Explicitly disable proxy discovery for the local browser control socket.
        with connect(endpoint, proxy=None, open_timeout=10, max_size=8 * 1024 * 1024) as websocket:
            request_guard = self._network_guard.ensure_public
            session = BidiSession(websocket, request_guard=request_guard)
            session.command("session.new", {"capabilities": {}})
            contexts = session.command("browsingContext.getTree", {}).get("contexts") or []
            if not contexts:
                raise BidiError("no such frame")
            context = contexts[0]["context"]
            session.command("webExtension.install", {
                "extensionData": {"type": "archivePath", "path": str(extension)},
                "moz:allowPrivateBrowsing": True,
            })
            session.command("session.subscribe", {
                "events": ["network.responseCompleted", "network.beforeRequestSent"], "contexts": [context],
            })
            if request_guard:
                session.command("network.addIntercept", {"phases": ["beforeRequestSent"]})
            session.command("browsingContext.navigate", {"context": context, "url": url, "wait": "none"})
            deadline = time.monotonic() + self._timeout_seconds
            page = {}
            detected_at = None
            while time.monotonic() < deadline:
                try:
                    tree = session.command("browsingContext.getTree", {"root": context})
                    frames = list(tree.get("contexts") or [])
                    while frames:
                        frame = frames.pop(0)
                        frames.extend(frame.get("children") or [])
                        try:
                            evaluated = session.command("script.evaluate", {
                                "expression": self._page_probe_expression(),
                                "target": {"context": frame["context"]}, "awaitPromise": False,
                            })
                        except BidiError as exc:
                            if exc.code in {"no such frame", "no such handle", "unknown error"}:
                                continue  # A redirect replaced this document; inspect the next one.
                            raise
                        result = evaluated.get("result") or {}
                        if result.get("type") != "string":
                            continue
                        probe = json.loads(result.get("value") or "{}")
                        if frame["context"] == context:
                            page.update({key: probe[key] for key in ("title", "page", "userAgent") if key in probe})
                        if probe.get("currentSrc") or probe.get("media"):
                            page.update({key: probe.get(key) for key in
                                         ("currentSrc", "duration", "videoWidth", "videoHeight", "poster")})
                            page["media"] = probe.get("media") or []
                    combined = list(dict.fromkeys((page.get("media") or []) + session.media))
                    page["media"] = combined
                    if combined or str(page.get("currentSrc", "")).startswith(("http://", "https://")):
                        detected_at = detected_at or time.monotonic()
                        if self._positive_int(page.get("videoHeight")) or time.monotonic() - detected_at > 3:
                            break
                except BidiError as exc:
                    if exc.code not in {"no such frame", "no such handle", "unknown error"}:
                        raise
                time.sleep(0.3)
            page["cookies"] = session.command("storage.getCookies", {
                "partition": {"type": "context", "context": context},
            }).get("cookies") or []
            # Firefox may omit private-window cookies from storage.getCookies.
            # Retain only cookies it actually sent to the detected media requests.
            for media_url in [page.get("currentSrc")] + (page.get("media") or []):
                page["cookies"].extend(session.request_cookies.get(media_url, []))
            page["request_headers"] = session.request_headers
            try:
                session.command("session.end", {}, timeout=3)
            except Exception:
                pass  # The enclosing context always terminates the process and removes its profile.
            return page

    @staticmethod
    def _page_probe_expression() -> str:
        return r"""
            (() => {
                const videos = [...document.querySelectorAll('video')];
                const visible = videos.filter(v => v.getClientRects().length &&
                    getComputedStyle(v).visibility !== 'hidden');
                const score = v => [Number(!!(v.currentSrc || v.src || v.querySelector('source[src]'))),
                    Number(v.controls), v.videoWidth*v.videoHeight];
                const video = (visible.length ? visible : videos).sort((a,b) => {
                    const left = score(a), right = score(b);
                    for (let i=0; i<left.length; i++) {
                        if (left[i] !== right[i]) return right[i]-left[i];
                    }
                    return 0;
                })[0];
                if (video && !video.__videodownloaderStarted) {
                    video.__videodownloaderStarted = true;
                    video.muted = true;
                    video.play().catch(() => {});
                }
                return JSON.stringify({
                    title: document.title, page: location.href, userAgent: navigator.userAgent,
                    duration: video?.duration || 0, videoWidth: video?.videoWidth || 0,
                    videoHeight: video?.videoHeight || 0, currentSrc: video?.currentSrc || '',
                    poster: video?.poster || '',
                    media: [...(video ? [...video.querySelectorAll('source')].map(s => s.src) : []),
                        ...performance.getEntriesByType('resource').map(e => e.name)]
                        .filter(u => /\.(m3u8|mpd|mp4|webm)(?:\?|$)/i.test(u))
                });
            })()
        """

    @staticmethod
    def _reserve_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    @staticmethod
    def _wait_for_port(port: int, process: subprocess.Popen[str]) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Firefox stopped before verification began")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("Firefox verification did not start in time")

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if os.name == "nt" and process.poll() is None:
            # Firefox owns several child processes. Terminating only its parent
            # leaves profile files open and defeats disposable-profile cleanup.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
                **hidden_process_options(),
            )
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _write_private_preferences(profile: Path) -> None:
        download_directory = profile / "downloads"
        download_directory.mkdir()
        encoded_download_directory = json.dumps(str(download_directory))
        preferences = "\n".join(
            (
                'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
                'user_pref("datareporting.healthreport.uploadEnabled", false);',
                'user_pref("toolkit.telemetry.enabled", false);',
                'user_pref("browser.ping-centre.telemetry", false);',
                'user_pref("browser.shell.checkDefaultBrowser", false);',
                'user_pref("browser.tabs.warnOnClose", false);',
                'user_pref("privacy.trackingprotection.enabled", true);',
                'user_pref("privacy.trackingprotection.pbmode.enabled", true);',
                'user_pref("privacy.trackingprotection.cryptomining.enabled", true);',
                'user_pref("privacy.trackingprotection.fingerprinting.enabled", true);',
                'user_pref("browser.contentblocking.category", "strict");',
                'user_pref("browser.privatebrowsing.autostart", true);',
                'user_pref("network.lna.enabled", true);',
                'user_pref("network.lna.blocking", true);',
                'user_pref("network.lna.block_trackers", true);',
                'user_pref("network.lna.etp.enabled", true);',
                'user_pref("network.lna.skip-domains", "");',
                'user_pref("media.peerconnection.enabled", false);',
                'user_pref("network.http.http3.enable", false);',
                'user_pref("network.webtransport.enabled", false);',
                'user_pref("network.prefetch-next", false);',
                'user_pref("network.dns.disablePrefetch", true);',
                'user_pref("network.predictor.enabled", false);',
                'user_pref("dom.disable_open_during_load", true);',
                'user_pref("permissions.default.desktop-notification", 2);',
                'user_pref("permissions.default.geo", 2);',
                'user_pref("permissions.default.camera", 2);',
                'user_pref("permissions.default.microphone", 2);',
                'user_pref("browser.download.folderList", 2);',
                'user_pref("browser.download.useDownloadDir", true);',
                f'user_pref("browser.download.dir", {encoded_download_directory});',
                f'user_pref("browser.download.lastDir", {encoded_download_directory});',
                'user_pref("browser.download.always_ask_before_handling_new_types", true);',
            )
        )
        (profile / "user.js").write_text(preferences + "\n", encoding="utf-8")

    @staticmethod
    def _isolated_environment(profile: Path) -> dict[str, str]:
        cache = profile / "cache"
        config = profile / "config"
        data = profile / "data"
        runtime = profile / "runtime"
        temporary = profile / "tmp"
        for directory in (cache, config, data, runtime, temporary):
            directory.mkdir()
        runtime.chmod(0o700)
        environment = {
            "HOME": str(profile),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", ""),
            "TZ": os.environ.get("TZ", "UTC"),
            "TMPDIR": str(temporary),
            "XDG_CACHE_HOME": str(cache),
            "XDG_CONFIG_HOME": str(config),
            "XDG_DATA_HOME": str(data),
            "XDG_RUNTIME_DIR": str(runtime),
            "MOZ_CRASHREPORTER_DISABLE": "1",
            "MOZ_DISABLE_AUTO_SAFE_MODE": "1",
        }
        if sys.platform == "win32":
            # Windows DLL loading and networking require these system locations.
            for name in ("SystemRoot", "WINDIR", "SYSTEMDRIVE", "COMSPEC"):
                if name in os.environ:
                    environment[name] = os.environ[name]
            environment.update({
                "USERPROFILE": str(profile), "APPDATA": str(config),
                "LOCALAPPDATA": str(data), "TEMP": str(temporary), "TMP": str(temporary),
            })
        return environment

    @staticmethod
    def _firefox_command(firefox: str, profile: Path, port: int) -> list[str]:
        firefox = str(Path(firefox).resolve())
        firefox_arguments = [
            firefox,
            "--headless",
            "--no-remote",
            "--profile",
            str(profile),
            "--remote-debugging-port",
            str(port),
            "about:blank",
        ]
        if os.name != "posix" or not sys.platform.startswith("linux"):
            return firefox_arguments
        # Distribution binaries can carry a required AppArmor profile (Ubuntu).
        system_bwrap = Path("/usr/bin/bwrap")
        bubblewrap = str(system_bwrap) if os.access(system_bwrap, os.X_OK) else shutil.which("bwrap")
        if not bubblewrap:
            raise AppError(
                ErrorCode.VERIFICATION_REQUIRED,
                "Secure Firefox verification requires bubblewrap on Linux.",
            )
        command = [bubblewrap, "--die-with-parent", "--new-session", "--unshare-all",
                   "--share-net", "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev"]
        for hidden_path in ("/tmp", "/home", "/root", "/media", "/mnt", "/run/media", "/run/user", "/opt"):
            if Path(hidden_path).exists():
                command.extend(("--tmpfs", hidden_path))
        # Fixed sandbox paths work when the package is on a USB drive, under /home,
        # or mounted read-only by AppImage. Host paths stay outside the browser.
        sandbox_profile = "/tmp/videodownloader-profile"
        browser_dir = Path(firefox).parent
        command.extend(("--ro-bind", str(browser_dir), "/opt/videodownloader-browser",
                        "--bind", str(profile), sandbox_profile,
                        "--ro-bind", str(profile.parent / "ublock-origin-lite.xpi"),
                        "/tmp/videodownloader-addon.xpi"))
        for variable, suffix in (("HOME", ""), ("XDG_CACHE_HOME", "/cache"),
                                 ("XDG_CONFIG_HOME", "/config"), ("XDG_DATA_HOME", "/data"),
                                 ("XDG_RUNTIME_DIR", "/runtime"), ("TMPDIR", "/tmp")):
            command.extend(("--setenv", variable, sandbox_profile + suffix))
        firefox_arguments[0] = "/opt/videodownloader-browser/" + Path(firefox).name
        firefox_arguments[4] = sandbox_profile
        return command + ["--"] + firefox_arguments

    @staticmethod
    def _positive_int(value) -> int | None:
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None
