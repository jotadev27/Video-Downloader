from http.cookiejar import Cookie, CookieJar
from types import SimpleNamespace

import pytest

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import DownloadRequest
from video_downloader.infrastructure.firefox_media_resolver import ResolvedMedia
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway

URL = "https://example.com/watch"
CANONICAL = "https://example.com/canonical"


class Guard:
    def ensure_public(self, url):
        pass


class Engine:
    def __init__(self, directory):
        self.directory = directory
        self.extractions = []
        self.processed = []
        self.clients = []
        self.rejections = 0
        self.unsupported = False

    def client(self, options):
        engine = self

        class Client:
            def __init__(self):
                self.options = options
                self.cookiejar = CookieJar()

            def __enter__(self):
                engine.clients.append(self)
                return self

            def __exit__(self, *args):
                pass

            def extract_info(self, url, download=False):
                engine.extractions.append((url, download))
                if engine.unsupported and url in {URL, CANONICAL}:
                    raise RuntimeError("Unsupported URL")
                raw = {"id": "film", "title": "Film", "webpage_url": CANONICAL,
                       "formats": [{"url": "https://cdn.example.com/film", "height": 720,
                                    "vcodec": "avc1", "ext": "mp4"}],
                       "requested_formats": [{"height": 1080}], "height": 1080}
                self.cookiejar.set_cookie(Cookie(
                    0, "session", "temporary", None, False, "example.com", False, False,
                    "/", True, True, None, True, None, None, {},
                ))
                return self.save(raw) if download else raw

            def process_ie_result(self, raw, download=True):
                engine.processed.append(raw)
                return self.save(raw)

            def save(self, raw):
                if engine.rejections:
                    engine.rejections -= 1
                    raise RuntimeError("HTTP Error 401: Unauthorized")
                output = engine.directory / "film.mp4"
                output.write_bytes(b"video")
                return {**raw, "height": 720, "_filename": "obsolete-intermediate.webm",
                        "requested_downloads": [{"filepath": str(output), "height": 720,
                                                 "vcodec": "avc1"}]}

        return Client()


def gateway_for(directory, resolver=None):
    engine = Engine(directory)
    gateway = YtDlpGateway(resolver, Guard())
    gateway._module = lambda: SimpleNamespace(YoutubeDL=engine.client)
    return gateway, engine


def test_inspection_is_reused_with_cookies_and_selected_quality(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    result = gateway.download(DownloadRequest(CANONICAL, tmp_path, 720), lambda _: None, lambda: False)
    assert engine.extractions == [(URL, False)]
    assert len(engine.processed) == 1
    assert "requested_formats" not in engine.processed[0]
    assert "height" not in engine.processed[0]
    assert "height=720" in engine.clients[-1].options["format"]
    assert next(iter(engine.clients[-1].cookiejar)).value == "temporary"
    assert result.file_path == tmp_path / "film.mp4"
    assert result.actual_height == 720
    assert not gateway._inspection_urls
    assert not gateway._inspection_cookies


def test_unauthorized_cached_source_is_refreshed_once(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    engine.rejections = 1
    events = []
    result = gateway.download(DownloadRequest(URL, tmp_path, 720), events.append, lambda: False)
    assert result.file_path.exists()
    assert engine.extractions == [(URL, False), (URL, False)]
    assert len(engine.processed) == 2
    assert engine.clients[-1].options["continuedl"] is False
    assert any(event.message == "Refreshing video session" for event in events)


def test_repeated_unauthorized_error_stops_without_retry_loop(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    engine.rejections = 10
    with pytest.raises(AppError) as caught:
        gateway.download(DownloadRequest(URL, tmp_path, 720), lambda _: None, lambda: False)
    assert caught.value.code == ErrorCode.ACCESS_REQUIRED
    assert len(engine.processed) == 2


def test_new_proxy_does_not_reuse_old_session(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    gateway.download(DownloadRequest(URL, tmp_path, 720, "http://proxy.example.com:8080"),
                     lambda _: None, lambda: False)
    assert engine.processed == []
    assert engine.extractions == [(URL, False), (URL, True)]


def test_stale_normal_inspection_extracts_fresh_urls(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    gateway._inspection_time -= 121
    gateway.download(DownloadRequest(URL, tmp_path, 720), lambda _: None, lambda: False)
    assert engine.processed == []
    assert engine.extractions[-1] == (URL, True)


class Resolver:
    def __init__(self):
        self.calls = []

    def resolve(self, url, proxy=None):
        self.calls.append(url)
        return ResolvedMedia(CANONICAL, f"https://cdn.example.com/video-{len(self.calls)}.mp4",
                             "100% film", 60, 1280, 720, None)


def test_browser_session_handles_redirects_and_refreshes_expired_media(tmp_path):
    resolver = Resolver()
    gateway, engine = gateway_for(tmp_path, resolver)
    engine.unsupported = True
    gateway.inspect(URL)
    engine.rejections = 1
    result = gateway.download(DownloadRequest(CANONICAL, tmp_path, 720), lambda _: None, lambda: False)
    assert result.file_path.exists()
    assert resolver.calls == [URL, CANONICAL]
    assert engine.extractions[-1] == ("https://cdn.example.com/video-2.mp4", True)
    assert "100%% film" in engine.clients[-1].options["outtmpl"]["default"]
    assert not gateway._resolved_media


def test_cancel_during_refresh_starts_no_second_network_request(tmp_path):
    gateway, engine = gateway_for(tmp_path)
    gateway.inspect(URL)
    engine.rejections = 1
    with pytest.raises(AppError) as caught:
        gateway.download(DownloadRequest(URL, tmp_path, 720), lambda _: None,
                         lambda: engine.rejections == 0)
    assert caught.value.code == ErrorCode.CANCELLED
    assert engine.extractions == [(URL, False)]


def test_browser_request_referer_overrides_top_page_referer():
    media = ResolvedMedia(URL, "https://cdn.example.com/video.mp4", "Film", None,
                          None, None, None, request_headers=(("referer", CANONICAL),))
    assert media.headers["Referer"] == CANONICAL
