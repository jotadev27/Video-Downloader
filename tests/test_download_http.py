from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from video_downloader.domain.models import DownloadRequest
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


class FixtureGuard:
    """Only this synthetic offline fixture may use loopback addresses."""

    def ensure_public(self, url):
        assert url.startswith("http://127.0.0.1:")


@contextmanager
def media_server():
    state = {"token": 0, "pages": 0, "rejected": 0}
    payload = b"local video download fixture\x00" * 1024

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/watch/"):
                state["pages"] += 1
                state["token"] += 1
                self.send_response(302)
                self.send_header("Location", "/media/film.mp4")
                self.send_header("Set-Cookie", f"session={state['token']}; Path=/; HttpOnly")
                self.end_headers()
                return
            if self.path == "/media/film.mp4":
                if self.headers.get("Cookie") != f"session={state['token']}":
                    state["rejected"] += 1
                    self.send_error(401)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state, payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_two_real_downloads_preserve_redirect_cookies_without_duplicate_extraction(tmp_path):
    with media_server() as (base, state, payload):
        gateway = YtDlpGateway(network_guard=FixtureGuard())
        for number in (1, 2):
            url = f"{base}/watch/{number}"
            info = gateway.inspect(url)
            assert info.qualities
            directory = tmp_path / str(number)
            directory.mkdir()
            result = gateway.download(DownloadRequest(url, directory, 0),
                                      lambda _: None, lambda: False)
            assert result.file_path.read_bytes() == payload
        assert state["pages"] == 2
        assert state["rejected"] == 0


def test_real_http_401_refreshes_source_session_and_downloads_complete_bytes(tmp_path):
    with media_server() as (base, state, payload):
        gateway = YtDlpGateway(network_guard=FixtureGuard())
        url = f"{base}/watch/1"
        gateway.inspect(url)
        state["token"] += 1  # Expire the session before the user presses Download.
        events = []
        result = gateway.download(DownloadRequest(url, tmp_path, 0), events.append, lambda: False)
        assert result.file_path.read_bytes() == payload
        assert state["pages"] == 2
        assert state["rejected"] > 0
        assert any(event.message == "Refreshing video session" for event in events)
