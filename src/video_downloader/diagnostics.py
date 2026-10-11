"""A private, offline end-to-end check using a temporary local video fixture."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.firefox_media_resolver import FirefoxMediaResolver
from video_downloader.infrastructure.runtime import (
    find_tool,
    hidden_process_options,
    temporary_directory,
)
from video_downloader.infrastructure.site_guard import SiteGuard
from video_downloader.infrastructure.video_validator import VideoValidator
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


def run() -> int:
    results = {}
    stage = 'tools'
    try:
        names = ['firefox', 'ffmpeg', 'ffprobe', 'node']
        if sys.platform.startswith('linux'):
            names.append('bwrap')
        for name in names:
            if not find_tool(name):
                raise RuntimeError('A bundled tool is missing')
        results[stage] = 'OK'
        with tempfile.TemporaryDirectory(prefix='videodownloader-check-', dir=temporary_directory()) as directory:
            root = Path(directory)
            stage = 'media_generation'
            subprocess.run([
                'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=10',
                '-t', '1', '-c:v', 'mpeg4', str(root / 'sample.mp4'),
            ], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30, **hidden_process_options())
            (root / 'key.bin').write_bytes(os.urandom(16))
            (root / 'key-info').write_text('key.bin\n' + str(root / 'key.bin') + '\n')
            subprocess.run([
                'ffmpeg', '-v', 'error', '-i', str(root / 'sample.mp4'), '-c:v', 'mpeg2video',
                '-f', 'hls', '-hls_time', '1', '-hls_key_info_file', str(root / 'key-info'),
                '-hls_list_size', '0', str(root / 'playlist.m3u8'),
            ], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30, **hidden_process_options())
            results[stage] = 'OK'
            (root / 'page.html').write_text(
                '<title>Diagnostic video</title><script>setTimeout(() => {'
                'let frame=document.createElement("iframe");frame.src="/player.html";'
                'document.body.append(frame)},250)</script>')
            (root / 'player.html').write_text(
                '<video class="preview" style="display:none"></video>'
                '<video preload="none" controls><source src="/sample.mp4"></video>')

            class Handler(SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    if self.path == '/start':
                        self.send_response(302)
                        self.send_header('Location', '/page.html')
                        self.send_header('Set-Cookie', 'diagnostic=temporary; Path=/; HttpOnly')
                        self.end_headers()
                        return
                    if self.path.endswith(('.mp4', '.m3u8', '.ts', '.bin')) and 'diagnostic=temporary' not in self.headers.get('Cookie', ''):
                        self.send_error(403)
                        return
                    super().do_GET()

            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                stage = 'private_firefox_redirect_iframe'
                base = f'http://127.0.0.1:{server.server_port}'

                class FixtureGuard:
                    def ensure_public(self, url):
                        from urllib.parse import urlsplit
                        parsed = urlsplit(url)
                        if (parsed.scheme, parsed.hostname, parsed.port) != ('http', '127.0.0.1', server.server_port):
                            raise AppError(ErrorCode.INVALID_LINK, 'The diagnostic only allows its local fixture.')

                resolver = FirefoxMediaResolver(timeout_seconds=15, network_guard=FixtureGuard())
                with resolver.browser_session() as (port, extension):
                    page = resolver._inspect_page(port, base + '/start', extension)
                source = page.get('currentSrc') or next(iter(page.get('media') or []), None)
                if not source or '/sample.mp4' not in source:
                    raise RuntimeError('The test video was not detected')
                results[stage] = 'OK'
                stage = 'download_with_ephemeral_cookies'
                import yt_dlp
                options = YtDlpGateway._base_options(None) | {
                    'outtmpl': str(root / 'download.%(ext)s'), 'format': 'best',
                }
                with yt_dlp.YoutubeDL(options) as client:
                    YtDlpGateway._load_session_cookies(client, tuple(page.get('cookies') or []))
                    info = client.extract_info(source, download=True)
                    downloaded = Path(client.prepare_filename(info))
                if downloaded.read_bytes() != (root / 'sample.mp4').read_bytes():
                    raise RuntimeError('Downloaded bytes did not match')
                results[stage] = 'OK'
                stage = 'native_hls_aes128'
                options['outtmpl'] = str(root / 'hls.%(ext)s')
                with yt_dlp.YoutubeDL(options) as client:
                    YtDlpGateway._load_session_cookies(client, tuple(page.get('cookies') or []))
                    info = client.extract_info(f'http://127.0.0.1:{server.server_port}/playlist.m3u8', download=True)
                hls = root / 'hls.mp4'
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height',
                                        '-of', 'json', str(hls)], capture_output=True, check=True, timeout=15,
                                       **hidden_process_options())
                if not any(item.get('width') == 160 for item in json.loads(probe.stdout)['streams']):
                    raise RuntimeError('HLS output was invalid')
                results[stage] = 'OK'
                stage = 'video_format_validation'
                validator = VideoValidator()
                if validator.validate(downloaded, lambda: False) != 90:
                    raise RuntimeError('Video dimensions were not validated')
                validator.validate(hls, lambda: False)
                sample = root / 'fake.mp4'
                sample.write_bytes(b'<html>This is not a video</html>')
                try:
                    validator.validate(sample, lambda: False)
                except AppError as exc:
                    if exc.code != ErrorCode.FORMAT_UNAVAILABLE:
                        raise
                else:
                    raise RuntimeError('The fake video was accepted')
                results[stage] = 'OK'
                stage = 'video_over_2gb'
                large = root / 'large.mp4'
                shutil.copyfile(downloaded, large)
                with large.open('ab') as file:
                    file.truncate(2_147_483_649)
                validator.validate(large, lambda: False)
                results[stage] = 'OK'
                stage = 'site_threat_filter'
                # Synthetic threat list: never connect to an actual malicious URL.
                feed = root / 'threats.txt'
                feed.write_text("# Title: HaGeZi's Threat Intelligence Feeds - diagnostic fixture\n" +
                                '\n'.join(f'blocked-{number}.example' for number in range(60)))
                protection = SiteGuard(root / 'protection-cache', feed)
                protection.ensure_allowed('https://allowed.example/video')
                try:
                    protection.ensure_allowed('https://blocked-1.example/video')
                except AppError as exc:
                    if exc.code != ErrorCode.SITE_BLOCKED:
                        raise
                else:
                    raise RuntimeError('The synthetic malicious domain was not blocked')
                results[stage] = 'OK'
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
        results['temporary_files_removed'] = 'OK'
        print(json.dumps(results, indent=2))
        return 0
    except Exception as exc:
        results[stage] = exc.user_message if isinstance(exc, AppError) else type(exc).__name__
        if isinstance(exc.__cause__, OSError):
            # Numeric filesystem errors are useful for support without exposing
            # browsing data, personal directories, or downloaded filenames.
            results['filesystem_error'] = {
                'errno': exc.__cause__.errno,
                'windows_error': getattr(exc.__cause__, 'winerror', None),
            }
        print(json.dumps(results, indent=2))
        return 1
